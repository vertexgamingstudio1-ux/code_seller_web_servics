import os
from functools import wraps
import jwt
from flask import request, jsonify
def require_admin(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({
                "success": False,
                "error": "Admin authentication required"
            }), 401
        token = header[7:].strip()
        secret = os.getenv("JWT_SECRET")
        if not secret:
            return jsonify({
                "success": False,
                "error": "JWT_SECRET is not configured"
            }), 500
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"]
            )
        except jwt.ExpiredSignatureError:
            return jsonify({
                "success": False,
                "error": "Admin token expired"
            }), 401
        except jwt.InvalidTokenError:
            return jsonify({
                "success": False,
                "error": "Invalid admin token"
            }), 401
        if payload.get("role") != "admin":
            return jsonify({
                "success": False,
                "error": "Admin permission required"
            }), 403
        return f(*args, **kwargs)
    return wrapped
