import os
import uuid
import bcrypt
import re
import zipfile
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, jsonify, request
from db import get_connection
from auth.jwt import create_admin_token
from middleware.auth import require_admin
bp = Blueprint("admin", __name__)
FESTIVAL_CAMPAIGNS = (("holi", "Holi"), ("diwali", "Diwali"), ("navratri", "Navratri"), ("ganesh-chaturthi", "Ganesh Chaturthi"), ("new-year", "New Year"))

def ensure_festival_tables(client):
    client.execute("""CREATE TABLE IF NOT EXISTS festival_scheduler_settings (id INTEGER PRIMARY KEY CHECK (id=1), enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    client.execute("INSERT OR IGNORE INTO festival_scheduler_settings (id,enabled) VALUES (1,0)")
    client.execute("""CREATE TABLE IF NOT EXISTS festival_campaigns (slug TEXT PRIMARY KEY, name TEXT NOT NULL, reference_sale_date TEXT, enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    for slug,name in FESTIVAL_CAMPAIGNS:
        client.execute("INSERT OR IGNORE INTO festival_campaigns (slug,name) VALUES (?,?)",(slug,name))

def festival_payload(client):
    ensure_festival_tables(client)
    enabled=client.execute("SELECT enabled FROM festival_scheduler_settings WHERE id=1").rows[0][0]
    records=client.execute("SELECT slug,name,reference_sale_date,enabled FROM festival_campaigns ORDER BY rowid").rows
    today=datetime.now(ZoneInfo("Asia/Kolkata")).date(); campaigns=[]
    for slug,name,sale_date,campaign_enabled in records:
        start=date.fromisoformat(sale_date)-timedelta(days=1) if sale_date else None
        notification=None
        if start and campaign_enabled and enabled:
            if start==today: notification="Turn on your "+name+" Code Seller sale today."
            elif today<start<=today+timedelta(days=7): notification="Your "+name+" Code Seller sale starts "+start.isoformat()+"."
        campaigns.append({"slug":slug,"name":name,"reference_sale_date":sale_date,"campaign_start_date":start.isoformat() if start else None,"enabled":bool(campaign_enabled),"notification":notification})
    return {"enabled":bool(enabled),"campaigns":campaigns,"today":today.isoformat()}
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

@bp.get("/festival-scheduler")
@require_admin
def get_festival_scheduler():
    try:
        with get_connection() as client: result=festival_payload(client)
        return jsonify(success=True,result=result)
    except Exception:
        return fail("Could not load festival schedules",503)

@bp.put("/festival-scheduler")
@require_admin
def save_festival_scheduler():
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or not isinstance(data.get("campaigns"),list): return fail("Scheduler settings and campaign list are required",400)
    submitted={item.get("slug"):item for item in data["campaigns"] if isinstance(item,dict)}
    if set(submitted)!={slug for slug,_ in FESTIVAL_CAMPAIGNS}: return fail("All five festival campaigns must be included",400)
    normalized=[]
    try:
        for slug,_ in FESTIVAL_CAMPAIGNS:
            item=submitted[slug]; raw_date=item.get("reference_sale_date") or None
            parsed=date.fromisoformat(raw_date) if raw_date else None
            if raw_date and parsed.isoformat()!=raw_date: raise ValueError
            normalized.append((slug,raw_date,int(bool(item.get("enabled",False)))))
    except (TypeError,ValueError): return fail("Enter valid sale dates in YYYY-MM-DD format",400)
    try:
        with get_connection() as client:
            ensure_festival_tables(client)
            client.execute("UPDATE festival_scheduler_settings SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",(int(bool(data.get("enabled",False))),))
            for slug,sale_date,campaign_enabled in normalized:
                client.execute("UPDATE festival_campaigns SET reference_sale_date=?,enabled=?,updated_at=CURRENT_TIMESTAMP WHERE slug=?",(sale_date,campaign_enabled,slug))
            result=festival_payload(client)
        return jsonify(success=True,result=result)
    except Exception: return fail("Could not save festival schedules to the database",503)

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

@bp.post("/products/with-code")
@require_admin
def create_product_with_code():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return fail("A JSON object is required", 400)
    name = str(data.get("name", "")).strip()
    slug = str(data.get("slug", "")).strip().lower()
    description = str(data.get("description", "")).strip()
    category = str(data.get("category", "")).strip() or None
    version = str(data.get("version", "1.0.0")).strip()
    kind = str(data.get("product_type", "")).strip().lower()
    files = data.get("files")
    if not name or not slug or len(name) > 160 or len(slug) > 180:
        return fail("Product name and a valid slug are required", 400)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        return fail("Slug must contain lowercase letters, numbers and hyphens", 400)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return fail("Version must use the format 1.0.0", 400)
    if kind not in {"single", "package"} or not isinstance(files, list) or not files:
        return fail("A single file or whole package with source files is required", 400)
    if kind == "single" and len(files) != 1:
        return fail("Single File products must contain exactly one file", 400)
    if len(files) > 100:
        return fail("A package can contain up to 100 files", 400)
    total_bytes = 0
    cleaned = []
    allowed = {"py", "js", "ts", "html", "css", "json", "txt", "md", "java", "c", "cpp", "h", "hpp", "cs", "go", "rs", "php", "sql", "sh", "yaml", "yml", "xml", "toml", "jsx", "tsx", "vue", "svelte", "svg", "gitignore"}
    for entry in files:
        if not isinstance(entry, dict):
            return fail("Each source file must include a name and content", 400)
        raw_name = str(entry.get("name", "")).replace("\\", "/").strip()
        parts = raw_name.split("/")
        if not raw_name or raw_name.startswith("/") or any(p in {"", ".", ".."} for p in parts):
            return fail("Source file paths must be relative and cannot contain '..'", 400)
        filename = secure_filename(parts[-1])
        if not filename or ("." in filename and filename.rsplit(".", 1)[-1].lower() not in allowed):
            return fail("A source file uses an unsupported file type", 400)
        safe_name = "/".join(parts[:-1] + [filename])
        content = entry.get("content", "")
        if not isinstance(content, str):
            return fail("Source file content must be text", 400)
        encoded = content.encode("utf-8")
        total_bytes += len(encoded)
        if total_bytes > 5 * 1024 * 1024:
            return fail("Source files must total 5 MB or less", 413)
        cleaned.append((safe_name, encoded))
    try:
        price = int(data.get("price", 0))
    except (TypeError, ValueError):
        return fail("Price must be a whole number in INR", 400)
    if price < 0:
        return fail("Price cannot be negative", 400)
    is_free = bool(data.get("is_free", False))
    if is_free:
        price = 0
    is_published = bool(data.get("is_published", False))
    product_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    upload_root = Path(__file__).resolve().parent.parent / "uploads"
    target_dir = upload_root / product_id / version
    target_dir.mkdir(parents=True, exist_ok=True)
    single_path = package_path = None
    try:
        if kind == "single":
            filename = secure_filename(cleaned[0][0].rsplit("/", 1)[-1])
            target = target_dir / filename
            target.write_bytes(cleaned[0][1])
            single_path = str(target.relative_to(upload_root))
        else:
            target = target_dir / (secure_filename(slug) + ".zip")
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_name, content in cleaned:
                    archive.writestr(file_name, content)
            package_path = str(target.relative_to(upload_root))
        with get_connection() as client:
            client.execute("""INSERT INTO products
                (id,name,slug,description,category,price,currency,is_free,is_published)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (product_id,name,slug,description,category,price,"INR",int(is_free),int(is_published)))
            client.execute("""INSERT INTO product_versions
                (id,product_id,version,changelog,single_file_path,package_file_path,is_active)
                VALUES (?,?,?,?,?,?,1)""",
                (version_id,product_id,version,"Initial release",single_path,package_path))
        return jsonify(success=True, result={"id":product_id,"version_id":version_id,
            "slug":slug,"version":version,"product_type":kind,"source_file_count":len(cleaned)}), 201
    except Exception:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        return fail("Could not save the product. The slug may already exist.", 409)

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
