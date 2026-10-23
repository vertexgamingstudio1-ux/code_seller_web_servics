import os
import libsql_client
from dotenv import load_dotenv
load_dotenv()
def get_connection():
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
    if not url:
        raise RuntimeError("TURSO_DATABASE_URL is not configured")
    url = url.replace("libsql://", "https://", 1).replace("wss://", "https://", 1)
    return libsql_client.create_client_sync(url, auth_token=token or None)
def database_ready():
    with get_connection() as client:
        result = client.execute("SELECT 1")
        return bool(result.rows and result.rows[0][0] == 1)
