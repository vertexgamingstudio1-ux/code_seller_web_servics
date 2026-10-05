from flask import Blueprint, jsonify, request
from services.customer_service import CustomerService
auth_bp = Blueprint("auth", __name__)
@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    return jsonify({
        "success": True,
        "result": CustomerService.register(data)
    }), 201
@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    return jsonify({
        "success": True,
        "result": CustomerService.login(data)
    })
@auth_bp.post("/logout")
def logout():
    return jsonify({
        "success": True,
        "message": "Logged out"
    })
@auth_bp.get("/status")
def auth_status():
    return jsonify({
        "success": True,
        "area": "auth",
        "status": "available"
    })
