import secrets
from db import get_connection
PRODUCT_FIELDS = (
    "id", "name", "slug", "description", "category", "price",
    "currency", "is_free", "is_published", "sales_count",
    "created_at", "updated_at"
)
def _product(row):
    if row is None:
        return None
    result = dict(zip(PRODUCT_FIELDS, row))
    result["is_free"] = bool(result["is_free"])
    result["is_published"] = bool(result["is_published"])
    return result
class ProductService:
    @staticmethod
    def list_products(user_id=None):
        with get_connection() as client:
            result = client.execute(
                """SELECT id, name, slug, description, category, price,
                          currency, is_free, is_published, sales_count,
                          created_at, updated_at
                   FROM products
                   WHERE is_published = 1
                   ORDER BY created_at DESC"""
            )
        from services.festival_service import active_campaign, apply_campaign
        membership_percent, membership_plan_name = _membership_discount(user_id)
        with get_connection() as client:
            campaign = active_campaign(client)
        products = [apply_campaign(_product(row), campaign, membership_percent) for row in result.rows]
        for product in products:
            product["membership_plan_name"] = membership_plan_name if membership_percent else None
        return {"products": products, "count": len(products), "festival_campaign": campaign}
    @staticmethod
    def get_product(product_id, user_id=None, membership_percent=None):
        with get_connection() as client:
            result = client.execute(
                """SELECT id, name, slug, description, category, price,
                          currency, is_free, is_published, sales_count,
                          created_at, updated_at
                   FROM products
                   WHERE id = ? AND is_published = 1
                   LIMIT 1""",
                (product_id,)
            )
        if not result.rows:
            return None
        from services.festival_service import active_campaign, apply_campaign
        if membership_percent is None:
            membership_percent, membership_plan_name = _membership_discount(user_id)
        else:
            membership_plan_name = None
        with get_connection() as client:
            campaign = active_campaign(client)
        product=apply_campaign(_product(result.rows[0]), campaign, membership_percent)
        product["membership_plan_name"] = membership_plan_name if membership_percent else None
        return product
    @staticmethod
    def create_product(data):
        import secrets
        import re
        name = str(data.get("name", "")).strip()
        slug = str(data.get("slug", "")).strip().lower()
        description = str(data.get("description", "")).strip()
        category = str(data.get("category", "")).strip() or None
        currency = str(data.get("currency", "INR")).strip().upper()
        is_free = bool(data.get("is_free", False))
        is_published = bool(data.get("is_published", False))
        if not name or not slug:
            raise ValueError("Product name and slug are required")
        if len(name) > 160 or len(slug) > 180:
            raise ValueError("Product name or slug is too long")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError("Slug must use lowercase letters, numbers and hyphens")
        if currency != "INR":
            raise ValueError("Only INR is currently supported")
        try:
            price = int(data.get("price", 0))
        except (TypeError, ValueError):
            raise ValueError("Price must be a whole number in paise") from None
        if price < 0:
            raise ValueError("Price cannot be negative")
        if is_free:
            price = 0
        with get_connection() as client:
            product_id = _new_product_id(client)
            client.execute(
                """INSERT INTO products
                   (id, name, slug, description, category, price, currency,
                    is_free, is_published)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (product_id, name, slug, description, category, price,
                 currency, int(is_free), int(is_published))
            )
        return ProductService.get_product_for_admin(product_id)
    @staticmethod
    def get_product_for_admin(product_id):
        with get_connection() as client:
            result = client.execute(
                """SELECT id, name, slug, description, category, price,
                          currency, is_free, is_published, sales_count,
                          created_at, updated_at
                   FROM products WHERE id = ? LIMIT 1""",
                (product_id,)
            )
        return _product(result.rows[0]) if result.rows else None

def _new_product_id(client):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    for _ in range(30):
        candidate = "".join(secrets.choice(alphabet) for _ in range(6))
        if not client.execute("SELECT 1 FROM products WHERE id=?", (candidate,)).rows:
            return candidate
    raise RuntimeError("Could not allocate a unique product ID")


def _membership_discount(user_id):
    if not user_id:
        return 0,None
    from routes.memberships import product_discount_percent
    with get_connection() as client:
        return product_discount_percent(client, user_id)


def _membership_discount_percent(user_id):
    return _membership_discount(user_id)[0]
