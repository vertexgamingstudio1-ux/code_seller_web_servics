from flask import Blueprint, jsonify, request
from services.version_service import VersionService
versions_bp = Blueprint("versions", __name__)
@versions_bp.get("/")
def version_list():
    return jsonify({"success": True, "result": VersionService.list_versions()})
@versions_bp.get("/<version_id>")
def version_detail(version_id):
    return jsonify({"success": True, "result": VersionService.get_version(version_id)})
@versions_bp.post("/")
def version_create():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "result": VersionService.create_version(data)}), 201
