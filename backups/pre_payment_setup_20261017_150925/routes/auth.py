from flask import Blueprint, jsonify, request
import jwt
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from auth.jwt import verify_token, create_phone_verification_token, create_customer_token
from services.otp_service import generate_otp, expiry
from services.msg91 import send_msg91_otp
from services.otp_repository import save_otp, verify_saved_otp
from services.customer_auth_service import (
    create_customer, find_customer, password_matches, find_or_create_google_customer
)
from config import Config
bp = Blueprint("auth", __name__)
@bp.post("/google")
def google_login():
    data = request.get_json(silent=True) or {}
    credential = str(data.get("credential", "")).strip()
    if not credential:
        return jsonify(success=False, error="Google credential is required"), 400
    try:
        client_id = getattr(Config, "GOOGLE_CLIENT_ID", None)
        if not client_id:
            return jsonify(success=False, error="Google login is not configured"), 503
        claims = id_token.verify_oauth2_token(
            credential, google_requests.Request(), client_id
        )
        email = str(claims.get("email", "")).strip().lower()
        name = str(claims.get("name", "")).strip()
        if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            return jsonify(success=False, error="Invalid Google issuer"), 401
        if not email or claims.get("email_verified") is not True:
            return jsonify(success=False, error="Google email is not verified"), 401
        user, created = find_or_create_google_customer(email, name)
        token = create_customer_token(user["id"], email)
        return jsonify(
            success=True,
            created=created,
            customer={k: user.get(k) for k in ("id", "email", "display_name", "role")},
            token=token
        ), 201 if created else 200
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 403
    except Exception:
        return jsonify(success=False, error="Google sign-in failed"), 401
@bp.post("/request-otp")
def request_otp():
    data = request.get_json(silent=True) or {}
    phone = str(data.get("phone", "")).strip()
    if not phone:
        return jsonify(success=False, error="Phone is required"), 400
    code = generate_otp()
    save_otp(phone, "registration", code, expiry())
    try:
        result = send_msg91_otp(phone, code)
    except Exception:
        return jsonify(success=False, error="Unable to send OTP"), 500
    return jsonify(success=True, message="OTP sent", provider=result), 200
@bp.post("/verify-otp")
def verify_otp():
    data = request.get_json(silent=True) or {}
    phone = str(data.get("phone", "")).strip()
    code = str(data.get("otp", "")).strip()
    if not phone or not code:
        return jsonify(success=False, error="Phone and OTP are required"), 400
    ok, msg = verify_saved_otp(phone, "registration", code)
    if not ok:
        return jsonify(success=False, error=msg), 400
    return jsonify(success=True, verification_token=create_phone_verification_token(phone)), 200
@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip()
    phone = str(data.get("phone", "")).strip() or None
    name = str(data.get("display_name", "")).strip()
    password = str(data.get("password", ""))
    vt = str(data.get("verification_token", "")).strip()
    if not email or not name or not password:
        return jsonify(success=False, error="Email, name and password are required"), 400
    if len(password) < 8:
        return jsonify(success=False, error="Password must be at least 8 characters"), 400
    if vt:
        try:
            claims = verify_token(vt)
            if claims.get("purpose") != "phone_verification" or claims.get("phone") != phone:
                return jsonify(success=False, error="Invalid phone verification"), 400
        except jwt.ExpiredSignatureError:
            return jsonify(success=False, error="Phone verification expired"), 400
        except Exception:
            return jsonify(success=False, error="Invalid phone verification"), 400
    try:
        user = create_customer(email, phone, name, password)
        return jsonify(
            success=True,
            customer={k: user.get(k) for k in ("id", "email", "display_name", "role")},
            token=create_customer_token(user["id"], email)
        ), 201
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 409
    except Exception:
        return jsonify(success=False, error="Registration failed"), 500
@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))
    user = find_customer(email)
    if not user or not user["is_active"] or not password_matches(password, user["password_hash"]):
        return jsonify(success=False, error="Invalid email or password"), 401
    return jsonify(
        success=True,
        customer={k: user.get(k) for k in ("id", "email", "display_name", "role")},
        token=create_customer_token(user["id"], email)
    ), 200
