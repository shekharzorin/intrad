from pya3 import Aliceblue
import pyotp
import os
from dotenv import load_dotenv


def login():
    load_dotenv()

    USER_ID = os.getenv("ALICEBLUE_USER_ID")
    PASSWORD = os.getenv("ALICEBLUE_PASSWORD")  # not directly used, kept for safety
    API_KEY = os.getenv("ALICEBLUE_API_KEY")
    TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

    if not all([USER_ID, API_KEY, TOTP_SECRET]):
        raise Exception("❌ Missing Alice Blue credentials in .env")

    # Generate fresh OTP
    otp = pyotp.TOTP(TOTP_SECRET).now()
    print("🔐 Generated OTP:", otp)

    # Create client
    alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)

    # Login using OTP
    session_id = alice.get_session_id(otp)

    if session_id:
        print("✅ Alice Blue Login Successful")
    else:
        raise Exception("❌ Login Failed")
    return alice