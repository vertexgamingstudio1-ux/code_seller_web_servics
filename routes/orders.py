from flask import Blueprint, jsonify, request
from services.order_service import OrderService
orders_bp = Blueprint("orders", __name__)
@orders_bp.get("/")
def order_list():
    return jsonify({"success": True, "result": OrderService.list_orders()})
@orders_bp.get("/<order_id>")
def order_detail(order_id):
    return jsonify({"success": True, "result": OrderService.get_order(order_id)})
@orders_bp.post("/")
def order_create():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "result": OrderService.create_order(data)}), 201
@orders_bp.post("/<order_id>/cancel")
def order_cancel(order_id):
    return jsonify({"success": True, "result": OrderService.cancel_order(order_id)})
