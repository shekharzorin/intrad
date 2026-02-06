from pya3 import Aliceblue
import time
from collections import deque
import pyotp
import os
from dotenv import load_dotenv

# ---------------- CONFIG ---------------- #
load_dotenv()

API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

SYMBOL = "Nifty 50" # Changed from NIFTY to match Alice Blue instrument name
EXCHANGE = "NSE"
WINDOW = 20  # rolling window

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

    # Logic: 
    # Buy if price is significantly above average (>0.3) AND volume is spiking (>1.5x average)
    # Sell if price is significantly below average (<-0.3) AND volume is spiking (>1.5x average)
    
    if price_force > 0.3 and volume_force > 1.5:
        return "🚀 BUY (Anti-Gravity Breakout)"

    if price_force < -0.3 and volume_force > 1.5:
        return "🔻 SELL (Downward Force)"

    return "⚪ HOLD"

# ---------------- SOCKET CALLBACK ---------------- #
def on_tick(ws, tick):
    try:
        # Handle different tick structures (pya3 v2 vs v3)
        # lp = Last Traded Price, v = Volume, ltp/volume used in some versions
        ltp = float(tick.get('lp', tick.get('ltp', 0)))
        vol = float(tick.get('v', tick.get('volume', 0)))

        if ltp == 0: return

        signal = anti_gravity_logic(ltp, vol)
        if signal and signal != "⚪ HOLD":
            print(f"{SYMBOL} | LTP: {ltp:.2f} | Vol: {vol} | {signal}")
        elif signal:
            # Optional: Uncomment to see heartbeat
            # print(f"{SYMBOL} | LTP: {ltp:.2f} | {signal}")
            pass

    except Exception as e:
        print("Error processing tick:", e)

def on_open(ws):
    print("📡 WebSocket Connected")
    # Subscribe to the instrument
    # LiveFeedType: 1 = COMPACT, 2 = MARKET_DATA. Using 1 (Compact) as per user request (or default)
    alice.subscribe([instrument], live_feed_type=1)

# ---------------- START ---------------- #
if __name__ == "__main__":
    print("🚀 Anti-Gravity Market Agent Initializing...")
    
    if not all([USER_ID, API_KEY, TOTP_SECRET]):
        print("❌ Missing credentials in .env. Please check ALICEBLUE_USER_ID, ALICEBLUE_API_KEY, ALICEBLUE_TOTP_SECRET.")
        exit(1)

    print(f"🔐 Logging in as {USER_ID}...")
    try:
        otp = pyotp.TOTP(TOTP_SECRET).now()
        alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
        session_id = alice.get_session_id(otp)
        print("✅ Login Successful")
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        exit(1)

    print(f"🔍 Getting Instrument: {SYMBOL} ({EXCHANGE})...")
    try:
        instrument = alice.get_instrument_by_symbol(EXCHANGE, SYMBOL)
    except Exception as e:
        print(f"⚠️  Symbol lookup failed: {e}. Trying by Token 26000 (Nifty 50)...")
        try:
            instrument = alice.get_instrument_by_token("NSE", 26000)
        except Exception as e2:
            print(f"❌ Instrument lookup failed: {e2}")
            exit(1)

    if not instrument:
        print("❌ Instrument object is None")
        exit(1)
        
    print(f"✅ Instrumented Found: {instrument.symbol} (Token: {instrument.token})")

    print("📡 Starting Background WebSocket...")
    alice.start_websocket(
        socket_open_callback=on_open,
        subscription_callback=on_tick,
        run_in_background=True
    )

    print("⏳ Agent Running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Agent Stopped.")
