import os
import pyotp
from pya3 import Aliceblue
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

def test_login():
    print(f"Attempting login for User ID: {USER_ID}")
    try:
        alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
        session_id = alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
        print(f"Login Successful! Session ID: {session_id}")
        
        # Test getting instrument
        inst = alice.get_instrument_by_token('NSE', 26000)
        print(f"Instrument NIFTY: {inst}")
        
        # Test getting scrip info
        res = alice.get_scrip_info(inst)
        import json
        print(f"Scrip Info Result: {json.dumps(res, indent=2)}")
        
    except Exception as e:
        print(f"Login Failed: {str(e)}")

if __name__ == "__main__":
    test_login()pyth
