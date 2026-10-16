from functools import wraps
from flask import request,jsonify
from auth.jwt import verify_token
def require_role(role):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            h=request.headers.get("Authorization","")
            if not h.startswith("Bearer "):return jsonify(success=False,error="Authentication required"),401
            try:
                claims=verify_token(h[7:].strip())
                if claims.get("role")!=role:return jsonify(success=False,error="Forbidden"),403
                request.auth=claims
                return fn(*args,**kwargs)
            except Exception:return jsonify(success=False,error="Invalid or expired token"),401
        return wrapped
    return deco
require_customer=require_role("customer")
require_admin=require_role("admin")
