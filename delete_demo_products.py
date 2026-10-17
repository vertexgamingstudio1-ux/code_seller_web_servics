import json
from pathlib import Path
from datetime import datetime
from db import get_connection
targets = {
    "code-001": "AI Starter Project",
    "code-002": "Modern Web Starter",
    "code-003": "Game Development Kit",
    "code-004": "Developer Utility",
}
def rows_as_dicts(result):
    columns = [str(c) for c in result.columns]
    return [dict(zip(columns, row)) for row in result.rows]
with get_connection() as client:
    result = client.execute(
        "SELECT * FROM products WHERE id IN (?, ?, ?, ?)",
        list(targets),
    )
    products = rows_as_dicts(result)
    if not products or any(
        p.get("id") not in targets
        or p.get("name") != targets.get(p.get("id"))
        for p in products
    ) or len(products) != 4:
        print("STOPPED: product records did not match exactly.")
        print("Returned columns:", result.columns)
        print("Returned rows:", result.rows)
        raise SystemExit(1)
    tables = [
        r[0] for r in client.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).rows
    ]
    versions = []
    if "product_versions" in tables:
        versions = rows_as_dicts(client.execute(
            "SELECT * FROM product_versions "
            "WHERE product_id IN (?, ?, ?, ?)",
            list(targets),
        ))
    backup = {
        "created_at": datetime.now().isoformat(),
        "products": products,
        "product_versions": versions,
    }
    path = Path(
        f"demo_products_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    path.write_text(json.dumps(backup, indent=2, default=str), encoding="utf-8")
    print("Backup saved:", path.resolve())
    blockers = []
    for table in tables:
        if table in ("products", "product_versions", "sqlite_sequence"):
            continue
        safe_table = table.replace('"', '""')
        cols = [r[1] for r in client.execute(
            f'PRAGMA table_info("{safe_table}")'
        ).rows]
        for col in ("product_id", "productId"):
            if col in cols:
                safe_col = col.replace('"', '""')
                count = client.execute(
                    f'SELECT COUNT(*) FROM "{safe_table}" '
                    f'WHERE "{safe_col}" IN (?, ?, ?, ?)',
                    list(targets),
                ).rows[0][0]
                if count:
                    blockers.append(f"{table}.{col}: {count} related rows")
    if blockers:
        print("STOPPED: related rows need review; nothing deleted.")
        print("\n".join(blockers))
        raise SystemExit(2)
    if "product_versions" in tables:
        client.execute(
            "DELETE FROM product_versions "
            "WHERE product_id IN (?, ?, ?, ?)",
            list(targets),
        )
    client.execute(
        "DELETE FROM products WHERE id IN (?, ?, ?, ?)",
        list(targets),
    )
    check = client.execute(
        "SELECT id, name FROM products WHERE id IN (?, ?, ?, ?)",
        list(targets),
    )
    if check.rows:
        print("WARNING: some product rows remain:", check.rows)
    else:
        print("VERIFIED: all four demo products deleted.")
