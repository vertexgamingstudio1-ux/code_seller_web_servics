from pathlib import Path
from flask import Blueprint, jsonify, request, send_file
from middleware.auth import require_customer
from db import get_connection

downloads_bp = Blueprint("downloads", __name__)

@downloads_bp.get("/")
@require_customer
def download_list():
    try:
        with get_connection() as c:
            rows=c.execute("""SELECT DISTINCT i.product_id,p.name,i.order_id,o.status
                FROM order_items i JOIN orders o ON o.id=i.order_id JOIN products p ON p.id=i.product_id
                WHERE o.user_id=? AND o.status IN ('paid','processing','completed') ORDER BY o.created_at DESC""",(request.auth["sub"],)).rows
        return jsonify(success=True,result=[dict(zip(("product_id","name","order_id","order_status"),r)) for r in rows])
    except Exception:return jsonify(success=False,error="Could not load downloads"),503

@downloads_bp.post("/authorize")
@require_customer
def authorize_download():
    data=request.get_json(silent=True) or {};product_id=str(data.get("product_id",""));order_id=str(data.get("order_id",""))
    try:
        with get_connection() as c:
            rows=c.execute("""SELECT v.single_file_path,v.package_file_path FROM orders o
                JOIN order_items i ON i.order_id=o.id JOIN product_versions v ON v.product_id=i.product_id AND v.id=COALESCE(i.product_version_id,(SELECT id FROM product_versions WHERE product_id=i.product_id AND is_active=1 ORDER BY created_at DESC LIMIT 1))
                WHERE o.id=? AND o.user_id=? AND o.status IN ('paid','processing','completed') AND i.product_id=? LIMIT 1""",(order_id,request.auth["sub"],product_id)).rows
        if not rows:return jsonify(success=False,error="A confirmed paid order is required"),403
        relative=rows[0][1] or rows[0][0]
        if not relative:return jsonify(success=False,error="No downloadable release is available"),404
        root=Path(__file__).resolve().parent.parent / "uploads";target=(root/relative).resolve()
        if root.resolve() not in target.parents or not target.is_file():return jsonify(success=False,error="Download file is unavailable"),404
        return send_file(target,as_attachment=True)
    except Exception:return jsonify(success=False,error="Could not authorize download"),503

@downloads_bp.get("/stats")
def download_stats():
    return jsonify(success=True,result={"status":"ready"})
