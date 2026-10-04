import os
from dotenv import load_dotenv
load_dotenv()
class Config:
    SERVICE_NAME = os.getenv(
        "SERVICE_NAME",
        "Code Seller Web Service"
    )
    SERVICE_VERSION = os.getenv(
        "SERVICE_VERSION",
        "1.0.0"
    )
    HOST = os.getenv(
        "HOST",
        "0.0.0.0"
    )
    PORT = int(os.getenv(
        "PORT",
        "5000"
    ))
    DEBUG = os.getenv(
        "DEBUG",
        "false"
    ).lower() == "true"
    API_PREFIX = "/api"
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "*"
    )
