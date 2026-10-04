import os
from datetime import datetime, timedelta, timezone
import jwt
def create_admin_token(user_id, email):
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": "admin",
        "iat": now,
        "exp": now + timedelta(hours=12)
    }
    return jwt.encode(payload, secret, algorithm="HS256")
def verify_token(token):
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"]
    )
