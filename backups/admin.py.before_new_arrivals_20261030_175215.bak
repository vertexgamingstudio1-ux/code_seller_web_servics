import os
import uuid
import bcrypt
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from werkzeug.utils import secure_filename
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

@bp.get("/payment-settings")
@require_admin
def get_payment_settings():
    try:
        from services.order_service import payment_options
        return jsonify(success=True, result=payment_options())
    except Exception:
        return fail("Could not load payment settings", 503)

@bp.put("/payment-settings")
@require_admin
def save_payment_settings():
    data = request.get_json(silent=True) or {}
    upi_id = str(data.get("upi_id", "")).strip()
    if len(upi_id) > 120 or (upi_id and not re.fullmatch(r"[A-Za-z0-9._-]{2,100}@[A-Za-z0-9.-]{2,30}", upi_id)):
        return fail("Enter a valid UPI ID", 400)
    try:
        from services.order_service import ensure_payment_settings_schema
        with get_connection() as client:
            ensure_payment_settings_schema(client)
            client.execute("UPDATE payment_settings SET upi_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=1", (upi_id,))
        return jsonify(success=True, result={"upi_id": upi_id})
    except Exception:
        return fail("Could not save payment settings", 503)
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
        from services.festival_service import scheduler_payload
        with get_connection() as client: result=scheduler_payload(client)
        return jsonify(success=True,result=result)
    except Exception:
        return fail("Could not load festival schedules",503)

@bp.put("/festival-scheduler")
@require_admin
def save_festival_scheduler():
    from services.festival_service import CAMPAIGNS, scheduler_payload, ensure_festival_tables
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or not isinstance(data.get("campaigns"),list): return fail("Scheduler settings and campaign list are required",400)
    submitted={item.get("slug"):item for item in data["campaigns"] if isinstance(item,dict)}
    if set(submitted)!={slug for slug,_ in CAMPAIGNS}: return fail("All five festival campaigns must be included",400)
    normalized=[]
    try:
        for slug,_ in CAMPAIGNS:
            item=submitted[slug]
            raw_start=item.get("reference_sale_start",item.get("reference_sale_date")) or None
            raw_end=item.get("campaign_end_date") or None
            sale_start=date.fromisoformat(raw_start) if raw_start else None
            end=date.fromisoformat(raw_end) if raw_end else None
            if raw_start and sale_start.isoformat()!=raw_start: raise ValueError
            if raw_end and end.isoformat()!=raw_end: raise ValueError
            if sale_start and end and end < sale_start-timedelta(days=1): raise ValueError
            normalized.append((raw_start,raw_end,int(bool(item.get("enabled",False))),slug))
    except (TypeError,ValueError): return fail("Enter valid dates and ensure the campaign end date follows its start",400)
    try:
        with get_connection() as client:
            ensure_festival_tables(client)
            from routes.campaigns import ensure_campaign_table, _dates
            ensure_campaign_table(client)
            if bool(data.get("enabled",False)):
                for raw_start,raw_end,campaign_enabled,slug in normalized:
                    if not campaign_enabled or not raw_start or not raw_end:continue
                    proposed_start=date.fromisoformat(raw_start)-timedelta(days=1);proposed_end=date.fromisoformat(raw_end)
                    for custom in client.execute("SELECT slug,name,start_date,end_date,recurring_yearly,enabled,archived FROM event_campaigns WHERE enabled=1 AND archived=0").rows:
                        item={"slug":custom[0],"name":custom[1],"start_date":custom[2],"end_date":custom[3],"recurring_yearly":bool(custom[4])}
                        custom_start,custom_end=_dates(item,date.today())
                        if proposed_start<=custom_end and custom_start<=proposed_end:
                            return fail("Festival dates overlap with the active "+custom[1]+" campaign",409)
            client.execute("UPDATE festival_scheduler_settings SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",(int(bool(data.get("enabled",False))),))
            for raw_start,raw_end,campaign_enabled,slug in normalized:
                client.execute("UPDATE festival_campaigns SET reference_sale_date=?,campaign_end_date=?,enabled=?,updated_at=CURRENT_TIMESTAMP WHERE slug=?",(raw_start,raw_end,campaign_enabled,slug))
            result=scheduler_payload(client)
        return jsonify(success=True,result=result)
    except Exception: return fail("Could not save festival schedules to the database",503)

@bp.get("/demands")
@require_admin
def list_demands():
    try:
        from routes.customer import ensure_demand_tables
        with get_connection() as client: ensure_demand_tables(client)
        result=rows("""SELECT t.id,t.subject,t.status,t.created_at,t.updated_at,u.email AS customer_email,
          (SELECT message FROM demand_messages m WHERE m.thread_id=t.id ORDER BY m.created_at DESC LIMIT 1) AS last_message,
          (SELECT COUNT(*) FROM demand_messages m WHERE m.thread_id=t.id) AS message_count
          FROM demand_threads t JOIN users u ON u.id=t.user_id ORDER BY t.updated_at DESC""",
          fields=("id","subject","status","created_at","updated_at","customer_email","last_message","message_count"))
        return jsonify(success=True,result=result)
    except Exception: return fail("Could not load Demand conversations",503)

@bp.get("/demands/<thread_id>/messages")
@require_admin
def get_demand_messages(thread_id):
    try:
        messages=rows("SELECT id,thread_id,sender_role,message,created_at FROM demand_messages WHERE thread_id=? ORDER BY created_at,rowid",(thread_id,),("id","thread_id","sender_role","message","created_at"))
        return jsonify(success=True,result=messages)
    except Exception: return fail("Could not load Demand messages",503)

@bp.post("/demands/<thread_id>/messages")
@require_admin
def reply_to_demand(thread_id):
    data=request.get_json(silent=True) or {}; message=str(data.get("message","")).strip()
    if not message or len(message)>4000: return fail("Message must contain 1 to 4000 characters",400)
    try:
        with get_connection() as client:
            found=client.execute("SELECT id FROM demand_threads WHERE id=?",(thread_id,)).rows
            if not found: return fail("Demand conversation not found",404)
            client.execute("INSERT INTO demand_messages (id,thread_id,user_id,sender_role,message) VALUES (?,?,?,?,?)",(str(uuid.uuid4()),thread_id,request.auth.get("sub"),"admin",message))
            client.execute("UPDATE demand_threads SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(thread_id,))
        return jsonify(success=True),201
    except Exception: return fail("Could not send reply",503)

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
    try:
        with get_connection() as client:
            from services.product_service import _new_product_id
            product_id = _new_product_id(client)
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
    from services.product_service import _new_product_id
    version_id = str(uuid.uuid4())
    try:
        with get_connection() as client:
            product_id = _new_product_id(client)
    except Exception:
        return fail("Could not allocate a product ID", 503)
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
@bp.delete("/products/<product_id>")
@require_admin
def delete_product(product_id):
    """Delete a product only when it has no customer/order/download history."""
    try:
        with get_connection() as client:
            product = client.execute(
                "SELECT id FROM products WHERE id = ? LIMIT 1", (product_id,)
            ).rows
            if not product:
                return fail("Product not found", 404)

            # Retain all order and download history, including version references.
            history = client.execute(
                """SELECT 1 FROM order_items
                   WHERE product_id = ? OR product_version_id IN
                     (SELECT id FROM product_versions WHERE product_id = ?)
                   UNION ALL
                   SELECT 1 FROM downloads
                   WHERE product_id = ? OR product_version_id IN
                     (SELECT id FROM product_versions WHERE product_id = ?)
                   LIMIT 1""",
                (product_id, product_id, product_id, product_id),
            ).rows
            if history:
                return fail(
                    "This product has order or download history and cannot be deleted", 409
                )

            # The schema has no cascade: remove only unreferenced versions and product.
            client.execute("DELETE FROM product_versions WHERE product_id = ?", (product_id,))
            client.execute("DELETE FROM products WHERE id = ?", (product_id,))
        return jsonify(success=True, deleted=True, id=product_id)
    except Exception:
        return fail("Could not delete product", 503)
@bp.get("/orders")
@require_admin
def orders():
    try:
        from services.order_service import ensure_cash_approval_schema
        with get_connection() as client:
            ensure_cash_approval_schema(client)
            order_rows = client.execute("""
                SELECT o.id,o.user_id,u.email,o.status,o.subtotal,o.total,
                       o.currency,o.created_at,o.updated_at
                FROM orders o
                LEFT JOIN users u ON u.id=o.user_id
                ORDER BY o.created_at DESC LIMIT 500
            """).rows
            data = [
                dict(zip(
                    ("id","user_id","email","status","subtotal","total",
                     "currency","created_at","updated_at"), row
                ))
                for row in order_rows
            ]
            payment_rows = client.execute("""
                SELECT id,order_id,provider,provider_payment_id,status,
                       amount,currency,paid_at,created_at
                FROM payments ORDER BY created_at
            """).rows
            approval_rows = client.execute("""
                SELECT order_id,customer_id,amount,currency,approved_by,approved_at
                FROM cash_approvals
            """).rows
        payments_by_order = {}
        for row in payment_rows:
            payment = dict(zip(
                ("id","order_id","provider","provider_payment_id","status",
                 "amount","currency","paid_at","created_at"), row
            ))
            payments_by_order.setdefault(payment["order_id"], []).append(payment)
        approvals_by_order = {}
        for row in approval_rows:
            approval = dict(zip(
                ("order_id","customer_id","amount","currency","approved_by",
                 "approved_at"), row
            ))
            approvals_by_order.setdefault(approval["order_id"], []).append(approval)
        for order in data:
            approvals = approvals_by_order.get(order["id"], [])
            order["payments"] = payments_by_order.get(order["id"], [])
            order["cash_approval"] = approvals[0] if approvals else None
            order["can_confirm_cash"] = (
                order["status"] == "pending_cash" and not approvals
            )
        return jsonify(success=True, result=data)
    except Exception:
        import traceback
        traceback.print_exc()
        return fail("Could not load orders", 503)
@bp.post("/orders/<order_id>/confirm-cash")
@require_admin
def confirm_cash_received(order_id):
    try:
        from services.order_service import ensure_cash_approval_schema
        with get_connection() as client:
            ensure_cash_approval_schema(client)
            order=client.execute("SELECT user_id,total,currency,status FROM orders WHERE id=?",(order_id,)).rows
            if not order:return fail("Order not found",404)
            customer_id,amount,currency,status=order[0]
            if status!="pending_cash":return fail("Only pending cash orders can be approved",409)
            existing=client.execute("SELECT 1 FROM cash_approvals WHERE order_id=?",(order_id,)).rows
            if existing:return fail("Cash receipt was already approved",409)
            client.execute("INSERT INTO cash_approvals(order_id,customer_id,amount,currency,approved_by) VALUES(?,?,?,?,?)",
                           (order_id,customer_id,amount,currency,request.auth["sub"]))
            client.execute("UPDATE orders SET status='paid',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending_cash'",(order_id,))
            approval=client.execute("SELECT approved_at FROM cash_approvals WHERE order_id=?",(order_id,)).rows[0][0]
        return jsonify(success=True,result={"order_id":order_id,"customer_id":customer_id,"amount":amount,
            "currency":currency,"status":"paid","approved_by":request.auth["sub"],"approved_at":approval})
    except Exception:
        try:
            if rows("SELECT 1 FROM cash_approvals WHERE order_id=?",(order_id,)):
                return fail("Cash receipt was already approved",409)
        except Exception:
            pass
        return fail("Could not confirm cash receipt",503)
@bp.patch("/orders/<order_id>")
@require_admin
def update_order(order_id):
    data = request.get_json(silent=True) or {}
    status_value = str(data.get("status","")).strip().lower()
    if status_value not in {"pending","paid","processing","completed","cancelled","refunded","failed"}:
        return fail("Unsupported order status", 400)
    try:
        with get_connection() as client:
            current=client.execute("SELECT status FROM orders WHERE id=?",(order_id,)).rows
            if not current:return fail("Order not found",404)
            if status_value=="paid" and current[0][0]!="paid":
                return fail("An order can be marked paid only after verified Razorpay confirmation",409)
            if status_value in {"processing","completed"} and current[0][0] not in {"paid","processing","completed"}:
                return fail("Only confirmed paid orders can be fulfilled",409)
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

@bp.get("/payments")
@require_admin
def payments():
    try:
        from services.order_service import ensure_payment_schema
        with get_connection() as client: ensure_payment_schema(client)
        data=rows("""SELECT p.id,p.order_id,o.user_id,u.email,p.provider,p.provider_order_id,
            p.provider_payment_id,p.status,p.amount,p.currency,p.paid_at,p.created_at
            FROM payments p JOIN orders o ON o.id=p.order_id LEFT JOIN users u ON u.id=o.user_id
            ORDER BY p.created_at DESC LIMIT 500""",
            fields=("id","order_id","customer_id","email","provider","provider_order_id","provider_payment_id","status","amount","currency","paid_at","created_at"))
        return jsonify(success=True,result=data)
    except Exception:return fail("Could not load payments",503)

@bp.get("/orders/search")
@require_admin
def search_orders():
    """Exact Order ID or Customer ID search for the existing admin order screen."""
    query = str(request.args.get("q", "")).strip()
    if not query or len(query) > 128:
        return fail("Enter an Order ID or Customer ID", 400)
    try:
        from services.order_service import ensure_order_pricing_schema
        with get_connection() as client:
            ensure_order_pricing_schema(client)
            client.execute("""CREATE TABLE IF NOT EXISTS cash_payment_receipts (
                order_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,transaction_reference TEXT NOT NULL,
                screenshot_key TEXT NOT NULL,uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        found = rows("""SELECT o.id,o.user_id,u.display_name,u.email,u.phone,o.status,
            o.subtotal,o.total,o.currency,o.created_at,o.updated_at
            FROM orders o JOIN users u ON u.id=o.user_id
            WHERE o.id=? OR o.user_id=? ORDER BY o.created_at DESC LIMIT 50""",
            (query, query), ("id","customer_id","display_name","email","phone","status",
            "subtotal","total","currency","created_at","updated_at"))
        result=[]
        for order in found:
            order["items"] = rows("""SELECT i.product_id,p.name,i.quantity,i.unit_price,i.total_price,
                    i.original_unit_price,i.festival_discount_percent,i.membership_discount_percent,
                    i.festival_discount_amount,i.membership_discount_amount
                FROM order_items i LEFT JOIN products p ON p.id=i.product_id WHERE i.order_id=?""",
                (order["id"],),("product_id","name","quantity","unit_price","total_price","original_unit_price","festival_discount_percent","membership_discount_percent","festival_discount_amount","membership_discount_amount"))
            order["payments"] = rows("""SELECT provider,status,amount,currency,provider_payment_id,paid_at,created_at
                FROM payments WHERE order_id=? ORDER BY created_at""",(order["id"],),
                ("provider","status","amount","currency","transaction_reference","paid_at","created_at"))
            approvals = rows("SELECT approved_by,approved_at FROM cash_approvals WHERE order_id=?",
                (order["id"],),("approved_by","approved_at"))
            order["cash_approval"] = approvals[0] if approvals else None
            result.append(order)
            receipt=rows("SELECT transaction_reference,uploaded_at FROM cash_payment_receipts WHERE order_id=?",(order["id"],),("transaction_reference","uploaded_at"))
            if receipt:
                order["payment_receipt"]={"transaction_reference":receipt[0]["transaction_reference"],"uploaded_at":receipt[0]["uploaded_at"],"has_screenshot":True}
            else:order["payment_receipt"]=None
        return jsonify(success=True,result=result)
    except Exception:
        return fail("Could not search orders",503)

@bp.get("/orders/<order_id>/receipt")
@require_admin
def order_receipt(order_id):
    try:
        from services.object_storage import private_url
        with get_connection() as client:
            client.execute("""CREATE TABLE IF NOT EXISTS cash_payment_receipts (
                order_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,transaction_reference TEXT NOT NULL,
                screenshot_key TEXT NOT NULL,uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        receipt=rows("SELECT screenshot_key FROM cash_payment_receipts WHERE order_id=?",(order_id,),("screenshot_key",))
        if not receipt:return fail("Payment screenshot not found",404)
        return jsonify(success=True,result={"url":private_url(receipt[0]["screenshot_key"],expires=300),"expires_in":300})
    except Exception:return fail("Could not open payment screenshot",503)

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
