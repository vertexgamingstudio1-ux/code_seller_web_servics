from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CAMPAIGNS = (("holi", "Holi"), ("diwali", "Diwali"), ("navratri", "Navratri"), ("ganesh-chaturthi", "Ganesh Chaturthi"), ("new-year", "New Year"))

def ensure_festival_tables(client):
    client.execute("CREATE TABLE IF NOT EXISTS festival_scheduler_settings (id INTEGER PRIMARY KEY CHECK (id=1), enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    client.execute("INSERT OR IGNORE INTO festival_scheduler_settings (id,enabled) VALUES (1,0)")
    client.execute("CREATE TABLE IF NOT EXISTS festival_campaigns (slug TEXT PRIMARY KEY, name TEXT NOT NULL, reference_sale_date TEXT, enabled INTEGER NOT NULL DEFAULT 0, campaign_end_date TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    columns = {row[1] for row in client.execute("PRAGMA table_info(festival_campaigns)").rows}
    if "campaign_end_date" not in columns:
        client.execute("ALTER TABLE festival_campaigns ADD COLUMN campaign_end_date TEXT")
    for slug, name in CAMPAIGNS:
        client.execute("INSERT OR IGNORE INTO festival_campaigns (slug,name) VALUES (?,?)", (slug, name))

def scheduler_payload(client):
    ensure_festival_tables(client)
    enabled = bool(client.execute("SELECT enabled FROM festival_scheduler_settings WHERE id=1").rows[0][0])
    records = client.execute("SELECT slug,name,reference_sale_date,enabled,campaign_end_date FROM festival_campaigns ORDER BY rowid").rows
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    campaigns=[]
    for slug,name,ref_start,is_enabled,end_date in records:
        start = date.fromisoformat(ref_start)-timedelta(days=1) if ref_start else None
        end = date.fromisoformat(end_date) if end_date else None
        active = bool(enabled and is_enabled and start and end and start <= today <= end)
        reminder = None
        if enabled and is_enabled and start:
            if start == today:
                reminder = f"Turn on your {name} Code Seller sale today."
            elif today < start <= today + timedelta(days=7):
                reminder = f"Your {name} Code Seller sale starts {start.isoformat()}."
        campaigns.append({"slug":slug,"name":name,"reference_sale_start":ref_start,"reference_sale_date":ref_start,"campaign_start_date":start.isoformat() if start else None,"campaign_end_date":end_date,"enabled":bool(is_enabled),"active":active,"notification":reminder})
    return {"enabled":enabled,"campaigns":campaigns,"today":today.isoformat()}

def active_campaign(client, today=None):
    """Return at most one enabled campaign; a campaign runs from one day before its reference start through its end date."""
    payload = scheduler_payload(client)
    today = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()
    active = [c for c in payload["campaigns"] if c["enabled"] and payload["enabled"] and c["campaign_start_date"] and c["campaign_end_date"] and date.fromisoformat(c["campaign_start_date"]) <= today <= date.fromisoformat(c["campaign_end_date"])]
    return active[0] if active else None

def apply_campaign(product, campaign):
    result = dict(product)
    original = int(result.get("price") or 0)
    result["original_price"] = original
    result["festival_discount_percent"] = 30 if campaign and original > 0 else 0
    result["festival_campaign"] = campaign["name"] if campaign and original > 0 else None
    result["price"] = (original * 70 + 50) // 100 if campaign and original > 0 else original
    return result
