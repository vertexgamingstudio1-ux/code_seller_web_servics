import os
import uuid
import getpass
import bcrypt
from dotenv import load_dotenv
from db import get_connection
load_dotenv()
email = "vertexgamingstudio1@gmail.com"
password = getpass.getpass("Choose admin password: ")
confirm = getpass.getpass("Confirm admin password: ")
if len(password) < 12:
    raise SystemExit("Use a password with at least 12 characters.")
if password != confirm:
    raise SystemExit("Passwords do not match.")
password_hash = bcrypt.hashpw(
    password.encode("utf-8"),
    bcrypt.gensalt()
).decode("utf-8")
with get_connection() as client:
    existing = client.execute(
        "SELECT id, role FROM users WHERE email = ?",
        [email]
    )
    if existing.rows:
        raise SystemExit(
            f"An account already exists with role: {existing.rows[0][1]}. "
            "No changes made."
        )
    client.execute(
        """INSERT INTO users
        (id, email, password_hash, display_name, role, is_active)
        VALUES (?, ?, ?, ?, 'admin', 1)""",
        [str(uuid.uuid4()), email, password_hash, "Code Seller Admin"]
    )
    print("Admin account created successfully.")
    print("Email:", email)
    print("Role: admin")
