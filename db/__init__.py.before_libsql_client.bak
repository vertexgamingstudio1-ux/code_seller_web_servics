import os
from dotenv import load_dotenv
from libsql_client import create_client_sync
load_dotenv()
def get_connection():
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
    if not url:
        raise RuntimeError("TURSO_DATABASE_URL is not configured")
    if not token:
        raise RuntimeError("TURSO_AUTH_TOKEN is not configured")
    url = url.replace("libsql://", "https://", 1)
    return create_client_sync(url, auth_token=token)
def database_ready():
    client = get_connection()
    try:
        result = client.execute("SELECT 1")
        return bool(result.rows and result.rows[0][0] == 1)
    finally:
        client.close()
