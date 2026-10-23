from flask import Blueprint, jsonify
from services.finance_service import FinanceService
finance_bp = Blueprint("finance", __name__)
@finance_bp.get("/summary")
def finance_summary():
    return jsonify({"success": True, "result": FinanceService.summary()})
@finance_bp.get("/revenue")
def finance_revenue():
    return jsonify({"success": True, "result": FinanceService.revenue()})
@finance_bp.get("/sales")
def finance_sales():
    return jsonify({"success": True, "result": FinanceService.sales()})
@finance_bp.get("/margins")
def finance_margins():
    return jsonify({"success": True, "result": FinanceService.margins()})
