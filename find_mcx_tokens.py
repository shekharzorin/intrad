
from pya3 import Aliceblue
import os
import pyotp
from dotenv import load_dotenv

load_dotenv()

def find_mcx_tokens():
    user_id = os.getenv("ALICEBLUE_USER_ID")
    api_key = os.getenv("ALICEBLUE_API_KEY")
    totp_secret = os.getenv("ALICEBLUE_TOTP_SECRET")
    
    alice = Aliceblue(user_id=user_id, api_key=api_key)
    alice.get_session_id(pyotp.TOTP(totp_secret).now())
    
    commodities = ["CRUDEOIL", "NATURALGAS", "GOLD", "SILVER"]
    found = []
    
    print("Searching for current MCX tokens...")
    for comm in commodities:
        try:
            # This search is generic, usually returns a list or first match
            # Some SDKs have search_instruments
            inst = alice.get_instrument_by_symbol("MCX", comm)
            if inst:
                print(f"✅ Found {comm}: {inst.token} ({inst.symbol})")
                found.append({"name": comm, "token": inst.token, "symbol": inst.symbol})
        except:
            print(f"❌ Could not find {comm}")
            
    return found

if __name__ == "__main__":
    find_mcx_tokens()
