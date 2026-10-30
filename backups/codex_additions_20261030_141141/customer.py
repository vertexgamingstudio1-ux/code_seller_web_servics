import uuid
from flask import Blueprint,jsonify,request
from middleware.auth import require_customer
from db import get_connection
bp=Blueprint("customer",__name__)
def ensure_demand_tables(client):
    client.execute("CREATE TABLE IF NOT EXISTS demand_threads (id TEXT PRIMARY KEY,user_id TEXT NOT NULL,subject TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(user_id) REFERENCES users(id))")
    client.execute("CREATE TABLE IF NOT EXISTS demand_messages (id TEXT PRIMARY KEY,thread_id TEXT NOT NULL,user_id TEXT NOT NULL,sender_role TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(thread_id) REFERENCES demand_threads(id),FOREIGN KEY(user_id) REFERENCES users(id))")
@bp.get("/me")
@require_customer
def me():
    c=request.auth
    return jsonify(success=True,customer={"id":c.get("sub"),"email":c.get("email"),"role":c.get("role")})
@bp.get("/demands")
@require_customer
def demands():
    try:
        with get_connection() as client:
            ensure_demand_tables(client)
            result=client.execute("SELECT id,subject,status,created_at,updated_at FROM demand_threads WHERE user_id=? ORDER BY updated_at DESC",(request.auth.get("sub"),))
        return jsonify(success=True,result=[dict(zip(("id","subject","status","created_at","updated_at"),r)) for r in result.rows])
    except Exception:return jsonify(success=False,error="Could not load your Demands"),503
@bp.post("/demands")
@require_customer
def create_demand():
    data=request.get_json(silent=True) or {};subject=str(data.get("subject","")).strip();message=str(data.get("message","")).strip()
    if not subject or len(subject)>160 or not message or len(message)>4000:return jsonify(success=False,error="A subject and message are required"),400
    user=request.auth.get("sub");thread_id=str(uuid.uuid4())
    try:
        with get_connection() as client:
            ensure_demand_tables(client)
            client.execute("INSERT INTO demand_threads (id,user_id,subject) VALUES (?,?,?)",(thread_id,user,subject))
            client.execute("INSERT INTO demand_messages (id,thread_id,user_id,sender_role,message) VALUES (?,?,?,?,?)",(str(uuid.uuid4()),thread_id,user,"customer",message))
        return jsonify(success=True,result={"id":thread_id,"subject":subject,"status":"open"}),201
    except Exception:return jsonify(success=False,error="Could not save your Demand"),503
@bp.get("/demands/<thread_id>/messages")
@require_customer
def demand_messages(thread_id):
    try:
        with get_connection() as client:
            ensure_demand_tables(client)
            owner=client.execute("SELECT id FROM demand_threads WHERE id=? AND user_id=?",(thread_id,request.auth.get("sub"))).rows
            if not owner:return jsonify(success=False,error="Demand not found"),404
            result=client.execute("SELECT id,thread_id,sender_role,message,created_at FROM demand_messages WHERE thread_id=? ORDER BY created_at,rowid",(thread_id,))
        return jsonify(success=True,result=[dict(zip(("id","thread_id","sender_role","message","created_at"),r)) for r in result.rows])
    except Exception:return jsonify(success=False,error="Could not load Demand messages"),503
@bp.post("/demands/<thread_id>/messages")
@require_customer
def reply_demand(thread_id):
    message=str((request.get_json(silent=True) or {}).get("message","")).strip()
    if not message or len(message)>4000:return jsonify(success=False,error="Message must contain 1 to 4000 characters"),400
    user=request.auth.get("sub")
    try:
        with get_connection() as client:
            ensure_demand_tables(client)
            owner=client.execute("SELECT id FROM demand_threads WHERE id=? AND user_id=?",(thread_id,user)).rows
            if not owner:return jsonify(success=False,error="Demand not found"),404
            client.execute("INSERT INTO demand_messages (id,thread_id,user_id,sender_role,message) VALUES (?,?,?,?,?)",(str(uuid.uuid4()),thread_id,user,"customer",message))
            client.execute("UPDATE demand_threads SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(thread_id,))
        return jsonify(success=True),201
    except Exception:return jsonify(success=False,error="Could not send your message"),503
