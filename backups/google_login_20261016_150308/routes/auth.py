from flask import Blueprint,jsonify,request
import jwt
from auth.jwt import verify_token,create_phone_verification_token,create_customer_token
from services.otp_service import generate_otp,expiry
from services.msg91 import send_msg91_otp
from services.otp_repository import save_otp,verify_saved_otp
from services.customer_auth_service import create_customer,find_customer,password_matches
from db import get_connection
bp=Blueprint("auth",__name__)
@bp.post("/request-otp")
def request_otp():
    data=request.get_json(silent=True) or {}
    phone=str(data.get("phone","")).strip()
    if not phone:return jsonify(success=False,error="Phone is required"),400
    code=generate_otp()
    save_otp(phone,"registration",code,expiry())
    try:result=send_msg91_otp(phone,code)
    except Exception as e:return jsonify(success=False,error=str(e)),500
    return jsonify(success=True,message="OTP sent",provider=result),200
@bp.post("/verify-otp")
def verify_otp():
    data=request.get_json(silent=True) or {}
    phone=str(data.get("phone","")).strip()
    code=str(data.get("otp","")).strip()
    if not phone or not code:return jsonify(success=False,error="Phone and OTP are required"),400
    ok,msg=verify_saved_otp(phone,"registration",code)
    if not ok:return jsonify(success=False,error=msg),400
    return jsonify(success=True,verification_token=create_phone_verification_token(phone)),200
@bp.post("/register")
def register():
    data=request.get_json(silent=True) or {}
    email=str(data.get("email","")).strip()
    phone=str(data.get("phone","")).strip()
    name=str(data.get("display_name","")).strip()
    password=str(data.get("password",""))
    vt=str(data.get("verification_token","")).strip()
    if not all([email,phone,name,password,vt]):return jsonify(success=False,error="Missing required fields"),400
    if len(password)<8:return jsonify(success=False,error="Password must be at least 8 characters"),400
    try:
        claims=verify_token(vt)
        if claims.get("purpose")!="phone_verification" or claims.get("phone")!=phone:
            return jsonify(success=False,error="Invalid phone verification"),400
        user=create_customer(email,phone,name,password)
        return jsonify(success=True,customer=user,token=create_customer_token(user["id"],email)),201
    except ValueError as e:return jsonify(success=False,error=str(e)),409
    except jwt.ExpiredSignatureError:return jsonify(success=False,error="Phone verification expired"),400
    except Exception:return jsonify(success=False,error="Registration failed"),500
@bp.post("/login")
def login():
    data=request.get_json(silent=True) or {}
    email=str(data.get("email","")).strip()
    password=str(data.get("password",""))
    user=find_customer(email)
    if not user or not user["is_active"] or not password_matches(password,user["password_hash"]):
        return jsonify(success=False,error="Invalid email or password"),401
    return jsonify(success=True,customer={k:user[k] for k in ["id","email","phone","display_name","role"]},token=create_customer_token(user["id"],email)),200
