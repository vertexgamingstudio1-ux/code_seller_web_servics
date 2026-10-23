from flask import Blueprint, jsonify, request
from services.product_service import ProductService
orders_bp = Blueprint("orders", __name__)
@orders_bp.post("/quote")
def order_quote():
    data=request.get_json(silent=True) or {};items=data.get("items")
    if not isinstance(items,list) or not items or len(items)>100:return jsonify(success=False,error="Provide cart items to price"),400
    lines=[]
    try:
        for item in items:
            if not isinstance(item,dict):return jsonify(success=False,error="Invalid cart item"),400
            product=ProductService.get_product(str(item.get("id","")));quantity=int(item.get("quantity",1))
            if not product or quantity<1 or quantity>99:return jsonify(success=False,error="A product or quantity is invalid"),400
            lines.append({"id":product["id"],"name":product["name"],"quantity":quantity,"original_unit_price":product["original_price"],"unit_price":product["price"],"discount_percent":product["festival_discount_percent"],"festival_campaign":product["festival_campaign"],"total":product["price"]*quantity})
        return jsonify(success=True,result={"items":lines,"total":sum(line["total"] for line in lines),"festival_campaign":next((line["festival_campaign"] for line in lines if line["festival_campaign"]),None)})
    except Exception:return jsonify(success=False,error="Could not calculate current cart prices"),503
@orders_bp.get("/")
def order_list(): return jsonify({"success":True,"result":{"status":"pending_database","orders":[],"count":0}})
@orders_bp.get("/<order_id>")
def order_detail(order_id): return jsonify({"success":True,"result":{"status":"pending_database","order_id":order_id}})
@orders_bp.post("/")
def order_create(): return jsonify(success=False,error="Order creation is unavailable until payment processing is configured"),503
@orders_bp.post("/<order_id>/cancel")
def order_cancel(order_id): return jsonify(success=False,error="Order cancellation is unavailable"),503
