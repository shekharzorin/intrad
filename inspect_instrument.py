from pya3 import Aliceblue
import os
import pyotp
from dotenv import load_dotenv

load_dotenv()

user_id = os.getenv("ALICEBLUE_USER_ID")
api_key = os.getenv("ALICEBLUE_API_KEY")

print(f"Connecting as {user_id}...")
alice = Aliceblue(user_id=user_id, api_key=api_key)
print(f"Session: {alice.get_session_id(pyotp.TOTP(os.getenv('ALICEBLUE_TOTP_SECRET')).now())}")

print("Getting instrument NSE 26000...")
inst = alice.get_instrument_by_token("NSE", 26000)
print(f"Type: {type(inst)}")
print(f"Value: {inst}")

try:
    print(f"Exchange attr: {inst.exchange}")
except Exception as e:
    print(f"Error accessing .exchange: {e}")

print("Getting instrument NSE RELIANCE...")
inst2 = alice.get_instrument_by_symbol("NSE", "RELIANCE")
print(f"Type: {type(inst2)}")
print(f"Value: {inst2}")
