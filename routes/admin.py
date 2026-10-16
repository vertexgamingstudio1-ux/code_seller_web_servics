import os
import uuid
import bcrypt
from flask import Blueprint, jsonify, request
from db import get_connection
from auth.jwt import create_admin_token
from middleware.auth import require_admin
bp = Blueprint("admin", __name__)
def rows(sql, params=(), fields=()):
    with get_connection() as client:
        result = client.execute(sql, params)
    return [dict(zip(fields, row)) for row in result.rows]
def fail(message, status=500):
    return jsonify(success=False, error=message), status
@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))
    if not email or not password:
        return fail("Email and password are required", 400)
    try:
        users = rows(
            """SELECT id,email,password_hash,role,is_active
               FROM users WHERE email = ? COLLATE NOCASE LIMIT 1""",
            (email,), ("id","email","password_hash","role","is_active")
        )
        user = users[0] if users else None
        if not user or user["role"] != "admin" or not user["is_active"]:
            return fail("Invalid admin credentials", 401)
        if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return fail("Invalid admin credentials", 401)
        token = create_admin_token(user["id"], user["email"])
        return jsonify(success=True, token=token,
                       admin={"id":user["id"],"email":user["email"]})
    except Exception:
        return fail("Admin login is unavailable. Check database configuration.", 503)
@bp.get("/status")
@require_admin
def status():
    return jsonify(success=True, admin=True)
@bp.get("/dashboard")
@require_admin
def dashboard():
    try:
        result = rows("""SELECT
            (SELECT COUNT(*) FROM products) AS products,
            (SELECT COUNT(*) FROM orders) AS orders,
            (SELECT COUNT(*) FROM users WHERE role='customer') AS customers,
            (SELECT COUNT(*) FROM orders WHERE status='pending') AS pending_orders,
            (SELECT COALESCE(SUM(amount),0) FROM finance) AS finance_total
        """, fields=("products","orders","customers","pending_orders","finance_total"))
        return jsonify(success=True, result=result[0])
    except Exception:
        return fail("Could not load dashboard data. Verify the database schema.", 503)
@bp.get("/products")
@require_admin
def products():
    try:
        data = rows("""SELECT id,name,slug,description,category,price,currency,
            margin_percent,is_free,is_published,sales_count,created_at,updated_at
            FROM products ORDER BY created_at DESC""",
            fields=("id","name","slug","description","category","price","currency",
            "margin_percent","is_free","is_published","sales_count","created_at","updated_at"))
        for p in data:
            p["is_free"] = bool(p["is_free"])
            p["is_published"] = bool(p["is_published"])
        return jsonify(success=True, result=data)
    except Exception:
        return fail("Could not load products", 503)
@bp.post("/products")
@require_admin
def create_product():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("A JSON object is required", 400)
    name = str(data.get("name","")).strip()
    slug = str(data.get("slug","")).strip().lower()
    description = str(data.get("description","")).strip()
    category = str(data.get("category","")).strip() or None
    try:
        price = int(data.get("price",0))
    except (ValueError, TypeError):
        return fail("Price must be a whole number in INR", 400)
    if not name or not slug or price < 0:
        return fail("Valid name, slug and non-negative price are required", 400)
    import re
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        return fail("Slug must contain lowercase letters, numbers and hyphens", 400)
    free = bool(data.get("is_free",False))
    if free:
        price = 0
    product_id = str(uuid.uuid4())
    try:
        with get_connection() as client:
            client.execute("""INSERT INTO products
                (id,name,slug,description,category,price,currency,is_free,is_published)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (product_id,name,slug,description,category,price,"INR",int(free),0))
        return jsonify(success=True, id=product_id), 201
    except Exception:
        return fail("Could not create product. The slug may already exist.", 409)
@bp.patch("/products/<product_id>")
@require_admin
def update_product(product_id):
    data = request.get_json(silent=True) or {}
    allowed = {"is_published","name","description","category"}
    updates = {k:data[k] for k in allowed if k in data}
    if not updates:
        return fail("No supported fields supplied", 400)
    if "is_published" in updates:
        updates["is_published"] = int(bool(updates["is_published"]))
    if "name" in updates:
        updates["name"] = str(updates["name"]).strip()
        if not updates["name"]:
            return fail("Name cannot be empty", 400)
    sql = "UPDATE products SET " + ", ".join(k + " = ?" for k in updates) + ", updated_at=CURRENT_TIMESTAMP WHERE id = ?"
    try:
        with get_connection() as client:
            result = client.execute(sql, tuple(updates.values()) + (product_id,))
        return jsonify(success=True, updated=True)
    except Exception:
        return fail("Could not update product", 503)
@bp.get("/orders")
@require_admin
def orders():
    try:
        data = rows("""SELECT o.id,o.user_id,u.email,o.status,o.subtotal,o.total,
            o.currency,o.created_at,o.updated_at
            FROM orders o LEFT JOIN users u ON u.id=o.user_id
            ORDER BY o.created_at DESC LIMIT 500""",
            fields=("id","user_id","email","status","subtotal","total","currency","created_at","updated_at"))
        return jsonify(success=True, result=data)
    except Exception:
        return fail("Could not load orders", 503)
@bp.patch("/orders/<order_id>")
@require_admin
def update_order(order_id):
    data = request.get_json(silent=True) or {}
    status_value = str(data.get("status","")).strip().lower()
    if status_value not in {"pending","paid","processing","completed","cancelled","refunded","failed"}:
        return fail("Unsupported order status", 400)
    try:
        with get_connection() as client:
            client.execute("UPDATE orders SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                           (status_value,order_id))
        return jsonify(success=True, updated=True)
    except Exception:
        return fail("Could not update order", 503)
@bp.get("/customers")
@require_admin
def customers():
    try:
        data = rows("""SELECT id,email,phone,display_name,role,is_active,created_at
            FROM users WHERE role='customer' ORDER BY created_at DESC LIMIT 500""",
            fields=("id","email","phone","display_name","role","is_active","created_at"))
        return jsonify(success=True, result=data)
    except Exception:
        return fail("Could not load customers", 503)
@bp.get("/finance")
@require_admin
def finance():
    try:
        data = rows("""SELECT id,order_id,type,amount,currency,description,created_at
            FROM finance ORDER BY created_at DESC LIMIT 500""",
            fields=("id","order_id","type","amount","currency","description","created_at"))
        return jsonify(success=True, result=data)
    except Exception:
        return fail("Could not load finance", 503)
@bp.get("/refunds")
@require_admin
def refunds():
    try:
        data = rows("""SELECT id,order_id,payment_id,amount,currency,status,reason,created_at,updated_at
            FROM refunds ORDER BY created_at DESC LIMIT 500""",
            fields=("id","order_id","payment_id","amount","currency","status","reason","created_at","updated_at"))
        return jsonify(success=True, result=data)
    except Exception:
        return fail("Could not load refunds", 503)
@bp.get("/versions")
@require_admin
def versions():
    try:
        data = rows("""SELECT v.id,v.product_id,p.name AS product_name,v.version,
            v.changelog,v.single_file_path,v.package_file_path,v.is_active,v.created_at
            FROM product_versions v LEFT JOIN products p ON p.id=v.product_id
            ORDER BY v.created_at DESC LIMIT 500""",
            fields=("id","product_id","product_name","version","changelog","single_file_path",
            "package_file_path","is_active","created_at"))
        return jsonify(success=True, result=data)
    except Exception:
        return fail("Could not load versions", 503)
@bp.get("/downloads")
@require_admin
def downloads():
    try:
        data = rows("""SELECT d.id,d.user_id,u.email,d.product_id,p.name AS product_name,
            d.product_version_id,d.order_id,d.download_type,d.file_reference,d.created_at
            FROM downloads d LEFT JOIN users u ON u.id=d.user_id
            LEFT JOIN products p ON p.id=d.product_id
            ORDER BY d.created_at DESC LIMIT 500""",
            fields=("id","user_id","email","product_id","product_name","product_version_id",
            "order_id","download_type","file_reference","created_at"))
        return jsonify(success=True, result=data)
    except Exception:
        return fail("Could not load downloads", 503)
