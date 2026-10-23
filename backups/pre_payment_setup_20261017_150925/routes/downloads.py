from flask import Blueprint, jsonify, request
from services.download_service import DownloadService
downloads_bp = Blueprint("downloads", __name__)
@downloads_bp.get("/")
def download_list():
    return jsonify({"success": True, "result": DownloadService.list_downloads()})
@downloads_bp.get("/<download_id>")
def download_detail(download_id):
    return jsonify({"success": True, "result": DownloadService.get_download(download_id)})
@downloads_bp.post("/authorize")
def authorize_download():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "result": DownloadService.authorize(data)})
@downloads_bp.get("/stats")
def download_stats():
    return jsonify({"success": True, "result": DownloadService.stats()})
