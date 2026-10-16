import uuid
from datetime import datetime,timezone
from db import get_connection
from services.otp_service import hash_otp,verify_otp_hash
def save_otp(phone,purpose,code,expires_at):
    oid=str(uuid.uuid4())
    with get_connection() as c:
        c.execute("UPDATE otp_codes SET used_at=CURRENT_TIMESTAMP WHERE phone=? AND purpose=? AND used_at IS NULL",(phone,purpose))
        c.execute("INSERT INTO otp_codes(id,phone,purpose,code_hash,expires_at) VALUES(?,?,?,?,?)",
                  (oid,phone,purpose,hash_otp(code),expires_at.astimezone(timezone.utc).isoformat()))
    return oid
def verify_saved_otp(phone,purpose,code):
    with get_connection() as c:
        r=c.execute("""SELECT id,code_hash,expires_at,attempts FROM otp_codes
                       WHERE phone=? AND purpose=? AND used_at IS NULL
                       ORDER BY created_at DESC LIMIT 1""",(phone,purpose))
        if not r.rows:return False,"OTP not found"
        oid,h,exp,attempts=r.rows[0]
        if int(attempts)>=5:return False,"Too many attempts"
        try:e=datetime.fromisoformat(str(exp).replace("Z","+00:00"))
        except ValueError:return False,"OTP expiry invalid"
        if e.tzinfo is None:e=e.replace(tzinfo=timezone.utc)
        if e<=datetime.now(timezone.utc):return False,"OTP expired"
        if not verify_otp_hash(code,h):
            c.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE id=?",(oid,))
            return False,"Invalid OTP"
        c.execute("UPDATE otp_codes SET used_at=CURRENT_TIMESTAMP WHERE id=?",(oid,))
        return True,"OTP verified"
