import requests
from services.otp_service import generate_otp,expiry
def send_msg91_otp(phone,otp):
    from config import Config
    if not Config.MSG91_AUTH_KEY or not Config.MSG91_TEMPLATE_ID:
        raise RuntimeError("MSG91 OTP configuration is missing")
    r=requests.post(
        "https://control.msg91.com/api/v5/otp",
        headers={"authkey":Config.MSG91_AUTH_KEY,"Content-Type":"application/json"},
        json={"template_id":Config.MSG91_TEMPLATE_ID,"mobile":phone,"otp":otp},
        timeout=15)
    r.raise_for_status()
    return r.json()
def create_and_send(phone):
    return generate_otp(),expiry()
