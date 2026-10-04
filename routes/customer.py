from flask import Blueprint, jsonify, request
from services.customer_service import CustomerService
customer_bp = Blueprint("customer", __name__)
@customer_bp.get("/status")
def customer_status():
    return jsonify({"success": True, "area": "customer", "status": "available"})
@customer_bp.post("/register")
def customer_register():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "result": CustomerService.register(data)}), 201
@customer_bp.post("/login")
def customer_login():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "result": CustomerService.login(data)})
@customer_bp.get("/account")
def customer_account():
    return jsonify({"success": True, "result": CustomerService.account()})
