from flask import Blueprint, jsonify, request
from middleware.auth import require_admin
from auth.jwt import verify_token
from services.product_service import ProductService
bp = Blueprint("products", __name__)

def _optional_customer_id():
    header=request.headers.get("Authorization","")
    if not header.startswith("Bearer "):
        return None
    try:
        claims=verify_token(header[7:].strip())
        return claims.get("sub") if claims.get("role")=="customer" else None
    except Exception:
        return None

@bp.get("/")
def list_products():
    try:
        return jsonify(success=True, result=ProductService.list_products(_optional_customer_id())), 200
    except Exception:
        return jsonify(success=False, error="Could not load products"), 503
@bp.get("/<product_id>")
def product_detail(product_id):
    try:
        product = ProductService.get_product(product_id, _optional_customer_id())
        if product is None:
            return jsonify(success=False, error="Product not found"), 404
        return jsonify(success=True, result=product), 200
    except Exception:
        return jsonify(success=False, error="Could not load product"), 503
@bp.post("/")
@require_admin
def create_product():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, error="A JSON object is required"), 400
    try:
        product = ProductService.create_product(data)
        return jsonify(success=True, result=product), 201
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception:
        return jsonify(success=False, error="Could not create product"), 503
