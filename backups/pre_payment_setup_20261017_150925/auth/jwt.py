import os
from datetime import datetime,timedelta,timezone
import jwt
def token(payload,lifetime):
    secret=os.getenv("JWT_SECRET")
    if not secret:raise RuntimeError("JWT_SECRET is not configured")
    now=datetime.now(timezone.utc)
    return jwt.encode({**payload,"iat":now,"exp":now+lifetime},secret,algorithm="HS256")
def create_customer_token(user_id,email):
    return token({"sub":str(user_id),"email":email,"role":"customer"},timedelta(days=7))
def create_admin_token(user_id,email):
    return token({"sub":str(user_id),"email":email,"role":"admin"},timedelta(hours=12))
def create_phone_verification_token(phone):
    return token({"phone":phone,"purpose":"phone_verification"},timedelta(minutes=15))
def verify_token(value):
    secret=os.getenv("JWT_SECRET")
    if not secret:raise RuntimeError("JWT_SECRET is not configured")
    return jwt.decode(value,secret,algorithms=["HS256"])
