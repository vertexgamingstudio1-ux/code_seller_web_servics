from flask import Blueprint, jsonify, request`nfrom middleware.admin_auth import require_admin
from pathlib import Path
from werkzeug.utils import secure_filename
import uuid
files_bp = Blueprint("files", __name__)
UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_SINGLE = {
    "py","js","ts","html","css","json","txt","md",
    "java","c","cpp","h","hpp","cs","go","rs","php",
    "sql","sh","yaml","yml","xml"
}
MAX_SINGLE_SIZE = 25 * 1024 * 1024
MAX_PACKAGE_SIZE = 250 * 1024 * 1024
@files_bp.post("/upload")`n@require_admin
def upload_file():
    upload_type = request.form.get("upload_type", "").strip().lower()
    product_id = request.form.get("product_id", "").strip()
    version = request.form.get("version", "").strip()
    file = request.files.get("file")
    if upload_type not in {"single_file", "full_package"}:
        return jsonify({
            "success": False,
            "error": "upload_type must be single_file or full_package"
        }), 400
    if not file or not file.filename:
        return jsonify({
            "success": False,
            "error": "A file is required"
        }), 400
    if not product_id:
        return jsonify({
            "success": False,
            "error": "product_id is required"
        }), 400
    if not version:
        return jsonify({
            "success": False,
            "error": "version is required"
        }), 400
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({
            "success": False,
            "error": "Invalid filename"
        }), 400
    extension = Path(filename).suffix.lower().lstrip(".")
    if upload_type == "full_package":
        if extension != "zip":
            return jsonify({
                "success": False,
                "error": "Full packages must be ZIP files"
            }), 400
        max_size = MAX_PACKAGE_SIZE
    else:
        if extension not in ALLOWED_SINGLE:
            return jsonify({
                "success": False,
                "error": "File type is not allowed for single-file uploads"
            }), 400
        max_size = MAX_SINGLE_SIZE
    file_id = str(uuid.uuid4())
    target_dir = UPLOAD_ROOT / product_id / version
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{file_id}_{filename}"
    file.save(target)
    size = target.stat().st_size
    if size > max_size:
        target.unlink(missing_ok=True)
        return jsonify({
            "success": False,
            "error": "File exceeds the allowed size"
        }), 413
    return jsonify({
        "success": True,
        "status": "stored",
        "file": {
            "id": file_id,
            "product_id": product_id,
            "version": version,
            "upload_type": upload_type,
            "original_name": filename,
            "size": size,
            "extension": extension,
            "storage_path": str(target.relative_to(UPLOAD_ROOT))
        }
    }), 201

