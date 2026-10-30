import datetime
import io
import os
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
import routes.memberships as memberships
import routes.management as management
import routes.campaigns as campaigns
import services.product_service as product_service
import services.order_service as order_service
import services.object_storage as object_storage
from werkzeug.datastructures import FileStorage
import db
from routes.admin import bp as admin_bp
from routes.customer import bp as customer_bp
from routes.orders import orders_bp
from routes.products import bp as products_bp
from routes.community import bp as community_bp
from routes.memberships import bp as memberships_bp
from routes.management import bp as management_bp
from routes.campaigns import bp as campaigns_bp

class ObjectStorageValidationTests(unittest.TestCase):
    def test_upload_rejects_unsafe_type_mime_signature_and_oversize_before_storage(self):
        cases = [
            ("banner.svg", "image/svg+xml", b"<svg/>", "PNG, JPEG or WebP"),
            ("banner.png", "image/jpeg", b"\x89PNG\r\n\x1a\n", "content type"),
            ("banner.png", "image/png", b"not an image", "valid image"),
            ("banner.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024), "5 MB"),
        ]
        with patch.object(object_storage, "_client", side_effect=AssertionError("storage must not be contacted")):
            for filename, mimetype, payload, expected in cases:
                with self.subTest(filename=filename, expected=expected):
                    image = FileStorage(stream=io.BytesIO(payload), filename=filename, content_type=mimetype)
                    with self.assertRaisesRegex(ValueError, expected):
                        object_storage.upload(image, prefix="campaigns", max_bytes=5 * 1024 * 1024)

class Result:
    def __init__(self, rows, rows_affected=0):
        self.rows = rows
        self.rows_affected = rows_affected

class Client:
    def __init__(self, connection):
        self.connection = connection
        self.rows_affected = 0

    def execute(self, sql, params=()):
        cursor = self.connection.execute(sql, params)
        self.rows_affected = cursor.rowcount
        return Result(cursor.fetchall() if cursor.description else [], cursor.rowcount)

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
            single_file_path TEXT,package_file_path TEXT,is_active INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        self.client.execute("INSERT INTO users(id,email,role,display_name) VALUES ('customer-1','customer@example.com','customer','Customer One'),('admin-1','admin@example.com','admin','Admin One')")
        self.client.execute("INSERT INTO products(id,name,slug,description,category,price,currency,is_free,is_published) VALUES ('product-1','Test Pack','test-pack','Test description','Tools',999,'INR',0,1)")
        self.client.execute("CREATE TABLE orders (id TEXT PRIMARY KEY,user_id TEXT,status TEXT,subtotal INTEGER,total INTEGER,currency TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        self.client.execute("CREATE TABLE order_items (id TEXT PRIMARY KEY,order_id TEXT,product_id TEXT,product_version_id TEXT,quantity INTEGER,unit_price INTEGER,total_price INTEGER)")
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
        self.app.register_blueprint(memberships_bp, url_prefix="/api/memberships")
        self.app.register_blueprint(management_bp, url_prefix="/api/admin")
        self.app.register_blueprint(campaigns_bp, url_prefix="/api/campaigns")
        self.app.testing = True
        self.client = self.app.test_client()
        self.today = datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date()
        self.patches = [
            patch.object(auth, "verify_token", side_effect=lambda token: self.tokens[token]),
            patch.object(product_service, "get_connection", self.database.connection_context),
            patch.object(product_service, "_membership_discount", side_effect=lambda user_id: (memberships.product_discount_percent(self.database.client,user_id) if user_id else (0,None))),
            patch.object(order_service, "get_connection", self.database.connection_context),
            patch.object(products, "verify_token", side_effect=lambda token: self.tokens[token]),
            patch.object(orders, "verify_token", side_effect=lambda token: self.tokens[token]),
            patch.object(admin, "get_connection", self.database.connection_context),
            patch.object(customer, "get_connection", self.database.connection_context),
            patch.object(community, "get_connection", self.database.connection_context),
            patch.object(memberships, "get_connection", self.database.connection_context),
            patch.object(management, "get_connection", self.database.connection_context),
            patch.object(campaigns, "get_connection", self.database.connection_context),
            patch.object(db, "get_connection", self.database.connection_context),
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

    def test_member_festival_pricing_matches_catalog_quote_and_order(self):
        plans=self.client.get("/api/memberships/plans").get_json()["result"]
        self.assertEqual([(p["plan_key"],p["product_discount_percent"]) for p in plans],[('basic',0),('plus',5),('premium',10)])
        self.assertEqual(self.client.get("/api/products/product-1").get_json()["result"]["price"],999)
        approved=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=30)).isoformat().replace("+00:00","Z")
        self.database.client.execute("INSERT INTO membership_applications(membership_id,customer_id,plan_key,status,activated_at,expires_at) VALUES('CSM-PLUS','customer-1','plus','approved',?,?)",(datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),approved))
        member_product=self.client.get("/api/products/product-1",headers=self.bearer()).get_json()["result"]
        self.assertEqual((member_product["original_price"],member_product["price"],member_product["membership_discount_percent"]),(999,949,5))
        start=(self.today + datetime.timedelta(days=1)).isoformat();end=(self.today + datetime.timedelta(days=3)).isoformat()
        self.save_schedule(self.campaign_payload(start,end))
        nonmember=self.client.get("/api/products/product-1").get_json()["result"]
        combined=self.client.get("/api/products/product-1",headers=self.bearer()).get_json()["result"]
        self.assertEqual((nonmember["price"],nonmember["festival_discount_percent"],nonmember["membership_discount_percent"]),(699,30,0))
        self.assertEqual((combined["price"],combined["festival_discount_percent"],combined["membership_discount_percent"]),(664,30,5))
        quoted=self.client.post("/api/orders/quote",headers=self.bearer(),json={"items":[{"id":"product-1","quantity":2}]}).get_json()["result"]
        self.assertEqual((quoted["subtotal"],quoted["discount_total"],quoted["total"]),(1998,670,1328))
        self.assertEqual((quoted["items"][0]["festival_discount_amount"],quoted["items"][0]["membership_discount_amount"]),(600,70))
        created=self.client.post("/api/orders/upi",headers=self.bearer(),json={"items":[{"id":"product-1","quantity":2}]})
        self.assertEqual(created.status_code,201,created.get_json())
        order_id=created.get_json()["result"]["order_id"]
        self.assertEqual(created.get_json()["result"]["total"],quoted["total"])
        self.assertEqual(self.database.client.execute("SELECT subtotal,total FROM orders WHERE id=?",(order_id,)).rows[0],(1998,1328))
        item=self.database.client.execute("SELECT unit_price,total_price,original_unit_price,festival_discount_percent,membership_discount_percent FROM order_items WHERE order_id=?",(order_id,)).rows[0]
        self.assertEqual(item,(664,1328,999,30,5))
        admin_order=self.client.get("/api/admin/orders/search?q="+order_id,headers=self.bearer("admin")).get_json()["result"][0]
        self.assertEqual((admin_order["total"],admin_order["items"][0]["festival_discount_amount"],admin_order["items"][0]["membership_discount_amount"]),(1328,300,35))
        self.database.client.execute("INSERT INTO products(id,name,slug,description,category,price,currency,is_free,is_published) VALUES('free-1','Free Pack','free-pack','Free product','Tools',0,'INR',1,1)")
        free=self.client.get("/api/products/free-1",headers=self.bearer()).get_json()["result"]
        self.assertEqual((free["price"],free["festival_discount_percent"],free["membership_discount_percent"]),(0,0,0))

    def test_product_catalog_splits_new_arrivals_by_publication_timestamp(self):
        now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        self.client.get("/api/products/")  # applies the additive published_at migration for this legacy fixture
        self.database.client.execute("UPDATE products SET published_at=? WHERE id='product-1'",(now.isoformat().replace("+00:00","Z"),))
        ages={
            "age-9d23h":now-datetime.timedelta(days=9,hours=23),
            "age-10d":now-datetime.timedelta(days=10),
            "age-over-10d":now-datetime.timedelta(days=10,seconds=1),
        }
        for product_id,published_at in ages.items():
            self.database.client.execute("""INSERT INTO products
                (id,name,slug,description,category,price,currency,is_free,is_published,published_at)
                VALUES(?,?,?,?,?,999,'INR',0,1,?)""",
                (product_id,product_id,product_id,"", "Tools",published_at.isoformat().replace("+00:00","Z")))
        response=self.client.get("/api/products/")
        self.assertEqual(response.status_code,200,response.get_json())
        payload=response.get_json()["result"]
        arrivals={p["id"]:p for p in payload["new_arrivals"]}
        normal={p["id"]:p for p in payload["products"]}
        self.assertEqual(set(arrivals),{"product-1","age-9d23h"})
        self.assertEqual(set(normal),{"age-10d","age-over-10d"})
        self.assertEqual(set(arrivals)|set(normal),{"product-1","age-9d23h","age-10d","age-over-10d"})
        self.assertEqual(payload["count"],len(arrivals)+len(normal))
        self.assertEqual(arrivals["product-1"]["is_new_arrival"],True)
        self.assertEqual(normal["age-10d"]["is_new_arrival"],False)

    def test_unpublish_and_republish_starts_a_fresh_arrival_window(self):
        self.client.get("/api/products/")  # applies the migration on the legacy fixture
        earlier=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=20)).replace(microsecond=0)
        self.database.client.execute("UPDATE products SET published_at=? WHERE id='product-1'",(earlier.isoformat().replace("+00:00","Z"),))
        self.assertFalse(self.client.get("/api/products/product-1").get_json()["result"]["is_new_arrival"])
        self.assertEqual(self.client.patch("/api/admin/products/product-1",headers=self.bearer("admin"),json={"is_published":False}).status_code,200)
        self.assertEqual(self.client.patch("/api/admin/products/product-1",headers=self.bearer("admin"),json={"is_published":True}).status_code,200)
        republished=self.client.get("/api/products/product-1").get_json()["result"]
        self.assertTrue(republished["is_new_arrival"])
        saved=self.database.client.execute("SELECT published_at FROM products WHERE id='product-1'").rows[0][0]
        saved_at=datetime.datetime.fromisoformat(saved.replace("Z","+00:00"))
        if saved_at.tzinfo is None:
            saved_at=saved_at.replace(tzinfo=datetime.timezone.utc)
        self.assertGreaterEqual(saved_at,earlier)

    def test_catalog_and_detail_share_new_arrival_prices_for_members_and_campaigns(self):
        self.client.get("/api/memberships/plans")
        self.client.get("/api/products/")  # add published_at to the legacy fixture before setting it
        now=datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        self.database.client.execute("UPDATE products SET published_at=? WHERE id='product-1'",(now.isoformat().replace("+00:00","Z"),))
        start=(self.today + datetime.timedelta(days=1)).isoformat();end=(self.today + datetime.timedelta(days=3)).isoformat()
        self.save_schedule(self.campaign_payload(start,end))
        list_url="/api/products/"
        anonymous=self.client.get(list_url).get_json()["result"]
        arrival=anonymous["new_arrivals"][0]
        detail=self.client.get("/api/products/product-1").get_json()["result"]
        self.assertEqual((arrival["price"],arrival["festival_discount_amount"],arrival["membership_discount_amount"]),(699,300,0))
        self.assertEqual((arrival["price"],arrival["festival_discount_amount"],arrival["membership_discount_amount"]),(detail["price"],detail["festival_discount_amount"],detail["membership_discount_amount"]))
        expires=(now+datetime.timedelta(days=30)).isoformat().replace("+00:00","Z")
        self.database.client.execute("INSERT INTO membership_applications(membership_id,customer_id,plan_key,status,activated_at,expires_at) VALUES('CSM-PREMIUM','customer-1','premium','approved',?,?)",(now.isoformat().replace("+00:00","Z"),expires))
        member_payload=self.client.get(list_url,headers=self.bearer()).get_json()["result"]
        member_arrival=member_payload["new_arrivals"][0]
        member_detail=self.client.get("/api/products/product-1",headers=self.bearer()).get_json()["result"]
        self.assertEqual((member_arrival["price"],member_arrival["festival_discount_percent"],member_arrival["membership_discount_percent"],member_arrival["festival_discount_amount"],member_arrival["membership_discount_amount"]),(629,30,10,300,70))
        self.assertEqual((member_arrival["price"],member_arrival["festival_discount_amount"],member_arrival["membership_discount_amount"]),(member_detail["price"],member_detail["festival_discount_amount"],member_detail["membership_discount_amount"]))

    def test_pending_and_expired_memberships_do_not_receive_member_discount(self):
        self.client.get("/api/memberships/plans")
        self.database.client.execute("INSERT INTO membership_applications(membership_id,customer_id,plan_key,status) VALUES('CSM-PENDING','customer-1','premium','pending')")
        pending=self.client.get("/api/products/product-1",headers=self.bearer()).get_json()["result"]
        self.assertEqual((pending["price"],pending["membership_discount_percent"]),(999,0))
        self.database.client.execute("UPDATE membership_applications SET status='approved',activated_at='2020-01-01T00:00:00Z',expires_at='2000-01-01T00:00:00Z' WHERE membership_id='CSM-PENDING'")
        expired=self.client.get("/api/products/product-1",headers=self.bearer()).get_json()["result"]
        self.client.get("/api/memberships/current",headers=self.bearer())
        status=self.database.client.execute("SELECT status FROM membership_applications WHERE membership_id='CSM-PENDING'").rows[0][0]
        self.assertEqual((expired["price"],expired["membership_discount_percent"],status),(999,0,"expired"))

    def test_membership_rate_migration_keeps_existing_plan_settings(self):
        self.database.client.execute("CREATE TABLE membership_plans(plan_key TEXT PRIMARY KEY,name TEXT NOT NULL,price_paise INTEGER,duration_days INTEGER,benefits_json TEXT NOT NULL DEFAULT '[]',is_active INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        self.database.client.execute("INSERT INTO membership_plans(plan_key,name,price_paise,duration_days,benefits_json,is_active) VALUES('plus','Plus',50000,30,'[\"Priority support\"]',1)")
        memberships.ensure_tables(self.database.client)
        plus=self.database.client.execute("SELECT price_paise,duration_days,benefits_json,product_discount_percent FROM membership_plans WHERE plan_key='plus'").rows[0]
        premium=self.database.client.execute("SELECT product_discount_percent FROM membership_plans WHERE plan_key='premium'").rows[0][0]
        self.assertEqual(plus,(50000,30,'["Priority support"]',5))
        self.assertEqual(premium,10)
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
        demand=self.client.post("/api/community/demands/posts",headers=self.bearer(),json={"content":"Need a code product"})
        public_demands=self.client.get("/api/customer/demands").get_json()["result"]
        self.assertEqual(public_demands[0]["id"],demand.get_json()["result"]["id"])
        self.assertEqual(self.client.post("/api/community/discussions/posts",json={"content":"anonymous"}).status_code,401)
        self.assertEqual(self.client.post("/api/community/discussions/likes/post/missing",json={}).status_code,401)
        self.assertEqual(self.client.post("/api/community/discussions/posts/missing/replies",json={"content":"anonymous"}).status_code,401)
        self.assertEqual(self.client.get("/api/customer/support-demands").status_code,401)

    def test_public_reads_ignore_invalid_optional_jwt_but_writes_require_valid_customer(self):
        import jwt
        invalid_signature = patch.object(auth, "verify_token", side_effect=jwt.InvalidSignatureError("bad signature"))
        with invalid_signature:
            public = self.client.get("/api/customer/demands", headers={"Authorization": "Bearer invalid"})
            plans = self.client.get("/api/memberships/plans", headers={"Authorization": "Bearer invalid"})
        self.assertEqual(public.status_code, 200)
        self.assertEqual(plans.status_code, 200)
        self.assertNotIn("Signature mismatch", str(public.get_json()))
        self.assertEqual(self.client.get("/api/customer/support-demands", headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.assertEqual(self.client.post("/api/community/demands/posts", headers={"Authorization": "Bearer invalid"}, json={"content": "test"}).status_code, 401)
        self.assertEqual(self.client.post("/api/community/demands/likes/post/missing", headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.assertEqual(self.client.post("/api/memberships/applications", headers={"Authorization": "Bearer invalid"}, json={"plan_key": "basic"}).status_code, 401)

    def test_valid_customer_jwt_still_authorizes_protected_write(self):
        response = self.client.post("/api/community/demands/posts", headers=self.bearer(), json={"content": "A valid authenticated request"})
        self.assertEqual(response.status_code, 201, response.get_json())

    def test_real_valid_and_invalid_jwt_protected_route_behavior(self):
        import jwt
        from auth.jwt import verify_token as real_verify_token
        secret = "test-only-jwt-secret-long-enough-for-hs256"
        with patch.dict(os.environ, {"JWT_SECRET": secret}):
            valid = jwt.encode({"sub":"customer-1","role":"customer","exp":datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=5)},secret,algorithm="HS256")
            invalid = jwt.encode({"sub":"customer-1","role":"customer","exp":datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=5)},"different-test-secret-long-enough-for-hs256",algorithm="HS256")
            expired = jwt.encode({"sub":"customer-1","role":"customer","exp":datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=1)},secret,algorithm="HS256")
            with patch.object(auth,"verify_token",side_effect=real_verify_token):
                self.assertEqual(self.client.post("/api/community/demands/posts",headers={"Authorization":"Bearer "+valid},json={"content":"signed correctly"}).status_code,201)
                bad = self.client.post("/api/community/demands/posts",headers={"Authorization":"Bearer "+invalid},json={"content":"wrong signature"})
                old = self.client.post("/api/community/demands/posts",headers={"Authorization":"Bearer "+expired},json={"content":"expired token"})
        self.assertEqual(bad.status_code,401)
        self.assertEqual(old.status_code,401)
        self.assertNotIn("Signature mismatch",bad.get_json()["error"])

    def test_admin_order_search_is_exact_and_authorized(self):
        self.database.client.execute("INSERT INTO orders(id,user_id,status,subtotal,total,currency) VALUES('CSO-ABC123','customer-1','pending_cash',999,999,'INR')")
        self.database.client.execute("INSERT INTO order_items(id,order_id,product_id,quantity,unit_price,total_price) VALUES('item-1','CSO-ABC123','product-1',1,999,999)")
        response=self.client.get("/api/admin/orders/search?q=CSO-ABC123",headers=self.bearer("admin"))
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.get_json()["result"][0]["id"],"CSO-ABC123")
        self.assertEqual(len(response.get_json()["result"][0]["items"]),1)
        self.assertEqual(response.get_json()["result"][0]["items"][0]["original_unit_price"],999)
        self.assertEqual(self.client.get("/api/admin/orders/search?q=CSO-ABC123",headers=self.bearer()).status_code,403)

    def test_private_order_receipt_upload_and_admin_only_access(self):
        self.database.client.execute("INSERT INTO orders(id,user_id,status,subtotal,total,currency) VALUES('CSO-RECEIPT','customer-1','pending_cash',999,999,'INR')")
        with patch.object(object_storage,"upload",return_value="private/order-receipts/test.png"):
            response=self.client.post("/api/orders/CSO-RECEIPT/receipt",headers=self.bearer(),data={"transaction_reference":"UTR-987654","screenshot":(io.BytesIO(b"image"),"receipt.png","image/png")},content_type="multipart/form-data")
        self.assertEqual(response.status_code,201,response.get_json())
        self.assertEqual(self.client.post("/api/orders/CSO-RECEIPT/receipt",headers=self.bearer(),data={"transaction_reference":"UTR-NEW","screenshot":(io.BytesIO(b"image"),"receipt.png","image/png")},content_type="multipart/form-data").status_code,409)
        result=self.client.get("/api/admin/orders/search?q=CSO-RECEIPT",headers=self.bearer("admin")).get_json()["result"][0]
        self.assertEqual(result["payment_receipt"]["transaction_reference"],"UTR-987654")
        self.assertTrue(result["payment_receipt"]["has_screenshot"])
        self.assertEqual(self.client.get("/api/admin/orders/CSO-RECEIPT/receipt",headers=self.bearer()).status_code,403)
        with patch.object(object_storage,"private_url",return_value="https://storage.example/presigned"):
            url=self.client.get("/api/admin/orders/CSO-RECEIPT/receipt",headers=self.bearer("admin"))
        self.assertEqual(url.get_json()["result"]["url"],"https://storage.example/presigned")

    def test_membership_plans_ids_review_expiry_and_renewal(self):
        plans=self.client.get("/api/memberships/plans").get_json()["result"]
        self.assertEqual([p["plan_key"] for p in plans],["basic","plus","premium"])
        self.assertIsNone(next(p for p in plans if p["plan_key"]=="plus")["price_paise"])
        config=self.client.put("/api/admin/membership-plans/plus",headers=self.bearer("admin"),json={"name":"Plus","price_paise":50000,"duration_days":30,"benefits":["Priority support"]})
        self.assertEqual(config.status_code,200,config.get_json())
        def apply_paid():
            with patch.object(memberships,"upload",return_value="private/membership.png"):
                return self.client.post("/api/memberships/applications",headers=self.bearer(),data={"plan_key":"plus","transaction_reference":"UTR-123","screenshot":(io.BytesIO(b"receipt"),"receipt.png","image/png")},content_type="multipart/form-data")
        res=apply_paid();self.assertEqual(res.status_code,201,res.get_json())
        first=res.get_json()["result"]["membership_id"]
        self.assertTrue(first.startswith("CSM-"))
        self.assertEqual(self.client.post(f"/api/admin/membership-applications/{first}/approve",headers=self.bearer("admin"),json={}).status_code,200)
        approved=self.database.client.execute("SELECT expires_at FROM membership_applications WHERE membership_id=?",(first,)).rows[0][0]
        res=apply_paid();self.assertEqual(res.status_code,201,res.get_json())
        second=res.get_json()["result"]["membership_id"]
        self.assertNotEqual(first,second)
        self.assertEqual(self.client.post(f"/api/admin/membership-applications/{second}/approve",headers=self.bearer("admin"),json={}).status_code,200)
        renewed=self.database.client.execute("SELECT activated_at,expires_at FROM membership_applications WHERE membership_id=?",(second,)).rows[0]
        self.assertEqual(renewed[0],approved)
        self.assertEqual(self.client.post(f"/api/admin/membership-applications/{second}/approve",headers=self.bearer("admin"),json={}).status_code,409)
        self.database.client.execute("UPDATE membership_applications SET expires_at='2000-01-01T00:00:00Z' WHERE customer_id='customer-1' AND status='approved'")
        current=self.client.get("/api/memberships/current",headers=self.bearer()).get_json()["result"]
        self.assertEqual(current["plan_key"],"basic")
        self.assertEqual(self.database.client.execute("SELECT status FROM membership_applications WHERE membership_id=?",(second,)).rows[0][0],"expired")

    def test_campaign_create_activation_and_overlap_validation(self):
        start=self.today.isoformat();end=(self.today+datetime.timedelta(days=2)).isoformat()
        payload={"name":"Diwali","campaign_title":"The Light Festival","theme_color":"#a04010","start_date":start,"end_date":end,"enabled":True,"recurring_yearly":False}
        created=self.client.post("/api/admin/campaigns",headers=self.bearer("admin"),json=payload)
        self.assertEqual(created.status_code,201,created.get_json())
        active=self.client.get("/api/campaigns/active").get_json()["result"]
        self.assertEqual(active["campaign_title"],"The Light Festival")
        duplicate=self.client.post("/api/admin/campaigns",headers=self.bearer("admin"),json={**payload,"name":"Second Sale"})
        self.assertEqual(duplicate.status_code,409)
        self.assertEqual(self.client.get("/api/admin/campaigns",headers=self.bearer()).status_code,403)

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



