import hashlib
import hmac
import json
import os
import uuid
from urllib.parse import urljoin

import requests
from db import get_connection
from services.product_service import ProductService


def ensure_payment_settings_schema(client):
    client.execute("CREATE TABLE IF NOT EXISTS payment_settings (id INTEGER PRIMARY KEY CHECK (id=1), upi_id TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    client.execute("INSERT OR IGNORE INTO payment_settings(id,upi_id) VALUES (1,'')")


def payment_options():
    with get_connection() as c:
        ensure_payment_settings_schema(c)
        rows = c.execute("SELECT upi_id FROM payment_settings WHERE id=1").rows
    return {"upi_id": rows[0][0] if rows else ""}


def ensure_payment_schema(client):
    """Add payment metadata to existing Turso databases without rewriting history."""
    columns = {r[1] for r in client.execute("PRAGMA table_info(payments)").rows}
    for name, definition in (("provider_order_id", "TEXT"), ("signature", "TEXT")):
        if name not in columns:
            client.execute(f"ALTER TABLE payments ADD COLUMN {name} {definition}")
    duplicates = client.execute("SELECT 1 FROM payments WHERE provider_payment_id IS NOT NULL GROUP BY provider,provider_payment_id HAVING COUNT(*)>1 LIMIT 1").rows
    if not duplicates:
        client.execute("CREATE UNIQUE INDEX IF NOT EXISTS payments_provider_payment_id_uq ON payments(provider,provider_payment_id) WHERE provider_payment_id IS NOT NULL")
    client.execute("CREATE UNIQUE INDEX IF NOT EXISTS payments_provider_order_id_uq ON payments(provider,provider_order_id) WHERE provider_order_id IS NOT NULL")


def _priced_items(items):
    if not isinstance(items, list) or not items or len(items) > 100:
        raise ValueError("Provide between 1 and 100 cart items")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid cart item")
        product = ProductService.get_product(str(item.get("id", "")))
        try:
            quantity = int(item.get("quantity", 1))
        except (ValueError, TypeError):
            raise ValueError("Invalid quantity") from None
        if not product or quantity < 1 or quantity > 99:
            raise ValueError("A product or quantity is invalid")
        result.append((product, quantity))
    return result


def quote(items):
    rows = _priced_items(items)
    lines = [{"id": p["id"], "name": p["name"], "quantity": q,
              "unit_price": p["price"], "total": p["price"] * q,
              "discount_percent": p.get("festival_discount_percent", 0)} for p, q in rows]
    return {"items": lines, "total": sum(x["total"] for x in lines), "currency": "INR"}


def _create_order(user_id, items, status):
    rows = _priced_items(items)
    subtotal = sum(p["price"] * q for p, q in rows)
    order_id = "CSO-" + uuid.uuid4().hex[:16].upper()
    try:
        with get_connection() as c:
            c.execute("INSERT INTO orders(id,user_id,status,subtotal,total,currency) VALUES(?,?,?,?,?,'INR')", (order_id, user_id, status, subtotal, subtotal))
            for product, quantity in rows:
                versions=c.execute("SELECT id FROM product_versions WHERE product_id=? AND is_active=1 ORDER BY created_at DESC LIMIT 1",(product["id"],)).rows
                version_id=versions[0][0] if versions else None
                c.execute("INSERT INTO order_items(id,order_id,product_id,product_version_id,quantity,unit_price,total_price) VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), order_id, product["id"], version_id, quantity, product["price"], product["price"] * quantity))
    except Exception as exc:
        raise RuntimeError("Could not save the order") from exc
    return order_id


def create_order(user_id, items):
    return _create_order(user_id, items, "pending")


def create_cash_order(user_id, items):
    return _create_order(user_id, items, "pending_cash")


def ensure_cash_approval_schema(client):
    client.execute("""CREATE TABLE IF NOT EXISTS cash_approvals (
        order_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        amount INTEGER NOT NULL,
        currency TEXT NOT NULL DEFAULT 'INR',
        approved_by TEXT NOT NULL,
        approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


def _razorpay_request(method, path, payload=None):
    key, secret = os.getenv("RAZORPAY_KEY_ID", "").strip(), os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    mode = os.getenv("RAZORPAY_MODE", "test").lower()
    if mode != "test" or not key.startswith("rzp_test_"):
        raise RuntimeError("Only Razorpay test mode is supported by this setup")
    if os.getenv("PAYMENTS_ENABLED", "false").lower() != "true" or not key or not secret:
        raise RuntimeError("Razorpay payments are not enabled")
    base = os.getenv("RAZORPAY_API_BASE", "https://api.razorpay.com").rstrip("/") + "/"
    response = requests.request(method, urljoin(base, path.lstrip("/")), json=payload, auth=(key, secret), timeout=15)
    response.raise_for_status()
    return response.json()


def start_payment(order_id, user_id):
    with get_connection() as c:
        ensure_payment_schema(c)
        order = c.execute("SELECT id,total,currency,status FROM orders WHERE id=? AND user_id=?", (order_id, user_id)).rows
        if not order:
            raise LookupError("Order not found")
        oid, amount, currency, status = order[0]
        if status != "pending":
            raise ValueError("Only pending orders can be paid")
        existing = c.execute("SELECT provider_order_id FROM payments WHERE order_id=? AND status='created' ORDER BY created_at DESC LIMIT 1", (order_id,)).rows
        if existing:
            return {"order_id": order_id, "razorpay_order_id": existing[0][0], "amount": amount, "currency": currency, "key_id": os.getenv("RAZORPAY_KEY_ID", "")}
    remote = _razorpay_request("POST", "/v1/orders", {"amount": amount, "currency": currency, "receipt": order_id, "notes": {"internal_order_id": order_id}})
    payment_id = str(uuid.uuid4())
    with get_connection() as c:
        ensure_payment_schema(c)
        c.execute("INSERT INTO payments(id,order_id,provider,provider_order_id,status,amount,currency) VALUES(?,?,'razorpay',?,'created',?,?)", (payment_id, order_id, remote["id"], amount, currency))
    return {"order_id": order_id, "razorpay_order_id": remote["id"], "amount": amount, "currency": currency, "key_id": os.getenv("RAZORPAY_KEY_ID", "")}


def verify_checkout(user_id, order_id, razorpay_order_id, payment_id, signature):
    secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    expected = hmac.new(secret.encode(), f"{razorpay_order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, str(signature)):
        raise ValueError("Payment signature is invalid")
    remote_payment = _razorpay_request("GET", f"/v1/payments/{payment_id}")
    if remote_payment.get("status") != "captured":
        raise ValueError("Razorpay has not confirmed the payment as captured")
    if remote_payment.get("order_id") != razorpay_order_id:
        raise ValueError("Payment is linked to a different Razorpay order")
    with get_connection() as c:
        ensure_payment_schema(c)
        rows = c.execute("SELECT o.total,o.currency,p.amount,p.currency,p.provider_order_id,p.status FROM orders o JOIN payments p ON p.order_id=o.id WHERE o.id=? AND o.user_id=? AND p.provider='razorpay' AND p.provider_order_id=?", (order_id, user_id, razorpay_order_id)).rows
        if not rows:
            raise ValueError("Payment does not match this customer order")
        total, currency, amount, pcurrency, _, status = rows[0]
        if total != amount or currency != pcurrency or currency != "INR":
            raise ValueError("Payment amount or currency does not match the order")
        if remote_payment.get("amount") != total or remote_payment.get("currency") != currency:
            raise ValueError("Captured payment amount or currency does not match the order")
        if status == "captured":
            return
        c.execute("UPDATE payments SET provider_payment_id=?,signature=?,status='captured',paid_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE order_id=? AND provider_order_id=?", (payment_id, signature, order_id, razorpay_order_id))
        c.execute("UPDATE orders SET status='paid',updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (order_id, user_id))
        c.execute("UPDATE products SET sales_count=sales_count+(SELECT COALESCE(SUM(quantity),0) FROM order_items WHERE order_id=?) WHERE id IN (SELECT product_id FROM order_items WHERE order_id=?)", (order_id, order_id))


def handle_webhook(raw_body, signature):
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, str(signature or "")):
        raise ValueError("Webhook signature is invalid")
    event = json.loads(raw_body.decode("utf-8"))
    if event.get("event") not in ("payment.captured", "order.paid"):
        return "ignored"
    entity = (event.get("payload", {}).get("payment", {}).get("entity") or event.get("payload", {}).get("order", {}).get("entity") or {})
    order_id, remote_id = entity.get("order_id"), entity.get("id")
    if event.get("event") == "order.paid":
        payment = (event.get("payload", {}).get("payment", {}).get("entity") or {})
        order_id, remote_id = payment.get("order_id"), payment.get("id")
        entity = payment
    if not order_id or not remote_id or entity.get("currency") != "INR":
        raise ValueError("Webhook payment details are incomplete")
    with get_connection() as c:
        ensure_payment_schema(c)
        rows = c.execute("SELECT p.id,p.order_id,p.amount,p.currency,o.total,o.currency,p.status FROM payments p JOIN orders o ON o.id=p.order_id WHERE p.provider='razorpay' AND p.provider_order_id=?", (order_id,)).rows
        if not rows:
            raise ValueError("Webhook does not match a known order")
        pid, internal_order, amount, currency, total, order_currency, status = rows[0]
        if int(entity.get("amount", -1)) != amount or amount != total or currency != "INR" or order_currency != "INR":
            raise ValueError("Webhook amount or currency does not match the order")
        dupe = c.execute("SELECT id FROM payments WHERE provider='razorpay' AND provider_payment_id=?", (remote_id,)).rows
        if status == "captured" or dupe:
            return "duplicate"
        c.execute("UPDATE payments SET provider_payment_id=?,status='captured',paid_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (remote_id, pid))
        c.execute("UPDATE orders SET status='paid',updated_at=CURRENT_TIMESTAMP WHERE id=?", (internal_order,))
        c.execute("UPDATE products SET sales_count=sales_count+(SELECT COALESCE(SUM(quantity),0) FROM order_items WHERE order_id=?) WHERE id IN (SELECT product_id FROM order_items WHERE order_id=?)", (internal_order, internal_order))
    return "captured"


def customer_orders(user_id):
    with get_connection() as c:
        orders = c.execute("SELECT id,user_id,status,subtotal,total,currency,created_at,updated_at FROM orders WHERE user_id=? ORDER BY created_at DESC", (user_id,)).rows
        result=[]
        for row in orders:
            data=dict(zip(("id","customer_id","status","subtotal","total","currency","created_at","updated_at"),row))
            data["items"]=[dict(zip(("product_id","name","quantity","unit_price","total_price"),item)) for item in c.execute("SELECT i.product_id,p.name,i.quantity,i.unit_price,i.total_price FROM order_items i JOIN products p ON p.id=i.product_id WHERE i.order_id=?", (data["id"],)).rows]
            data["payments"]=[dict(zip(("provider","status","amount","currency","paid_at"),p)) for p in c.execute("SELECT provider,status,amount,currency,paid_at FROM payments WHERE order_id=? ORDER BY created_at",(data["id"],)).rows]
            try:
                approval=c.execute("SELECT approved_at FROM cash_approvals WHERE order_id=?",(data["id"],)).rows
                data["cash_approved_at"]=approval[0][0] if approval else None
            except Exception:
                data["cash_approved_at"]=None
            result.append(data)
    return result
