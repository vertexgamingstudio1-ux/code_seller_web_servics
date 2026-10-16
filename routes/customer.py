from flask import Blueprint,jsonify
from middleware.auth import require_customer
bp=Blueprint("customer",__name__)
@bp.get("/me")
@require_customer
def me():
    c=getattr(__import__("flask").request,"auth",{})
    return jsonify(success=True,customer={"id":c.get("sub"),"email":c.get("email"),"role":c.get("role")})
