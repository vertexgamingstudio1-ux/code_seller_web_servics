import datetime
import pathlib
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import sys
from zoneinfo import ZoneInfo
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from flask import Flask
import middleware.auth as auth
import routes.admin as admin
import routes.customer as customer
import routes.orders as orders
import routes.products as products
import routes.community as community
import services.product_service as product_service
from routes.admin import bp as admin_bp
from routes.customer import bp as customer_bp
from routes.orders import orders_bp
from routes.products import bp as products_bp
from routes.community import bp as community_bp

class Result:
    def __init__(self, rows):
        self.rows = rows

class Client:
    def __init__(self, connection):
        self.connection = connection
        self.rows_affected = 0

    def execute(self, sql, params=()):
        cursor = self.connection.execute(sql, params)
        self.rows_affected = cursor.rowcount
        return Result(cursor.fetchall() if cursor.description else [])

class Database:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        self.client = Client(self.connection)
        self.client.execute("CREATE TABLE users (id TEXT PRIMARY KEY,email TEXT,phone TEXT,role TEXT,display_name TEXT,is_active INTEGER DEFAULT 1)")
        self.client.execute("""CREATE TABLE products (
            id TEXT PRIMARY KEY,name TEXT,slug TEXT UNIQUE,description TEXT,category TEXT,
            price INTEGER,currency TEXT,margin_percent REAL DEFAULT 0,is_free INTEGER DEFAULT 0,
            is_published INTEGER DEFAULT 0,sales_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        self.client.execute("""CREATE TABLE product_versions (
            id TEXT PRIMARY KEY,product_id TEXT,version TEXT,changelog TEXT,
            single_file_path TEXT,package_file_path TEXT,is_active INTEGER)""")
        self.client.execute("INSERT INTO users(id,email,role,display_name) VALUES ('customer-1','customer@example.com','customer','Customer One'),('admin-1','admin@example.com','admin','Admin One')")
        self.client.execute("INSERT INTO products(id,name,slug,description,category,price,currency,is_free,is_published) VALUES ('product-1','Test Pack','test-pack','Test description','Tools',999,'INR',0,1)")
        self.client.execute("CREATE TABLE orders (id TEXT PRIMARY KEY,user_id TEXT,status TEXT,subtotal INTEGER,total INTEGER,currency TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        self.client.execute("CREATE TABLE order_items (id TEXT PRIMARY KEY,order_id TEXT,product_id TEXT,quantity INTEGER,unit_price INTEGER,total_price INTEGER)")
        self.client.execute("CREATE TABLE payments (id TEXT PRIMARY KEY,order_id TEXT,provider TEXT,status TEXT,amount INTEGER,currency TEXT,provider_payment_id TEXT,paid_at TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        self.client.execute("CREATE TABLE cash_approvals (order_id TEXT PRIMARY KEY,approved_by TEXT,approved_at TEXT)")

    @contextmanager
    def connection_context(self):
        yield self.client

class CodeSellerFeatureTests(unittest.TestCase):
    def setUp(self):
        self.database = Database()
        self.tokens = {
            "customer-token": {"sub": "customer-1", "role": "customer", "email": "customer@example.com"},
            "admin-token": {"sub": "admin-1", "role": "admin", "email": "admin@example.com"},
            "other-token": {"sub": "customer-2", "role": "customer", "email": "other@example.com"},
        }
        self.app = Flask(__name__)
        self.app.register_blueprint(admin_bp, url_prefix="/api/admin")
        self.app.register_blueprint(customer_bp, url_prefix="/api/customer")
        self.app.register_blueprint(orders_bp, url_prefix="/api/orders")
        self.app.register_blueprint(products_bp, url_prefix="/api/products")
        self.app.register_blueprint(community_bp, url_prefix="/api/community")
        self.app.testing = True
        self.client = self.app.test_client()
        self.today = datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()
        self.patches = [
            patch.object(auth, "verify_token", side_effect=lambda token: self.tokens[token]),
            patch.object(product_service, "get_connection", self.database.connection_context),
            patch.object(admin, "get_connection", self.database.connection_context),
            patch.object(customer, "get_connection", self.database.connection_context),
            patch.object(community, "get_connection", self.database.connection_context),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.database.connection.close()

    def bearer(self, role="customer"):
        return {"Authorization": "Bearer " + ("customer-token" if role == "customer" else "admin-token")}

    def campaign_payload(self, start, end, enabled=True, scheduler=True, overlap=False):
        records = [{"slug": "holi", "reference_sale_start": start, "campaign_end_date": end, "enabled": enabled}]
        records.extend({"slug": slug, "reference_sale_start": start if overlap else None,
                        "campaign_end_date": end if overlap else None, "enabled": overlap}
                       for slug in ("diwali", "navratri", "ganesh-chaturthi", "new-year"))
        return {"enabled": scheduler, "campaigns": records}

    def save_schedule(self, payload):
        return self.client.put("/api/admin/festival-scheduler", headers=self.bearer("admin"), json=payload)

    def test_discount_window_quote_overlap_and_original_price(self):
        start=(self.today + datetime.timedelta(days=1)).isoformat()
        end=(self.today + datetime.timedelta(days=3)).isoformat()
        saved=self.save_schedule(self.campaign_payload(start,end))
        self.assertEqual(saved.status_code,200)
        holi=next(c for c in saved.get_json()["result"]["campaigns"] if c["slug"]=="holi")
        self.assertEqual(holi["campaign_start_date"],self.today.isoformat())
        product=self.client.get("/api/products/product-1").get_json()["result"]
        self.assertEqual((product["original_price"],product["price"],product["festival_discount_percent"]),(999,699,30))
        quote=self.client.post("/api/orders/quote",json={"items":[{"id":"product-1","quantity":2}]})
        self.assertEqual(quote.get_json()["result"]["total"],1398)
        self.save_schedule(self.campaign_payload(start,end,overlap=True))
        self.assertEqual(self.client.get("/api/products/product-1").get_json()["result"]["price"],699)
        self.save_schedule(self.campaign_payload(start,end,scheduler=False,overlap=True))
        self.assertEqual(self.client.get("/api/products/product-1").get_json()["result"]["price"],999)
        past_start=(self.today-datetime.timedelta(days=3)).isoformat()
        past_end=(self.today-datetime.timedelta(days=2)).isoformat()
        self.save_schedule(self.campaign_payload(past_start,past_end,overlap=False))
        self.assertEqual(self.client.get("/api/products/product-1").get_json()["result"]["price"],999)

    def test_invalid_schedule_and_authorization(self):
        response=self.save_schedule({"enabled":True,"campaigns":[{"slug":"holi","reference_sale_start":"not-a-date"}]})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get("/api/admin/demands",headers=self.bearer()).status_code,403)

    def test_customer_admin_demand_chat_and_thread_ownership(self):
        created=self.client.post("/api/customer/demands",headers=self.bearer(),json={"subject":"Before purchase","message":"Does this run on Windows?"})
        self.assertEqual(created.status_code,201)
        thread_id=created.get_json()["result"]["id"]
        inbox=self.client.get("/api/admin/demands",headers=self.bearer("admin"))
        self.assertEqual(len(inbox.get_json()["result"]),1)
        self.assertEqual(self.client.get(f"/api/customer/demands/{thread_id}/messages",headers={"Authorization":"Bearer other-token"}).status_code,404)
        reply=self.client.post(f"/api/admin/demands/{thread_id}/messages",headers=self.bearer("admin"),json={"message":"Yes, it does."})
        self.assertEqual(reply.status_code,201)
        messages=self.client.get(f"/api/customer/demands/{thread_id}/messages",headers=self.bearer()).get_json()["result"]
        self.assertEqual([m["sender_role"] for m in messages],["customer","admin"])

    def test_public_community_read_authenticated_post_and_idempotent_likes(self):
        public=self.client.get("/api/community/discussions/posts")
        self.assertEqual(public.status_code,200)
        created=self.client.post("/api/community/discussions/posts",headers=self.bearer(),json={"content":"Python project ideas"})
        self.assertEqual(created.status_code,201)
        post_id=created.get_json()["result"]["id"]
        self.assertEqual(self.client.post(f"/api/community/discussions/likes/post/{post_id}",headers=self.bearer()).status_code,200)
        self.client.post(f"/api/community/discussions/likes/post/{post_id}",headers=self.bearer())
        listed=self.client.get("/api/community/discussions/posts?sort=popular").get_json()["result"]
        self.assertEqual(listed[0]["like_count"],1)
        self.assertEqual(listed[0]["author"],"Customer One")
        self.assertNotIn("email",listed[0])
        self.assertEqual(self.client.post("/api/community/discussions/posts",json={"content":"anonymous"}).status_code,401)

    def test_admin_order_search_is_exact_and_authorized(self):
        self.database.client.execute("INSERT INTO orders(id,user_id,status,subtotal,total,currency) VALUES('CSO-ABC123','customer-1','pending_cash',999,999,'INR')")
        self.database.client.execute("INSERT INTO order_items(id,order_id,product_id,quantity,unit_price,total_price) VALUES('item-1','CSO-ABC123','product-1',1,999,999)")
        response=self.client.get("/api/admin/orders/search?q=CSO-ABC123",headers=self.bearer("admin"))
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()["result"][0]["id"],"CSO-ABC123")
        self.assertEqual(len(response.get_json()["result"][0]["items"]),1)
        self.assertEqual(self.client.get("/api/admin/orders/search?q=CSO-ABC123",headers=self.bearer()).status_code,403)

    def test_single_file_and_whole_package_create_product_versions(self):
        original_file=admin.__file__
        with tempfile.TemporaryDirectory() as tmp:
            route_dir=pathlib.Path(tmp)/"routes"
            route_dir.mkdir()
            admin.__file__=str(route_dir/"admin.py")
            try:
                cases=(("single",[{"name":"main.py","content":"print(1)"}],"single-demo"),("package",[{"name":"src/app.js","content":"export const x=1"}],"package-demo"))
                for kind,files,slug in cases:
                    response=self.client.post("/api/admin/products/with-code",headers=self.bearer("admin"),json={"name":slug,"slug":slug,"description":"test","version":"1.0.0","price":100,"product_type":kind,"files":files,"is_published":True})
                    self.assertEqual(response.status_code,201,response.get_json())
                    product_id=response.get_json()["result"]["id"]
                    stored=self.database.client.execute("SELECT single_file_path,package_file_path FROM product_versions WHERE product_id=?",(product_id,)).rows[0]
                    self.assertEqual((bool(stored[0]),bool(stored[1])),(kind=="single",kind=="package"))
            finally:
                admin.__file__=original_file

if __name__ == "__main__":
    unittest.main()



