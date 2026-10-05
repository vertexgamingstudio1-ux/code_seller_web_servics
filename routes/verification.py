import os
import secrets
import time
import hashlib
from flask import Blueprint, jsonify, request
verification_bp = Blueprint("verification", __name__)
_codes = {}
_RATE_LIMIT_SECONDS = 60
_CODE_TTL_SECONDS = 600
def _email_key(email):
    return email.strip().lower()
def _hash_code(code):
    secret = os.getenv("JWT_SECRET", "temporary-local-secret")
    return hashlib.sha256((secret + code).encode()).hexdigest()
def _send_verification_email(email, code):
    print(f"[EMAIL VERIFICATION] {email}: {code}")
    # Real email provider integration goes here.
    # We deliberately do not expose the code to the browser.
    #
    # Configure a provider before production email delivery.
@verification_bp.post("/send-code")
def send_code():
    data = request.get_json(silent=True) or {}
    email = _email_key(data.get("email", ""))
    if not email or "@" not in email:
        return jsonify({
            "success": False,
            "error": "Valid email is required"
        }), 400
    now = time.time()
    previous = _codes.get(email)
    if previous and now - previous["sent_at"] < _RATE_LIMIT_SECONDS:
        return jsonify({
            "success": False,
            "error": "Please wait before requesting another code"
        }), 429
    code = f"{secrets.randbelow(1000000):06d}"
    _codes[email] = {
        "code_hash": _hash_code(code),
        "sent_at": now,
        "expires_at": now + _CODE_TTL_SECONDS,
        "attempts": 0
    }
    _send_verification_email(email, code)
    return jsonify({
        "success": True,
        "message": "Verification code sent"
    })
@verification_bp.post("/verify-code")
def verify_code():
    data = request.get_json(silent=True) or {}
    email = _email_key(data.get("email", ""))
    code = str(data.get("code", "")).strip()
    record = _codes.get(email)
    if not record:
        return jsonify({
            "success": False,
            "error": "No active verification code"
        }), 400
    if time.time() > record["expires_at"]:
        _codes.pop(email, None)
        return jsonify({
            "success": False,
            "error": "Verification code expired"
        }), 400
    if record["attempts"] >= 5:
        _codes.pop(email, None)
        return jsonify({
            "success": False,
            "error": "Too many attempts"
        }), 429
    record["attempts"] += 1
    if not secrets.compare_digest(
        record["code_hash"],
        _hash_code(code)
    ):
        return jsonify({
            "success": False,
            "error": "Invalid verification code"
        }), 400
    _codes.pop(email, None)
    customer_token = secrets.token_urlsafe(32)
    return jsonify({
        "success": True,
        "verified": True,
        "email": email,
        "customer_token": customer_token
    })
