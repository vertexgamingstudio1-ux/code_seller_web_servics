from db import get_connection
names = [
    "AI Starter Project",
    "Modern Web Starter",
    "Game Development Kit",
    "Developer Utility",
]
with get_connection() as client:
    for name in names:
        result = client.execute(
            "SELECT id, name, slug, price FROM products WHERE name = ?",
            [name],
        )
        for row in result.rows:
            print(f"ID={row[0]} | Name={row[1]} | Slug={row[2]} | Price={row[3]}")
