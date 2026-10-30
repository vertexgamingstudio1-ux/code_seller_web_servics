"""Configurable membership plans and application lifecycle."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from db import get_connection
from middleware.auth import require_customer
from services.object_storage import StorageNotConfigured, upload, private_url

bp = Blueprint("memberships", __name__)
PLAN_DEFAULTS = (("basic", "Basic", 0), ("plus", "Plus", 19900), ("premium", "Premium", 39900))


def ensure_tables(c):
    c.execute("""CREATE TABLE IF NOT EXISTS membership_plans (
        plan_key TEXT PRIMARY KEY, name TEXT NOT NULL, price_paise INTEGER,
        duration_days INTEGER, benefits_json TEXT NOT NULL DEFAULT '[]',
        is_active INTEGER NOT NULL DEFAULT 1, product_discount_percent INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    plan_columns={r[1] for r in c.execute("PRAGMA table_info(membership_plans)").rows}
    if "product_discount_percent" not in plan_columns:
        c.execute("ALTER TABLE membership_plans ADD COLUMN product_discount_percent INTEGER NOT NULL DEFAULT 0")
        c.execute("UPDATE membership_plans SET product_discount_percent=CASE plan_key WHEN 'plus' THEN 5 WHEN 'premium' THEN 10 ELSE 0 END")
    c.execute("""CREATE TABLE IF NOT EXISTS membership_applications (
        membership_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, plan_key TEXT NOT NULL,
        amount_paise INTEGER NOT NULL DEFAULT 0, duration_days INTEGER,
        transaction_reference TEXT, screenshot_key TEXT,
        status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','expired')),
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_by TEXT, reviewed_at TEXT,
        activated_at TEXT, expires_at TEXT, rejection_reason TEXT,
        FOREIGN KEY(customer_id) REFERENCES users(id), FOREIGN KEY(plan_key) REFERENCES membership_plans(plan_key))""")
    c.execute("""CREATE TABLE IF NOT EXISTS membership_events (
        id TEXT PRIMARY KEY, membership_id TEXT NOT NULL, actor_id TEXT NOT NULL,
        action TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(membership_id) REFERENCES membership_applications(membership_id))""")
    c.execute("CREATE INDEX IF NOT EXISTS memberships_customer_recent ON membership_applications(customer_id,applied_at)")
    for key, name, price_paise in PLAN_DEFAULTS:
        discount={"basic":0,"plus":5,"premium":10}[key]
        c.execute("INSERT OR IGNORE INTO membership_plans(plan_key,name,price_paise,duration_days,benefits_json,is_active,product_discount_percent) VALUES(?,?,?,NULL,'[]',1,?)",
                  (key,name,price_paise,discount))
        c.execute("UPDATE membership_plans SET price_paise=? WHERE plan_key=? AND price_paise IS NULL",(price_paise,key))


def _plans(c):
    rows=c.execute("SELECT plan_key,name,price_paise,duration_days,benefits_json,is_active,updated_at,product_discount_percent FROM membership_plans ORDER BY CASE plan_key WHEN 'basic' THEN 1 WHEN 'plus' THEN 2 WHEN 'premium' THEN 3 ELSE 4 END,name").rows
    result=[]
    for r in rows:
        try: benefits=json.loads(r[4] or "[]")
        except (TypeError,ValueError): benefits=[]
        result.append({"plan_key":r[0],"name":r[1],"price_paise":r[2],"duration_days":r[3],"benefits":benefits,"is_active":bool(r[5]),"updated_at":r[6],"product_discount_percent":int(r[7] or 0)})
    return result


def product_discount_percent(c, customer_id):
    """Return the rate for the customer's current approved, unexpired membership."""
    now=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
    sql="""SELECT p.product_discount_percent,p.name
        FROM membership_applications a JOIN membership_plans p ON p.plan_key=a.plan_key
        WHERE a.customer_id=? AND a.status='approved' AND (a.expires_at IS NULL OR a.expires_at>?)
        ORDER BY a.activated_at DESC,a.applied_at DESC LIMIT 1"""
    try:
        rows=c.execute(sql,(customer_id,now)).rows
    except Exception as exc:
        # Initialize the membership schema only for a new database or first upgrade.
        message=str(exc).lower()
        if "no such table" not in message and "no such column" not in message:
            raise
        ensure_tables(c)
        rows=c.execute(sql,(customer_id,now)).rows
    return (max(0,min(100,int(rows[0][0] or 0))),rows[0][1]) if rows else (0,None)


def _expire_customer(c, customer_id):
    now=datetime.now(timezone.utc)
    rows=c.execute("SELECT membership_id,expires_at FROM membership_applications WHERE customer_id=? AND status='approved' AND expires_at IS NOT NULL",(customer_id,)).rows
    for membership_id, expiry in rows:
        try: expired=datetime.fromisoformat(str(expiry).replace("Z","+00:00")) <= now
        except ValueError: expired=False
        if expired:
            c.execute("UPDATE membership_applications SET status='expired' WHERE membership_id=? AND status='approved'",(membership_id,))
            c.execute("INSERT INTO membership_events(id,membership_id,actor_id,action,note) VALUES(?,?,?,'expired','Expiry enforced on request')",
                      (str(uuid.uuid4()),membership_id,customer_id))


@bp.get("/plans")
def public_plans():
    try:
        with get_connection() as c:
            ensure_tables(c)
            return jsonify(success=True,result=[p for p in _plans(c) if p["is_active"]])
    except Exception:return jsonify(success=False,error="Could not load membership plans"),503


@bp.get("/current")
@require_customer
def current_membership():
    try:
        user=request.auth["sub"]
        with get_connection() as c:
            ensure_tables(c);_expire_customer(c,user)
            rows=c.execute("""SELECT a.membership_id,a.plan_key,p.name,a.status,a.activated_at,a.expires_at,a.amount_paise
                FROM membership_applications a JOIN membership_plans p ON p.plan_key=a.plan_key
                WHERE a.customer_id=? AND a.status='approved' ORDER BY a.activated_at DESC LIMIT 1""",(user,)).rows
        if not rows:return jsonify(success=True,result={"plan_key":"basic","name":"Basic","status":"active","membership_id":None})
        r=rows[0]
        return jsonify(success=True,result={"membership_id":r[0],"plan_key":r[1],"name":r[2],"status":r[3],"activated_at":r[4],"expires_at":r[5],"amount_paise":r[6]})
    except Exception:return jsonify(success=False,error="Could not load your membership"),503


@bp.post("/applications")
@require_customer
def apply_membership():
    user=request.auth["sub"]
    plan_key=str(request.form.get("plan_key") or (request.get_json(silent=True) or {}).get("plan_key") or "").strip().lower()
    try:
        with get_connection() as c:
            ensure_tables(c)
            plan=next((p for p in _plans(c) if p["plan_key"]==plan_key and p["is_active"]),None)
            if not plan:return jsonify(success=False,error="Choose an active membership plan"),400
            pending=c.execute("SELECT membership_id FROM membership_applications WHERE customer_id=? AND status='pending' LIMIT 1",(user,)).rows
            if pending:return jsonify(success=False,error="You already have a membership application under review",membership_id=pending[0][0]),409
            if plan_key!="basic" and (plan["price_paise"] is None or plan["duration_days"] is None):
                return jsonify(success=False,error="This plan's price or duration has not been configured yet"),409
        screenshot_key=None; transaction_reference=None
        if plan_key!="basic":
            transaction_reference=str(request.form.get("transaction_reference","")).strip()
            image=request.files.get("screenshot")
            if not transaction_reference or len(transaction_reference)>160 or not image:
                return jsonify(success=False,error="Paid applications need a transaction reference and payment screenshot"),400
            screenshot_key=upload(image,prefix="membership-receipts",private=True,max_bytes=5*1024*1024)
        membership_id="CSM-"+uuid.uuid4().hex[:12].upper()
        now=datetime.now(timezone.utc); status="approved" if plan_key=="basic" else "pending"
        start=now.isoformat(timespec="seconds").replace("+00:00","Z") if status=="approved" else None
        expiry=(now+timedelta(days=plan["duration_days"])).isoformat(timespec="seconds").replace("+00:00","Z") if status=="approved" and plan["duration_days"] else None
        with get_connection() as c:
            ensure_tables(c)
            c.execute("""INSERT INTO membership_applications(membership_id,customer_id,plan_key,amount_paise,duration_days,
                transaction_reference,screenshot_key,status,activated_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (membership_id,user,plan_key,int(plan["price_paise"] or 0),plan["duration_days"],transaction_reference,screenshot_key,status,start,expiry))
            c.execute("INSERT INTO membership_events(id,membership_id,actor_id,action,note) VALUES(?,?,?,?,?)",
                (str(uuid.uuid4()),membership_id,user,"applied","Customer submitted application"))
            if status=="approved":c.execute("INSERT INTO membership_events(id,membership_id,actor_id,action,note) VALUES(?,?,?,?,?)",(str(uuid.uuid4()),membership_id,user,"approved","Free Basic plan activated"))
        return jsonify(success=True,result={"membership_id":membership_id,"plan_key":plan_key,"status":status,"activated_at":start,"expires_at":expiry}),201
    except ValueError as exc:return jsonify(success=False,error=str(exc)),400
    except StorageNotConfigured as exc:return jsonify(success=False,error=str(exc)),503
    except Exception:return jsonify(success=False,error="Could not submit membership application"),503


@bp.get("/applications")
@require_customer
def customer_applications():
    try:
        with get_connection() as c:
            ensure_tables(c)
            data=c.execute("SELECT membership_id,plan_key,amount_paise,duration_days,status,applied_at,reviewed_at,activated_at,expires_at,rejection_reason FROM membership_applications WHERE customer_id=? ORDER BY applied_at DESC LIMIT 50",(request.auth["sub"],)).rows
        keys=("membership_id","plan_key","amount_paise","duration_days","status","applied_at","reviewed_at","activated_at","expires_at","rejection_reason")
        return jsonify(success=True,result=[dict(zip(keys,r)) for r in data])
    except Exception:return jsonify(success=False,error="Could not load your applications"),503
