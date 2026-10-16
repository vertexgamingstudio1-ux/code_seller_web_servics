import uuid
import bcrypt
from db import get_connection
def hash_password(password):
    return bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
def password_matches(password,password_hash):
    return bcrypt.checkpw(password.encode(),password_hash.encode())
def create_customer(email,phone,display_name,password):
    uid=str(uuid.uuid4())
    ph=hash_password(password)
    with get_connection() as c:
        if c.execute("SELECT id FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1",(email,)).rows:
            raise ValueError("An account with this email already exists")
        c.execute("""INSERT INTO users(id,email,phone,password_hash,display_name,role,is_active)
                     VALUES(?,?,?,?,?,'customer',1)""",(uid,email,phone,ph,display_name))
    return {"id":uid,"email":email,"phone":phone,"display_name":display_name,"role":"customer"}
def find_customer(email):
    with get_connection() as c:
        r=c.execute("""SELECT id,email,phone,password_hash,display_name,role,is_active
                       FROM users WHERE LOWER(email)=LOWER(?) AND role='customer' LIMIT 1""",(email,))
        if not r.rows:return None
        x=r.rows[0]
    return {"id":str(x[0]),"email":x[1],"phone":x[2],"password_hash":x[3],"display_name":x[4],"role":x[5],"is_active":bool(x[6])}
