from db import get_connection
SCHEMA = [
"""CREATE TABLE IF NOT EXISTS users (
id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
phone TEXT, password_hash TEXT NOT NULL, display_name TEXT NOT NULL,
role TEXT NOT NULL DEFAULT 'customer' CHECK(role IN ('customer','admin')),
is_active INTEGER NOT NULL DEFAULT 1,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
"""CREATE TABLE IF NOT EXISTS otp_codes (
id TEXT PRIMARY KEY, phone TEXT NOT NULL, purpose TEXT NOT NULL,
code_hash TEXT NOT NULL, expires_at TEXT NOT NULL,
attempts INTEGER NOT NULL DEFAULT 0, used_at TEXT,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
"""CREATE TABLE IF NOT EXISTS products (
id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
description TEXT NOT NULL DEFAULT '', category TEXT,
price INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'INR',
margin_percent REAL NOT NULL DEFAULT 0, is_free INTEGER NOT NULL DEFAULT 0,
is_published INTEGER NOT NULL DEFAULT 0, sales_count INTEGER NOT NULL DEFAULT 0,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
"""CREATE TABLE IF NOT EXISTS product_versions (
id TEXT PRIMARY KEY, product_id TEXT NOT NULL, version TEXT NOT NULL,
changelog TEXT NOT NULL DEFAULT '', single_file_path TEXT,
package_file_path TEXT, is_active INTEGER NOT NULL DEFAULT 0,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY(product_id) REFERENCES products(id))""",
"""CREATE TABLE IF NOT EXISTS orders (
id TEXT PRIMARY KEY, user_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
subtotal INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
currency TEXT NOT NULL DEFAULT 'INR',
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY(user_id) REFERENCES users(id))""",
"""CREATE TABLE IF NOT EXISTS order_items (
id TEXT PRIMARY KEY, order_id TEXT NOT NULL, product_id TEXT NOT NULL,
product_version_id TEXT, quantity INTEGER NOT NULL DEFAULT 1,
unit_price INTEGER NOT NULL DEFAULT 0, total_price INTEGER NOT NULL DEFAULT 0,
FOREIGN KEY(order_id) REFERENCES orders(id),
FOREIGN KEY(product_id) REFERENCES products(id),
FOREIGN KEY(product_version_id) REFERENCES product_versions(id))""",
"""CREATE TABLE IF NOT EXISTS payments (
id TEXT PRIMARY KEY, order_id TEXT NOT NULL, provider TEXT,
provider_payment_id TEXT, status TEXT NOT NULL DEFAULT 'pending',
amount INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'INR',
paid_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY(order_id) REFERENCES orders(id))""",
"""CREATE TABLE IF NOT EXISTS finance (
id TEXT PRIMARY KEY, order_id TEXT, type TEXT NOT NULL,
amount INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'INR',
description TEXT NOT NULL DEFAULT '',
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY(order_id) REFERENCES orders(id))""",
"""CREATE TABLE IF NOT EXISTS downloads (
id TEXT PRIMARY KEY, user_id TEXT NOT NULL, product_id TEXT NOT NULL,
product_version_id TEXT, order_id TEXT, download_type TEXT NOT NULL DEFAULT 'package',
file_reference TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY(user_id) REFERENCES users(id),
FOREIGN KEY(product_id) REFERENCES products(id),
FOREIGN KEY(product_version_id) REFERENCES product_versions(id),
FOREIGN KEY(order_id) REFERENCES orders(id))""",
"""CREATE TABLE IF NOT EXISTS cash_approvals (
order_id TEXT PRIMARY KEY,
customer_id TEXT NOT NULL,
amount INTEGER NOT NULL,
currency TEXT NOT NULL DEFAULT 'INR',
approved_by TEXT NOT NULL,
approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
"""CREATE TABLE IF NOT EXISTS refunds (
id TEXT PRIMARY KEY, order_id TEXT NOT NULL, payment_id TEXT,
amount INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'INR',
status TEXT NOT NULL DEFAULT 'pending', reason TEXT NOT NULL DEFAULT '',
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY(order_id) REFERENCES orders(id),
FOREIGN KEY(payment_id) REFERENCES payments(id))"""
]
def init_schema():
    with get_connection() as client:
        for sql in SCHEMA:
            client.execute(sql)
