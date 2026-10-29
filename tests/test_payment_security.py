import hashlib
import hmac
import json
import os
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from flask import Flask, Response
import middleware.auth as auth
import routes.downloads as downloads
import routes.admin as admin_routes
import services.customer_auth_service as customer_auth
import services.order_service as service
from routes.auth import bp as auth_bp
from routes.orders import orders_bp


class SQLiteClient:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        cursor = self.connection.execute(sql, params)
        return type("Result", (), {"rows": cursor.fetchall() if cursor.description else []})()


class PaymentSecurityTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        self.client = SQLiteClient(self.connection)
        for statement in (
            "CREATE TABLE products(id TEXT PRIMARY KEY,name TEXT,price INTEGER,sales_count INTEGER DEFAULT 0)",
            "CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT UNIQUE COLLATE NOCASE,phone TEXT,password_hash TEXT,display_name TEXT,role TEXT,is_active INTEGER)",
            "CREATE TABLE orders(id TEXT PRIMARY KEY,user_id TEXT,status TEXT,subtotal INTEGER,total INTEGER,currency TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE order_items(id TEXT PRIMARY KEY,order_id TEXT,product_id TEXT,product_version_id TEXT,quantity INTEGER,unit_price INTEGER,total_price INTEGER)",
            "CREATE TABLE payments(id TEXT PRIMARY KEY,order_id TEXT NOT NULL,provider TEXT,provider_payment_id TEXT,status TEXT DEFAULT 'pending',amount INTEGER DEFAULT 0,currency TEXT DEFAULT 'INR',paid_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)",
            "CREATE TABLE product_versions(id TEXT PRIMARY KEY,product_id TEXT,version TEXT,single_file_path TEXT,package_file_path TEXT,is_active INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP)",
        ):
            self.client.execute(statement)
        self.client.execute("INSERT INTO users(id,email,role,is_active) VALUES ('customer-1','customer@example.com','customer',1)")
        self.client.execute("INSERT INTO products VALUES ('ABC123','Test Product',1200,0)")
        self.client.execute("INSERT INTO product_versions(id,product_id,version,single_file_path,package_file_path,is_active) VALUES ('version-1','ABC123','1.0.0',NULL,'files/test.zip',1)")
        self.order_id = "CSO-TEST-ORDER"
        self.client.execute("INSERT INTO orders(id,user_id,status,subtotal,total,currency) VALUES(?,?,'pending',1200,1200,'INR')", (self.order_id, "customer-1"))
        self.client.execute("INSERT INTO order_items VALUES('item-1',?,'ABC123','version-1',1,1200,1200)", (self.order_id,))
        self.env = patch.dict(os.environ, {
            "PAYMENTS_ENABLED": "true", "RAZORPAY_MODE": "test",
            "RAZORPAY_KEY_ID": "rzp_test_example", "RAZORPAY_KEY_SECRET": "test-key-secret",
            "RAZORPAY_WEBHOOK_SECRET": "test-webhook-secret", "JWT_SECRET": "test-jwt-secret-that-is-long-enough",
        })
        self.env.start()
        self.connection_patch = patch.object(service, "get_connection", self.connection_context)
        self.connection_patch.start()
        self.customer_auth_connection_patch = patch.object(customer_auth, "get_connection", self.connection_context)
        self.customer_auth_connection_patch.start()
        self.download_connection_patch = patch.object(downloads, "get_connection", self.connection_context)
        self.download_connection_patch.start()
        self.admin_connection_patch = patch.object(admin_routes, "get_connection", self.connection_context)
        self.admin_connection_patch.start()
        self.app = Flask(__name__)
        self.app.register_blueprint(downloads.downloads_bp, url_prefix="/api/downloads")
        self.app.register_blueprint(orders_bp, url_prefix="/api/orders")
        self.app.register_blueprint(auth_bp, url_prefix="/api/auth")
        self.app.register_blueprint(admin_routes.bp, url_prefix="/api/admin")
        self.app.testing = True
        self.client_http = self.app.test_client()
        self.token_patch = patch.object(auth, "verify_token", side_effect=lambda token: {"sub": "admin-1", "role": "admin"} if token=="admin-token" else {"sub": "customer-1", "role": "customer"})
        self.token_patch.start()

    @contextmanager
    def connection_context(self):
        yield self.client

    def tearDown(self):
        self.token_patch.stop()
        self.download_connection_patch.stop()
        self.admin_connection_patch.stop()
        self.customer_auth_connection_patch.stop()
        self.connection_patch.stop()
        self.env.stop()
        self.connection.close()

    def start_remote_order(self):
        with patch.object(service, "_razorpay_request", return_value={"id": "order_test_1"}) as remote:
            payment_order = service.start_payment(self.order_id, "customer-1")
        remote.assert_called_once()
        return payment_order

    def signature(self, value):
        return hmac.new(b"test-key-secret", value.encode(), hashlib.sha256).hexdigest()

    def captured_payment(self, status="captured", amount=1200):
        return {"id": "pay_test_1", "order_id": "order_test_1", "amount": amount,
                "currency": "INR", "status": status}

    def webhook(self, amount=1200):
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": "pay_test_1", "order_id": "order_test_1", "amount": amount,
            "currency": "INR", "status": "captured"}}}}).encode()
        signature = hmac.new(b"test-webhook-secret", body, hashlib.sha256).hexdigest()
        return body, signature

    def test_successful_payment_requires_captured_server_confirmation(self):
        self.start_remote_order()
        signature = self.signature("order_test_1|pay_test_1")
        with patch.object(service, "_razorpay_request", return_value=self.captured_payment()):
            service.verify_checkout("customer-1", self.order_id, "order_test_1", "pay_test_1", signature)
        self.assertEqual(self.client.execute("SELECT status FROM orders WHERE id=?", (self.order_id,)).rows[0][0], "paid")
        self.assertEqual(self.client.execute("SELECT status FROM payments WHERE order_id=?", (self.order_id,)).rows[0][0], "captured")
        class FakePath:
            def __init__(self, value): self.value=value
            def resolve(self): return self
            @property
            def parent(self): return FakePath(self.value.rsplit("/",1)[0])
            def __truediv__(self, part): return FakePath(self.value.rstrip("/")+"/"+str(part))
            @property
            def parents(self):
                bits=self.value.split("/")
                return tuple(FakePath("/".join(bits[:i])) for i in range(len(bits)-1,0,-1))
            def is_file(self): return True
            def __eq__(self, other): return isinstance(other,FakePath) and self.value==other.value
        with patch.object(downloads,"Path",side_effect=lambda value:FakePath("/app/routes/downloads.py")), patch.object(downloads,"send_file",return_value=Response("download")):
            response=self.client_http.post("/api/downloads/authorize",headers={"Authorization":"Bearer customer-token"},json={"product_id":"ABC123","order_id":self.order_id})
        self.assertEqual((response.status_code,response.get_data(as_text=True)),(200,"download"))

    def test_failed_payment_leaves_order_pending(self):
        self.start_remote_order()
        signature = self.signature("order_test_1|pay_test_1")
        with patch.object(service, "_razorpay_request", return_value=self.captured_payment(status="failed")):
            with self.assertRaisesRegex(ValueError, "not confirmed"):
                service.verify_checkout("customer-1", self.order_id, "order_test_1", "pay_test_1", signature)
        self.assertEqual(self.client.execute("SELECT status FROM orders WHERE id=?", (self.order_id,)).rows[0][0], "pending")

    def test_invalid_checkout_signature_is_rejected(self):
        self.start_remote_order()
        with self.assertRaisesRegex(ValueError, "signature is invalid"):
            service.verify_checkout("customer-1", self.order_id, "order_test_1", "pay_test_1", "forged")

    def test_forged_webhook_is_rejected(self):
        self.start_remote_order()
        body, _ = self.webhook()
        with self.assertRaisesRegex(ValueError, "Webhook signature is invalid"):
            service.handle_webhook(body, "forged")
        self.assertEqual(self.client.execute("SELECT status FROM orders WHERE id=?", (self.order_id,)).rows[0][0], "pending")

    def test_duplicate_webhook_is_idempotent(self):
        self.start_remote_order()
        body, signature = self.webhook()
        self.assertEqual(service.handle_webhook(body, signature), "captured")
        self.assertEqual(service.handle_webhook(body, signature), "duplicate")
        self.assertEqual(self.client.execute("SELECT sales_count FROM products WHERE id='ABC123'").rows[0][0], 1)

    def test_webhook_with_incorrect_amount_does_not_pay_order(self):
        self.start_remote_order()
        body, signature = self.webhook(amount=1199)
        with self.assertRaisesRegex(ValueError, "amount or currency"):
            service.handle_webhook(body, signature)
        self.assertEqual(self.client.execute("SELECT status FROM orders WHERE id=?", (self.order_id,)).rows[0][0], "pending")

    def test_download_is_denied_before_payment(self):
        response = self.client_http.post("/api/downloads/authorize", headers={"Authorization": "Bearer customer-token"},
                                         json={"product_id": "ABC123", "order_id": self.order_id})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "A confirmed paid order is required")

    def test_registration_and_login_use_real_bcrypt_without_auth_changes(self):
        response=self.client_http.post("/api/auth/register",json={"email":"new@example.com","display_name":"New Customer","password":"correct-horse-7"})
        self.assertEqual(response.status_code,201,response.get_json())
        customer_id=response.get_json()["customer"]["id"]
        self.assertRegex(customer_id,r"^CS-[A-HJ-NP-Z2-9]{8}$")
        success=self.client_http.post("/api/auth/login",json={"email":"new@example.com","password":"correct-horse-7"})
        self.assertEqual(success.status_code,200,success.get_json())
        failure=self.client_http.post("/api/auth/login",json={"email":"new@example.com","password":"wrong-password"})
        self.assertEqual(failure.status_code,401)

    def test_order_creation_uses_server_price_and_authenticated_customer(self):
        product={"id":"ABC123","name":"Test Product","price":1200,"currency":"INR","is_free":False,"is_published":True}
        with patch.object(service.ProductService,"get_product",return_value=product):
            response=self.client_http.post("/api/orders/",headers={"Authorization":"Bearer customer-token"},json={"items":[{"id":"ABC123","quantity":2,"unit_price":1}]})
        self.assertEqual(response.status_code,201,response.get_json())
        order_id=response.get_json()["result"]["order_id"]
        stored=self.client.execute("SELECT user_id,status,total FROM orders WHERE id=?",(order_id,)).rows[0]
        item=self.client.execute("SELECT product_id,quantity,unit_price,total_price FROM order_items WHERE order_id=?",(order_id,)).rows[0]
        self.assertEqual(stored,("customer-1","pending",2400))
        self.assertEqual(item,("ABC123",2,1200,2400))

    def create_cash_order(self):
        product={"id":"ABC123","name":"Test Product","price":1200,"currency":"INR","is_free":False,"is_published":True}
        with patch.object(service.ProductService,"get_product",return_value=product):
            response=self.client_http.post("/api/orders/cash",headers={"Authorization":"Bearer customer-token"},json={"items":[{"id":"ABC123","quantity":1,"unit_price":1}]})
        self.assertEqual(response.status_code,201,response.get_json())
        return response.get_json()["result"]["order_id"]

    def test_cash_order_is_pending_and_uses_server_calculated_total(self):
        order_id=self.create_cash_order()
        self.assertEqual(self.client.execute("SELECT user_id,status,total,currency FROM orders WHERE id=?",(order_id,)).rows[0],("customer-1","pending_cash",1200,"INR"))
        own_order=self.client_http.get("/api/orders/",headers={"Authorization":"Bearer customer-token"}).get_json()["result"]
        self.assertEqual(next(row for row in own_order if row["id"]==order_id)["status"],"pending_cash")

    def test_upi_order_uses_server_price_and_existing_admin_review_status(self):
        product={"id":"ABC123","name":"Test Product","price":1200,"currency":"INR","is_free":False,"is_published":True}
        with patch.object(service.ProductService,"get_product",return_value=product):
            response=self.client_http.post("/api/orders/upi",headers={"Authorization":"Bearer customer-token"},json={"items":[{"id":"ABC123","quantity":2,"unit_price":1}]})
        self.assertEqual(response.status_code,201,response.get_json())
        result=response.get_json()["result"]
        self.assertEqual((result["status"],result["payment_method"],result["total"]),("pending_cash","upi",2400))
        self.assertEqual(self.client.execute("SELECT user_id,status,total FROM orders WHERE id=?",(result["order_id"],)).rows[0],("customer-1","pending_cash",2400))

    def test_online_checkout_is_disabled_without_creating_order(self):
        response=self.client_http.post("/api/orders/online",headers={"Authorization":"Bearer customer-token"},json={"items":[{"id":"ABC123"}]})
        self.assertEqual(response.status_code,503)
        self.assertIn("currently unavailable",response.get_json()["error"])
        self.assertEqual(self.client.execute("SELECT COUNT(*) FROM orders").rows[0][0],1)

    def test_only_admin_can_confirm_cash_receipt(self):
        order_id=self.create_cash_order()
        response=self.client_http.post(f"/api/admin/orders/{order_id}/confirm-cash",headers={"Authorization":"Bearer customer-token"})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.client.execute("SELECT status FROM orders WHERE id=?",(order_id,)).rows[0][0],"pending_cash")

    def test_upi_details_are_publicly_readable_and_admin_writable_only(self):
        public=self.client_http.get("/api/orders/payment-options")
        self.assertEqual(public.status_code,200)
        self.assertEqual(public.get_json()["result"]["upi_id"],"")
        denied=self.client_http.put("/api/admin/payment-settings",headers={"Authorization":"Bearer customer-token"},json={"upi_id":"seller@upi"})
        self.assertEqual(denied.status_code,403)
        invalid=self.client_http.put("/api/admin/payment-settings",headers={"Authorization":"Bearer admin-token"},json={"upi_id":"not a UPI ID"})
        self.assertEqual(invalid.status_code,400)
        saved=self.client_http.put("/api/admin/payment-settings",headers={"Authorization":"Bearer admin-token"},json={"upi_id":"seller@upi"})
        self.assertEqual(saved.status_code,200,saved.get_json())
        self.assertEqual(self.client_http.get("/api/orders/payment-options").get_json()["result"]["upi_id"],"seller@upi")

    def test_admin_cash_approval_records_details_and_rejects_duplicate(self):
        order_id=self.create_cash_order()
        response=self.client_http.post(f"/api/admin/orders/{order_id}/confirm-cash",headers={"Authorization":"Bearer admin-token"})
        self.assertEqual(response.status_code,200,response.get_json())
        result=response.get_json()["result"]
        self.assertEqual((result["order_id"],result["customer_id"],result["amount"],result["approved_by"],result["status"]),(order_id,"customer-1",1200,"admin-1","paid"))
        self.assertTrue(result["approved_at"])
        duplicate=self.client_http.post(f"/api/admin/orders/{order_id}/confirm-cash",headers={"Authorization":"Bearer admin-token"})
        self.assertEqual(duplicate.status_code,409)
        self.assertEqual(self.client.execute("SELECT COUNT(*) FROM cash_approvals WHERE order_id=?",(order_id,)).rows[0][0],1)

    def test_cash_download_is_denied_before_and_allowed_after_approval(self):
        order_id=self.create_cash_order()
        payload={"product_id":"ABC123","order_id":order_id}
        headers={"Authorization":"Bearer customer-token"}
        denied=self.client_http.post("/api/downloads/authorize",headers=headers,json=payload)
        self.assertEqual(denied.status_code,403)
        approved=self.client_http.post(f"/api/admin/orders/{order_id}/confirm-cash",headers={"Authorization":"Bearer admin-token"})
        self.assertEqual(approved.status_code,200)
        class FakePath:
            def __init__(self,value):self.value=value
            def resolve(self):return self
            @property
            def parent(self):return FakePath(self.value.rsplit("/",1)[0])
            def __truediv__(self,part):return FakePath(self.value.rstrip("/")+"/"+str(part))
            @property
            def parents(self):
                bits=self.value.split("/")
                return tuple(FakePath("/".join(bits[:i])) for i in range(len(bits)-1,0,-1))
            def is_file(self):return True
            def __eq__(self,other):return isinstance(other,FakePath) and self.value==other.value
        with patch.object(downloads,"Path",side_effect=lambda value:FakePath("/app/routes/downloads.py")),patch.object(downloads,"send_file",return_value=Response("download")):
            granted=self.client_http.post("/api/downloads/authorize",headers=headers,json=payload)
        self.assertEqual((granted.status_code,granted.get_data(as_text=True)),(200,"download"))


if __name__ == "__main__":
    unittest.main()
