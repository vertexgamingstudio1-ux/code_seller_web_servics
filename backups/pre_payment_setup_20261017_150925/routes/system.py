from flask import Blueprint,jsonify
from db import database_ready
from config import Config
bp=Blueprint("system",__name__)
@bp.get("/health")
def health():
    database="ok"
    try:database_ready()
    except Exception:database="error"
    return jsonify(status="ok",service=Config.SERVICE_NAME,version=Config.SERVICE_VERSION,database=database)
