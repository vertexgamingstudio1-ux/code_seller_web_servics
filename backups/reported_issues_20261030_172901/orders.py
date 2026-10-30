from flask import Blueprint, jsonify, request
from middleware.auth import require_customer
from services.order_service import quote, create_order, create_cash_order, start_payment, verify_checkout, handle_webhook, customer_orders, payment_options

orders_bp = Blueprint("orders", __name__)

@orders_bp.post("/<order_id>/receipt")
@require_customer
def upload_manual_payment_receipt(order_id):
    """Store one private receipt for an existing pending UPI order."""
    from db import get_connection
    from services.object_storage import upload, StorageNotConfigured
    reference=str(request.form.get("transaction_reference","")).strip()
    image=request.files.get("screenshot")
    if not reference or len(reference)>160 or not image:
        return jsonify(success=False,error="Provide a transaction reference and payment screenshot"),400
    try:
        with get_connection() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS cash_payment_receipts (
                order_id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,transaction_reference TEXT NOT NULL,
                screenshot_key TEXT NOT NULL,uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(order_id) REFERENCES orders(id))""")
            order=c.execute("SELECT id FROM orders WHERE id=? AND user_id=? AND status='pending_cash'",(order_id,request.auth["sub"])).rows
            exists=c.execute("SELECT 1 FROM cash_payment_receipts WHERE order_id=?",(order_id,)).rows
        if not order:return jsonify(success=False,error="Pending UPI order not found"),404
        if exists:return jsonify(success=False,error="A receipt is already attached to this order. Contact support for corrections."),409
        key=upload(image,prefix="order-receipts",private=True,max_bytes=5*1024*1024)
        with get_connection() as c:
            c.execute("INSERT INTO cash_payment_receipts(order_id,customer_id,transaction_reference,screenshot_key) VALUES(?,?,?,?)",(order_id,request.auth["sub"],reference,key))
        return jsonify(success=True,result={"order_id":order_id,"status":"submitted_for_admin_review"}),201
    except ValueError as exc:return jsonify(success=False,error=str(exc)),400
    except StorageNotConfigured as exc:return jsonify(success=False,error=str(exc)),503
    except Exception:return jsonify(success=False,error="Could not submit payment receipt"),503

@orders_bp.get("/payment-options")
def get_payment_options():
    try:
        return jsonify(success=True, result=payment_options())
    except Exception:
        return jsonify(success=False, error="Could not load payment options"), 503

@orders_bp.post("/quote")
def order_quote():
    try:
        return jsonify(success=True, result=quote((request.get_json(silent=True) or {}).get("items")))
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception:
        return jsonify(success=False, error="Could not calculate current cart prices"), 503

@orders_bp.get("/")
@require_customer
def order_list():
    try: return jsonify(success=True, result=customer_orders(request.auth["sub"]))
    except Exception: return jsonify(success=False,error="Could not load orders"),503

@orders_bp.get("/<order_id>")
@require_customer
def order_detail(order_id):
    try:
        order=next((o for o in customer_orders(request.auth["sub"]) if o["id"]==order_id),None)
        return (jsonify(success=True,result=order),200) if order else (jsonify(success=False,error="Order not found"),404)
    except Exception:return jsonify(success=False,error="Could not load order"),503

@orders_bp.post("/")
@require_customer
def order_create():
    try:
        order_id=create_order(request.auth["sub"],(request.get_json(silent=True) or {}).get("items"))
        return jsonify(success=True,result={"order_id":order_id,"status":"pending"}),201
    except ValueError as exc:return jsonify(success=False,error=str(exc)),400
    except Exception:return jsonify(success=False,error="Could not create order"),503

@orders_bp.post("/cash")
@require_customer
def cash_order_create():
    try:
        items = (request.get_json(silent=True) or {}).get("items")
        priced = quote(items)
        order_id = create_cash_order(request.auth["sub"], items)
        return jsonify(success=True, result={
            "order_id": order_id,
            "status": "pending_cash",
            "total": priced["total"],
            "currency": priced["currency"]
        }), 201
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception:
        return jsonify(success=False, error="Could not create cash order"), 503

@orders_bp.post("/upi")
@require_customer
def upi_order_create():
    """Create a manually verified UPI order using the existing approval lifecycle."""
    try:
        items = (request.get_json(silent=True) or {}).get("items")
        priced = quote(items)
        order_id = create_cash_order(request.auth["sub"], items)
        return jsonify(success=True, result={
            "order_id": order_id,
            "status": "pending_cash",
            "total": priced["total"],
            "currency": priced["currency"],
            "payment_method": "upi"
        }), 201
    except ValueError as exc:
        return jsonify(success=False, error=str(exc)), 400
    except Exception:
        return jsonify(success=False, error="Could not create UPI order"), 503

@orders_bp.post("/online")
@require_customer
def online_checkout_unavailable():
    return jsonify(success=False,error="Online payments are coming soon and are currently unavailable"),503

@orders_bp.post("/<order_id>/payment")
@require_customer
def payment_create(order_id):
    try:return jsonify(success=True,result=start_payment(order_id,request.auth["sub"]))
    except LookupError as exc:return jsonify(success=False,error=str(exc)),404
    except ValueError as exc:return jsonify(success=False,error=str(exc)),400
    except Exception as exc:return jsonify(success=False,error=str(exc) if "not enabled" in str(exc) else "Could not create payment"),503

@orders_bp.post("/<order_id>/verify-payment")
@require_customer
def payment_verify(order_id):
    data=request.get_json(silent=True) or {}
    try:
        verify_checkout(request.auth["sub"],order_id,str(data.get("razorpay_order_id","")),str(data.get("razorpay_payment_id","")),str(data.get("razorpay_signature","")))
        return jsonify(success=True,result={"order_id":order_id,"status":"paid"})
    except ValueError as exc:return jsonify(success=False,error=str(exc)),400
    except Exception:return jsonify(success=False,error="Could not verify payment"),503

@orders_bp.post("/webhook/razorpay")
def razorpay_webhook():
    try:
        result=handle_webhook(request.get_data(cache=False),request.headers.get("X-Razorpay-Signature",""))
        return jsonify(success=True,result=result),200
    except ValueError as exc:return jsonify(success=False,error=str(exc)),400
    except Exception:return jsonify(success=False,error="Could not process payment webhook"),503

@orders_bp.post("/<order_id>/cancel")
@require_customer
def order_cancel(order_id):
    try:
        from db import get_connection
        with get_connection() as c:
            found=c.execute("SELECT id FROM orders WHERE id=? AND user_id=? AND status='pending'",(order_id,request.auth["sub"])).rows
            if not found:return jsonify(success=False,error="Pending order not found"),404
            c.execute("UPDATE orders SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND status='pending'",(order_id,request.auth["sub"]))
        return jsonify(success=True,result={"order_id":order_id,"status":"cancelled"})
    except Exception:return jsonify(success=False,error="Could not cancel order"),503

