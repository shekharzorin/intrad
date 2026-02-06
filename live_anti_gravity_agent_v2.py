import time
import json
import threading
import websocket
import hashlib
import sys
from collections import deque
import pyotp
import os
from dotenv import load_dotenv
from pya3 import Aliceblue

# ---------------- CONFIG ---------------- #
load_dotenv()
websocket.enableTrace(True)

API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

SYMBOL = "Nifty 50"
TOKEN = 26000
EXCHANGE = "NSE"
WINDOW = 20

# ---------------- STATE ---------------- #
prices = deque(maxlen=WINDOW)
volumes = deque(maxlen=WINDOW)
close_codes = deque(maxlen=5)  # For Loop Detection

# ---------------- LIFECYCLE SAFE CLIENT ---------------- #
class AliceBlueLifecycleSafe(Aliceblue):
    """
    V2 Client adhering to Strict Lifecycle Safety Rules:
    1. Session Creation happens EXACTLY ONCE at bootstrap.
    2. WebSocket connection uses existing session.
    3. Reconnects NEVER trigger session regeneration.
    """
    def __init__(self, user_id, api_key):
        super().__init__(user_id=user_id, api_key=api_key)
        self._session_initialized = False
        self._socket_running = False
        self._lifecycle_lock = threading.Lock()

    def bootstrap_session(self):
        """
        Stage 1: Prepare the session. Must be called ONCE before socket start.
        """
        with self._lifecycle_lock:
            # SAFETY INVARIANT: BANNED if Socket Running
            if self._socket_running:
                 print("🛑 FATAL: Attempted bootstrap_session() while WebSocket is RUNNING.")
                 print("   This violates the strict lifecycle invariant.")
                 os._exit(1) # Hard Kill to prevent loop

            if self._session_initialized:
                print("⚠️ Warning: Session already initialized. Skipping bootstrap.")
                return

            print("🔧 [Lifecycle] Bootstrapping WebSocket Session...")
            session_id = self.session_id
            if not session_id:
                raise Exception("❌ No Setup Session ID found. Login first.")

            # 1. Calc Encryption (Required for Socket Auth)
            sha256_encryption1 = hashlib.sha256(session_id.encode('utf-8')).hexdigest()
            self.ENC = hashlib.sha256(sha256_encryption1.encode('utf-8')).hexdigest()

            # 2. Invalidate Previous Sockets (Cleanup)
            try:
                inv = self.invalid_sess(session_id)
                print(f"   INV_SESS: {inv.get('stat')} ({inv.get('message', '')})")
            except Exception as e:
                print(f"   INV_SESS Ignored: {e}")

            # 3. Create NEW Socket Session
            try:
                crt = self.createSession(session_id)
                print(f"   CREATE_SESS: {crt.get('stat')} ({crt.get('message', '')})")
                if crt.get('stat') != 'Ok':
                     print("   ⚠️ Proceeding despite CreateSession notice...")
            except Exception as e:
                print(f"   CREATE_SESS Error: {e}")
            
            self._session_initialized = True
            print("✅ [Lifecycle] Session Ready. Waiting for Socket Connect...")

    def start_websocket_safe(self, 
                             socket_open_callback=None, 
                             socket_close_callback=None, 
                             socket_error_callback=None,
                             subscription_callback=None, 
                             run_in_background=False):
        """
        Stage 2: PURE Connection. No session logic here.
        """
        if not self._session_initialized:
            raise RuntimeError("❌ Lifecycle Violation: Must call bootstrap_session() before start_websocket_safe()")

        self._Aliceblue__on_open = socket_open_callback
        self._Aliceblue__on_disconnect = socket_close_callback
        self._Aliceblue__on_error = socket_error_callback
        self._Aliceblue__subscribe_callback = subscription_callback
        self.market_depth = False # Hardcoded for safety

        self._Aliceblue__stop_event = threading.Event()
        
        # Determine URL
        ws_url = self._sub_urls.get('base_url_socket', "wss://ws1.aliceblueonline.com/NorenWS/")
        print(f"🔗 Connecting to {ws_url}...")
        
        # Mark Running
        self._socket_running = True

        self.ws = websocket.WebSocketApp(ws_url,
                                         on_open=self.on_open,
                                         on_message=self.on_message,
                                         on_close=self.on_close,
                                         on_error=self.on_error)

        if run_in_background:
            self._Aliceblue__ws_thread = threading.Thread(target=self._Aliceblue__ws_run_forever)
            self._Aliceblue__ws_thread.daemon = True
            self._Aliceblue__ws_thread.start()
        else:
            self._Aliceblue__ws_run_forever()

    # ---------------- OVERRIDE HANDLERS TO FIX SIGNATURES & DEBUG ---------------- #
    def on_open(self, ws):
        print("⚡ [Lifecycle] Socket Connected. Sending Auth...")
        # Copied Auth Logic from pya3
        initCon = {
            "susertoken": self.ENC,
            "t": "c",
            "actid": self.user_id + "_API",
            "uid": self.user_id + "_API",
            "source": "API"
        }
        ws.send(json.dumps(initCon)) # Use ws argument directly
        
        # Call user callback
        if self._Aliceblue__on_open:
            self._Aliceblue__on_open(ws)

    def on_message(self, ws, message):
        # print(f"📩 Raw: {message[:50]}...") # Verbose
        if self._Aliceblue__subscribe_callback:
            self._Aliceblue__subscribe_callback(message)

    def on_error(self, ws, error):
        print(f"❌ [Lifecycle] Error: {error}")
        if self._Aliceblue__on_error:
            self._Aliceblue__on_error(ws, error)

    def on_close(self, ws, close_status_code, close_msg):
        print(f"🔌 [Lifecycle] Closed: {close_status_code} - {close_msg}")
        self._socket_running = False
        if self._Aliceblue__on_disconnect:
            self._Aliceblue__on_disconnect(ws, close_status_code, close_msg)

# ---------------- LOGIC ---------------- #
def anti_gravity_logic(price, volume):
    prices.append(price)
    volumes.append(volume)
    if len(prices) < WINDOW: return None
    
    avg_price = sum(prices) / len(prices)
    avg_vol = sum(volumes) / len(volumes) if len(volumes) > 0 else 1
    if avg_vol == 0: avg_vol = 1
    
    p_force = price - avg_price
    v_force = volume / avg_vol

    if p_force > 0.3 and v_force > 1.5:
        return f"🚀 BUY | Force: {p_force:.2f}"
    return None

# ---------------- HANDLERS ---------------- #
def on_tick(message):
    try:
        if isinstance(message, str): tick = json.loads(message)
        else: tick = message
        
        # Parse
        if 'lp' in tick: ltp = float(tick['lp'])
        elif 'ltp' in tick: ltp = float(tick['ltp'])
        else: return

        vol = float(tick.get('v', tick.get('volume', 0)))
        
        # Logic
        sig = anti_gravity_logic(ltp, vol)
        if sig: print(f"\n🔔 {sig}")
        else: print(f"Tick: {ltp:.2f} | V: {vol}", end='\r')
            
    except Exception:
        pass

def on_open(ws):
    print("\n📡 Socket Opened.")
    # Stability Buffer
    time.sleep(0.5)
    
    # Subscribe
    if instrument_obj:
        print(f"📝 Subscribing to {instrument_obj.symbol}...")
        alice.subscribe([instrument_obj])
    else:
        print("❌ Instrument Missing")

def on_close(ws, close_status_code, close_msg):
    print(f"\n❌ Socket Closed | Code: {close_status_code} | Msg: {close_msg}")
    
    # Loop Detection
    if close_status_code:
        close_codes.append(close_status_code)
    
    if len(close_codes) >= 3 and all(c == 1000 for c in close_codes):
        print("🛑 FATAL: Detected Infinite 'Normal Closure' Loop.")
        print("The server is rejecting the session repeatedly.")
        print("Action: Stopping execution to prevent ban.")
        os._exit(1)

def on_error(ws, error):
    print(f"⚠️ Error: {error}")

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    print("🚀 Anti-Gravity Lifecycle V2 Initializing...")

    # 1. Login
    try:
        alice = AliceBlueLifecycleSafe(USER_ID, API_KEY)
        otp = pyotp.TOTP(TOTP_SECRET).now()
        alice.get_session_id(otp)
        print("✅ Login OK")
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        exit(1)

    # 2. Get Instrument
    try:
        instrument_obj = alice.get_instrument_by_token("NSE", TOKEN)
    except:
        instrument_obj = None # Will fail in on_open check

    if not instrument_obj:
        print("❌ Instrument Failed")
        exit(1)

    # 3. BOOTSTRAP (Once)
    try:
        alice.bootstrap_session()
    except Exception as e:
        print(f"❌ Bootstrap Failed: {e}")
        exit(1)

    # 4. CONNECT
    print("⏳ Starting Safe WebSocket...")
    try:
        alice.start_websocket_safe(
            socket_open_callback=on_open,
            subscription_callback=on_tick,
            socket_close_callback=on_close,
            socket_error_callback=on_error,
            run_in_background=False # Block main thread here
        )
    except KeyboardInterrupt:
        print("🛑 User Stop")
    except Exception as e:
        print(f"🛑 Crash: {e}")
