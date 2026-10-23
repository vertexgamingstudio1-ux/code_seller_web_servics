import uuid
import hashlib
import secrets
from datetime import datetime,timezone
def generate_otp():
    return "".join(str(secrets.randbelow(10)) for _ in range(6))
def hash_otp(code):
    return hashlib.sha256(code.encode()).hexdigest()
def verify_otp_hash(code,stored):
    return secrets.compare_digest(hash_otp(code),stored)
def expiry():
    from datetime import timedelta
    return datetime.now(timezone.utc)+timedelta(minutes=10)
