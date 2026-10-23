from db import get_connection
email = "vertexgamingstudio1@gmail.com"
with get_connection() as client:
    result = client.execute(
        "UPDATE users SET role = 'admin', updated_at = CURRENT_TIMESTAMP WHERE email = ? AND role = 'customer'",
        [email]
    )
    check = client.execute(
        "SELECT email, role, is_active FROM users WHERE email = ?",
        [email]
    )
    if check.rows:
        print("Email:", check.rows[0][0])
        print("Role:", check.rows[0][1])
        print("Active:", check.rows[0][2])
        print("Admin promotion successful." if check.rows[0][1] == "admin" else "Promotion failed.")
    else:
        print("Account not found.")
