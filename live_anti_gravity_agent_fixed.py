from pya3 import Aliceblue
import time
import json
from collections import deque
import pyotp
import os
from dotenv import load_dotenv

# ---------------- CONFIG ---------------- #
load_dotenv()

API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

# Use Nifty 50 Token directly for reliability
SYMBOL = "Nifty 50"
TOKEN = 26000
EXCHANGE = "NSE"
WINDOW = 20

# ---------------- STATE ---------------- #
prices = deque(maxlen=WINDOW)
volumes = deque(maxlen=WINDOW)

# ---------------- LOGIC ---------------- #
def anti_gravity_logic(price, volume):
    prices.append(price)
    volumes.append(volume)

    if len(prices) < WINDOW:
        return None

    avg_price = sum(prices) / len(prices)
    avg_volume = sum(volumes) / len(volumes)

    price_force = price - avg_price
    volume_force = volume / avg_volume if avg_volume else 0

    if price_force > 0.3 and volume_force > 1.5:
        return "🚀 BUY (Anti-Gravity Breakout)"

    if price_force < -0.3 and volume_force > 1.5:
        return "🔻 SELL (Downward Force)"

    return "⚪ HOLD"

# ---------------- SOCKET CALLBACK ---------------- #
def on_tick(message):
    try:
        # Pya3 v1.0.30 sends RAW JSON STRING to callback
        if isinstance(message, str):
            tick = json.loads(message)
        else:
            tick = message
            
        # Check if it's a data tick (look for 'lp' or 'ltp')
        # Response format: {'t': 'tk', 'e': 'NSE', 'tk': '26000', 'lp': '23456.75', 'v': '10000', ...}
        # Or {'t': 'tf', ...} for depth
        
        if 'lp' not in tick and 'ltp' not in tick:
             # This might be a heartbeat or ack: {'t': 'ck', 'k': 'OK'}
             if tick.get('t') == 'ck':
                 print(f"✅ Subscription Acknowledged: {tick}")
             return

        ltp = float(tick.get('lp', tick.get('ltp', 0)))
        vol = float(tick.get('v', tick.get('volume', 0)))

        if ltp == 0: return

        signal = anti_gravity_logic(ltp, vol)
        if signal and signal != "⚪ HOLD":
            print(f"{SYMBOL} | LTP: {ltp:.2f} | Vol: {vol} | {signal}")
        elif signal:
            # Heartbeat for debug
            # print(f"{SYMBOL} | LTP: {ltp:.2f} | {signal}")
            pass

    except Exception as e:
        print(f"Error processing tick: {e}")

def on_open(ws):
    print("📡 WebSocket Connected")
    
    # ---------------- CRITICAL FIX ---------------- 
    # 1. Use correct subscribe signature (no live_feed_type)
    # 2. Pass list of instruments
    # 3. Ensure instrument object is valid
    # ----------------------------------------------
    
    try:
        # Re-fetch instrument to be sure (or use global if available)
        # We can construct a minimal dummy instrument if needed, but let's try the real one
        if instrument_obj:
            print(f"📝 Subscribing to {instrument_obj.symbol} ({instrument_obj.token})...")
            # Correct call for pya3 v1.0.30
            alice.subscribe([instrument_obj])
            print("✅ Subscribe command sent.")
        else:
            print("❌ No instrument object to subscribe to.")
            
    except Exception as e:
        print(f"❌ Subscription Failed in on_open: {e}")

def on_error(ws, error):
    print(f"⚠️ WebSocket Error: {error}")

def on_close(ws, *args, **kwargs):
    print("❌ WebSocket Closed")

# ---------------- START ---------------- #
if __name__ == "__main__":
    print("🚀 Anti-Gravity Market Agent Initializing (FIXED)...")
    
    if not all([USER_ID, API_KEY, TOTP_SECRET]):
        print("❌ Missing credentials.")
        exit(1)

    try:
        otp = pyotp.TOTP(TOTP_SECRET).now()
        alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
        session_id = alice.get_session_id(otp)
        if alice.get_session_id()['stat'] != 'Ok':
             print(f"❌ Login stat not Ok: {alice.get_session_id()}")
        print("✅ Login Successful")
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        exit(1)

    # Lookup Instrument
    instrument_obj = None
    try:
        # Try Token Lookup first (most reliable)
        instrument_obj = alice.get_instrument_by_token("NSE", TOKEN)
    except Exception:
        pass
        
    if not instrument_obj:
        print("Trying by symbol...")
        try:
             instrument_obj = alice.get_instrument_by_symbol("NSE", "Nifty 50")
        except:
             pass

    if not instrument_obj:
        print("❌ Could not find Nifty 50 instrument. Exiting.")
        print("DEBUG: Checking Contract Master...")
        # Fallback to manual object creation if needed? No, pya3 needs the object type.
        exit(1)
        
    print(f"✅ Found Instrument: {instrument_obj.symbol} (Token: {instrument_obj.token})")

    print("📡 Starting Background WebSocket...")
    
    # Correct start_websocket call
    # Note: 'socket_data_callback' was wrong. 'subscription_callback' is correct.
    # We pass 'market_depth=False' explicitly.
    alice.start_websocket(
        socket_open_callback=on_open,
        subscription_callback=on_tick,
        socket_error_callback=on_error,
        socket_close_callback=on_close,
        run_in_background=True,
        market_depth=False 
    )

    print("⏳ Agent Running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Agent Stopped.")
