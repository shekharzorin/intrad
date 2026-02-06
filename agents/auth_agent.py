
from pya3 import Aliceblue
import pyotp
import os
from dotenv import load_dotenv

load_dotenv()

class AuthAgent:
    def login(self):
        user_id = os.getenv("ALICEBLUE_USER_ID")
        api_key = os.getenv("ALICEBLUE_API_KEY")
        totp_secret = os.getenv("ALICEBLUE_TOTP_SECRET")

        if not all([user_id, api_key, totp_secret]):
            raise Exception("❌ Missing Alice Blue credentials in .env")

        otp = pyotp.TOTP(totp_secret).now()
        # Avoid printing emojis to prevent UnicodeEncodeError in some consoles
        print(f"Generated OTP: {otp}")

        alice = Aliceblue(user_id=user_id, api_key=api_key)
        session_res = alice.get_session_id(otp)

        # Validate the response from the broker: ensure a sessionID was returned
        if not session_res or not isinstance(session_res, dict) or not session_res.get("sessionID"):
            emsg = session_res.get("emsg") if isinstance(session_res, dict) else str(session_res)
            raise Exception(f"❌ Login failed: session not established. Server response: {emsg} | full_response={session_res}")

        # Ensure the Aliceblue instance has the session_id set
        if getattr(alice, 'session_id', None) is None:
            alice.session_id = session_res.get('sessionID')

        print("Alice Blue Login Successful")
        return alice
