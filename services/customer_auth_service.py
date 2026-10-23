import uuid
import secrets
import bcrypt
from db import get_connection
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def password_matches(password, password_hash):
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError):
        return False
def create_customer(email, phone, display_name, password):
    ph = hash_password(password)
    with get_connection() as c:
        existing = c.execute(
            "SELECT id FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1", (email,)
        ).rows
        if existing:
            raise ValueError("An account with this email already exists")
        uid = _new_customer_id(c)
        c.execute(
            """INSERT INTO users(id,email,phone,password_hash,display_name,role,is_active)
               VALUES(?,?,?,?,?,'customer',1)""",
            (uid, email, phone or None, ph, display_name)
        )
    return {
        "id": uid, "email": email, "phone": phone or None,
        "display_name": display_name, "role": "customer"
    }

def _new_customer_id(client):
    # Readable, short IDs; the database uniqueness check handles rare collisions.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        candidate = "CS-" + "".join(secrets.choice(alphabet) for _ in range(8))
        if not client.execute("SELECT 1 FROM users WHERE id=?", (candidate,)).rows:
            return candidate
    raise RuntimeError("Could not allocate a unique customer ID")
def find_customer(email):
    with get_connection() as c:
        r = c.execute(
            """SELECT id,email,phone,password_hash,display_name,role,is_active
               FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1""", (email,)
        )
        if not r.rows:
            return None
        x = r.rows[0]
    return {
        "id": str(x[0]), "email": x[1], "phone": x[2],
        "password_hash": x[3], "display_name": x[4],
        "role": x[5], "is_active": bool(x[6])
    }
def find_or_create_google_customer(email, display_name):
    email = email.strip().lower()
    with get_connection() as c:
        r = c.execute(
            """SELECT id,email,phone,display_name,role,is_active
               FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1""", (email,)
        )
        if r.rows:
            x = r.rows[0]
            user = {
                "id": str(x[0]), "email": x[1], "phone": x[2],
                "display_name": x[3], "role": x[4], "is_active": bool(x[5])
            }
            if user["role"] != "customer":
                raise ValueError("This email belongs to a non-customer account")
            if not user["is_active"]:
                raise ValueError("This account is disabled")
            return user, False
        uid = _new_customer_id(c)
        random_password_hash = hash_password(secrets.token_urlsafe(32))
        c.execute(
            """INSERT INTO users(id,email,phone,password_hash,display_name,role,is_active)
               VALUES(?,?,NULL,?,?,'customer',1)""",
            (uid, email, random_password_hash, display_name or email.split("@")[0])
        )
        return {
            "id": uid, "email": email, "phone": None,
            "display_name": display_name or email.split("@")[0],
            "role": "customer"
        }, True

