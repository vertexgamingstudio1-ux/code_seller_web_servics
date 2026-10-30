from functools import wraps

import jwt
from flask import jsonify, request

from auth.jwt import verify_token


def require_role(role):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify({"success": False, "error": "Authentication required"}), 401

            token = header[7:].strip()
            if not token:
                return jsonify({"success": False, "error": "Authentication required"}), 401

            try:
                claims = verify_token(token)
            except jwt.ExpiredSignatureError:
                print("AUTH DEBUG: TOKEN EXPIRED")
                return jsonify({"success": False, "error": "Token expired"}), 401
            except jwt.InvalidSignatureError:
                print("AUTH DEBUG: SIGNATURE MISMATCH")
                return jsonify({"success": False, "error": "Signature mismatch"}), 401
            except jwt.InvalidTokenError as exc:
                print("AUTH DEBUG: INVALID TOKEN:", type(exc).__name__)
                return jsonify({"success": False, "error": "Invalid token"}), 401
            except Exception as exc:
                print("AUTH DEBUG: OTHER ERROR:", type(exc).__name__)
                return jsonify({"success": False, "error": "Authentication error"}), 401

            if claims.get("role") != role:
                return jsonify({"success": False, "error": "Forbidden"}), 403

            request.auth = claims
            return fn(*args, **kwargs)

        return wrapped

    return deco


require_customer = require_role("customer")
require_admin = require_role("admin")
