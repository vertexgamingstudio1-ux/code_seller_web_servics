from functools import wraps
import logging

import jwt
from flask import jsonify, request

from auth.jwt import verify_token

logger = logging.getLogger(__name__)


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
                logger.warning("Rejected expired JWT for protected route")
                return jsonify({"success": False, "error": "Your session has expired. Please sign in again."}), 401
            except jwt.InvalidTokenError as exc:
                logger.warning("Rejected invalid JWT for protected route (%s)", type(exc).__name__)
                return jsonify({"success": False, "error": "Your session is invalid. Please sign in again."}), 401
            except Exception as exc:
                logger.error("JWT verification failed for protected route (%s)", type(exc).__name__)
                return jsonify({"success": False, "error": "Could not verify your session. Please sign in again."}), 401

            if claims.get("role") != role:
                return jsonify({"success": False, "error": "Forbidden"}), 403

            request.auth = claims
            return fn(*args, **kwargs)

        return wrapped

    return deco


require_customer = require_role("customer")
require_admin = require_role("admin")
