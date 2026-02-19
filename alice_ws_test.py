"""
🧪 Alice Blue WebSocket Test
Simple test to verify WebSocket connection and live data flow
"""

from pya3 import Aliceblue
import pyotp
import os
import time
from dotenv import load_dotenv

# Load credentials
load_dotenv()

print("=" * 70)
print("🧪 ALICE BLUE WEBSOCKET TEST")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: AUTHENTICATE
# ─────────────────────────────────────────────────────────────────────────────

print("\n[1/4] Authenticating with Alice Blue...")

user_id = os.getenv("ALICEBLUE_USER_ID")
api_key = os.getenv("ALICEBLUE_API_KEY")
totp_secret = os.getenv("ALICEBLUE_TOTP_SECRET")

if not all([user_id, api_key, totp_secret]):
    print("❌ Missing credentials in .env file")
    exit(1)

try:
    otp = pyotp.TOTP(totp_secret).now()
    print(f"   Generated OTP: {otp}")
    
    alice = Aliceblue(user_id=user_id, api_key=api_key)
    session_id = alice.get_session_id(otp)
    
    if not session_id:
        print("❌ Login failed - Invalid session")
        exit(1)
    
    print("✅ Login successful")
    
except Exception as e:
    print(f"❌ Authentication error: {e}")
    exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: SETUP CALLBACKS
# ─────────────────────────────────────────────────────────────────────────────

print("\n[2/4] Setting up WebSocket callbacks...")

tick_count = 0
is_connected = False

def socket_open():
    """Called when WebSocket connects"""
    global is_connected
    is_connected = True
    print("✅ WebSocket Connected")
    
    # Subscribe to NIFTY 50 (token: 26000)
    nifty = alice.get_instrument_by_token("NSE", 26000)
    try:
        from alice_blue import LiveFeedType
    except Exception:
        try:
            from pya3 import LiveFeedType
        except Exception:
            LiveFeedType = None

    if LiveFeedType:
        try:
            alice.subscribe(nifty, LiveFeedType.MARKET_DATA)
        except TypeError:
            try:
                alice.subscribe(nifty)
            except Exception as e:
                print(f"⚠️ Subscription failed: {e}")
    else:
        try:
            alice.subscribe(nifty)
        except Exception as e:
            print(f"⚠️ Subscription failed: {e}")
    print("📊 Subscribed to NIFTY 50")

def socket_close():
    """Called when WebSocket closes"""
    global is_connected
    is_connected = False
    print("❌ WebSocket Closed")

def socket_error(message):
    """Called on WebSocket error"""
    print(f"⚠️  WebSocket Error: {message}")

def feed_data(message):
    """Called for each live tick"""
    global tick_count
    if not isinstance(message, dict):
        # Ignore non-dictionary messages (control packets, strings)
        return

    tick_count += 1
    
    symbol = message.get("ts", "NIFTY50") # Fallback to NIFTY50 for test
    price = message.get("lp", 0)
    volume = message.get("v", 0)
    
    if tick_count % 10 == 0:  # Log every 10th tick
        print(f"📈 TICK #{tick_count}: {symbol} @ {price:.2f} (Vol: {volume})")

print("✅ Callbacks ready")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: START WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

print("\n[3/4] Starting WebSocket...")

try:
    alice.start_websocket(
        socket_open_callback=socket_open,
        socket_close_callback=socket_close,
        socket_error_callback=socket_error,
        subscription_callback=feed_data,
        run_in_background=True
    )
    print("✅ WebSocket started in background")
    
except Exception as e:
    print(f"❌ WebSocket start error: {e}")
    exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: WAIT FOR DATA
# ─────────────────────────────────────────────────────────────────────────────

print("\n[4/4] Waiting for live data (60 seconds)...")
print("─" * 70)

start_time = time.time()
prev_tick_count = 0

while time.time() - start_time < 60:
    elapsed = int(time.time() - start_time)
    
    # Print status every 10 seconds
    if elapsed % 10 == 0 and elapsed > 0:
        status = "🔌 CONNECTED" if is_connected else "❌ DISCONNECTED"
        ticks_per_sec = (tick_count - prev_tick_count) / 10 if prev_tick_count > 0 else 0
        print(f"{status} | Ticks: {tick_count} | Rate: {ticks_per_sec:.1f}/sec")
        prev_tick_count = tick_count
    
    time.sleep(1)

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─" * 70)
print("📊 TEST SUMMARY")
print("─" * 70)

if tick_count > 0:
    print(f"✅ TEST PASSED")
    print(f"   Total ticks received: {tick_count}")
    print(f"   Average rate: {tick_count/60:.1f} ticks/second")
    print(f"   WebSocket: {'CONNECTED' if is_connected else 'DISCONNECTED'}")
else:
    print(f"⚠️  No ticks received")
    print(f"   This could mean:")
    print(f"   1. Market is closed (9:15 AM - 3:30 PM IST only)")
    print(f"   2. WebSocket connection failed")
    print(f"   3. Subscription didn't work")
    print(f"   4. API permissions issue")

print("\n" + "=" * 70)
