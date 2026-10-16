import os
from dotenv import load_dotenv
load_dotenv()
class Config:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "Code Seller API")
    SERVICE_VERSION = os.getenv("SERVICE_VERSION", "4.0.0")
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "10000"))
    DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
    TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY", "")
    MSG91_TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID", "")
