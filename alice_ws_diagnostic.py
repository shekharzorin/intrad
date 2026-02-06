"""
🔍 Alice Blue WebSocket Diagnostic Test
Enhanced test with detailed debugging
"""

from pya3 import Aliceblue
import pyotp
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("🔍 ALICE BLUE WEBSOCKET DIAGNOSTIC TEST")
print("=" * 70)

# Check current time
ist_time = datetime.now()
print(f"\n⏰ Current Time (IST): {ist_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"   Market Hours: 09:15 - 15:30 (Mon-Fri)")

if ist_time.weekday() >= 5:
    print(f"   ⚠️  WARNING: Today is a weekend!")

is_market_open = 9 <= ist_time.hour < 15 or (ist_time.hour == 15 and ist_time.minute < 30)
if not is_market_open:
    print(f"   ⚠️  WARNING: Market is CLOSED")
else:
    print(f"   ✅ Market is OPEN")

# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────

print("\n[1/5] Authenticating...")

user_id = os.getenv("ALICEBLUE_USER_ID")
api_key = os.getenv("ALICEBLUE_API_KEY")
totp_secret = os.getenv("ALICEBLUE_TOTP_SECRET")

if not user_id:
    print("❌ ALICEBLUE_USER_ID not in .env")
    exit(1)
if not api_key:
    print("❌ ALICEBLUE_API_KEY not in .env")
    exit(1)
if not totp_secret:
    print("❌ ALICEBLUE_TOTP_SECRET not in .env")
    exit(1)

print(f"   User ID: {user_id[:5]}***")
print(f"   API Key: {api_key[:5]}***")

try:
    otp = pyotp.TOTP(totp_secret).now()
    print(f"   OTP: {otp}")
    
    alice = Aliceblue(user_id=user_id, api_key=api_key)
    session_id = alice.get_session_id(otp)
    
    if not session_id:
        print("❌ Session ID not returned")
        exit(1)
    
    print(f"✅ Login OK - Session: {str(session_id)[:10]}...")
    
except Exception as e:
    print(f"❌ Login failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# CHECK INSTRUMENT
# ─────────────────────────────────────────────────────────────────────────────

print("\n[2/5] Checking instrument...")

try:
    nifty = alice.get_instrument_by_token("NSE", 26000)
    print(f"✅ Got instrument: {nifty}")
except Exception as e:
    print(f"⚠️  Could not get instrument: {e}")
    nifty = None

# ─────────────────────────────────────────────────────────────────────────────
# SETUP CALLBACKS WITH DEBUGGING
# ─────────────────────────────────────────────────────────────────────────────

print("\n[3/5] Setting up callbacks...")

state = {
    "connected": False,
    "tick_count": 0,
    "last_tick_time": None,
    "first_tick_time": None
}

def socket_open():
    print("   → socket_open() called")
    state["connected"] = True
    state["connected_time"] = time.time()
    print("✅ WebSocket opened")
    
    if nifty:
        try:
            print("   → Subscribing to NIFTY...")
            try:
                from alice_blue import LiveFeedType
            except Exception:
                try:
                    from pya3 import LiveFeedType
                except Exception:
                    LiveFeedType = None

            alice.subscribe([nifty])
            print("   ✅ Subscribed to NIFTY")

            reliance = alice.get_instrument_by_symbol("NSE", "RELIANCE")
            if reliance:
                 alice.subscribe([reliance], LiveFeedType.MARKET_DATA)
                 print("   ✅ Subscribed to RELIANCE")
        except Exception as e:
            print(f"⚠️  Subscribe error: {e}")

def socket_close():
    print("   → socket_close() called")
    state["connected"] = False
    print("❌ WebSocket closed")

def socket_error(msg):
    print(f"   → socket_error() called: {msg}")
    print(f"⚠️  WebSocket error: {msg}")

def feed_data(msg):
    state["tick_count"] += 1
    if state["first_tick_time"] is None:
        state["first_tick_time"] = time.time()
    state["last_tick_time"] = time.time()
    
    if state["tick_count"] % 10 == 0:
        print(f"   → feed_data() #{state['tick_count']}")

print("✅ Callbacks defined")

# ─────────────────────────────────────────────────────────────────────────────
# START WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

print("\n[4/5] Starting WebSocket...")

try:
    print("   → Calling start_websocket()...")
    alice.start_websocket(
        socket_open_callback=socket_open,
        socket_close_callback=socket_close,
        socket_error_callback=socket_error,
        subscription_callback=feed_data,
        run_in_background=True
    )
    print("✅ start_websocket() returned")
    
except Exception as e:
    print(f"❌ start_websocket() error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# WAIT AND MONITOR
# ─────────────────────────────────────────────────────────────────────────────

print("\n[5/5] Monitoring (60 seconds)...")
print("─" * 70)

for i in range(60):
    time.sleep(1)
    
    status = "🔌 CONNECTED" if state["connected"] else "❌ DISCONNECTED"
    print(f"{status} | Ticks: {state['tick_count']}")
    
    if i == 5 and state["tick_count"] == 0:
        print("   ℹ️  No ticks in 5 seconds - checking if callback was called...")
    
    if state["tick_count"] > 100:
        print("   ✅ Good data flow - stopping test")
        break

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─" * 70)
print("📊 TEST SUMMARY")
print("─" * 70)

print(f"✅ Authentication: PASSED")
print(f"✅ WebSocket: {'CONNECTED' if state['connected'] else 'NOT CONNECTED'}")
print(f"📊 Ticks received: {state['tick_count']}")

if state["tick_count"] > 0:
    elapsed = state["last_tick_time"] - state["first_tick_time"]
    rate = state["tick_count"] / elapsed if elapsed > 0 else 0
    print(f"📈 Data rate: {rate:.1f} ticks/second")
    print(f"✅ WEBSOCKET WORKING!")
else:
    print(f"❌ No data received")
    print(f"   Possible causes:")
    print(f"   1. Market closed (not 09:15-15:30 IST)")
    print(f"   2. socket_open() callback never called")
    print(f"   3. Subscription failed")
    print(f"   4. No data available for token")

print("\n" + "=" * 70)
