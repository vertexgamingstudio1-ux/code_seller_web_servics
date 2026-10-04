from flask import Blueprint, jsonify, request
from services.product_service import ProductService
products_bp = Blueprint("products", __name__)
@products_bp.get("/")
def product_list():
    return jsonify({"success": True, "result": ProductService.list_products()})
@products_bp.get("/<product_id>")
def product_detail(product_id):
    return jsonify({"success": True, "result": ProductService.get_product(product_id)})
@products_bp.post("/")
def product_create():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "result": ProductService.create_product(data)}), 201
@products_bp.put("/<product_id>")
def product_update(product_id):
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "result": ProductService.update_product(product_id, data)})
@products_bp.delete("/<product_id>")
def product_delete(product_id):
    return jsonify({"success": True, "result": ProductService.delete_product(product_id)})
