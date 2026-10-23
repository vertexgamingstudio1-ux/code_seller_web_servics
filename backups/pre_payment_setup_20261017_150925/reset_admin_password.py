import getpass
import bcrypt
from db import get_connection
email = input("Admin email: ").strip()
password = getpass.getpass("New password: ")
confirm = getpass.getpass("Confirm password: ")
if len(password) < 12:
    raise SystemExit("Password must be at least 12 characters.")
if password != confirm:
    raise SystemExit("Passwords do not match.")
hashed = bcrypt.hashpw(
    password.encode("utf-8"), bcrypt.gensalt()
).decode("utf-8")
with get_connection() as client:
    result = client.execute(
        """UPDATE users
           SET password_hash = ?, role = 'admin',
               is_active = 1, updated_at = CURRENT_TIMESTAMP
           WHERE email = ? COLLATE NOCASE""",
        [hashed, email]
    )
    check = client.execute(
        "SELECT email, role, is_active FROM users WHERE email = ? COLLATE NOCASE",
        [email]
    )
    if check.rows:
        print("Password reset successfully.")
        print("Email:", check.rows[0][0])
        print("Role:", check.rows[0][1])
        print("Active:", check.rows[0][2])
    else:
        print("No account found. No account was created.")
