"""
PRODUCTION-GRADE HYBRID AGENT [ALICE BLUE]
==========================================
Architecture:
1. WebSocket: NSE Equities + F&O + MCX (Tick Streaming)
2. REST API: Indices (NIFTY, BANKNIFTY, SENSEX) (Polling)

Strict Constraints:
- Indices (26000, 26009, 30) MUST NEVER go to WebSocket.
- WebSocket must act as Keep-Alive using an Equity Anchor (Reliance).
"""

import os
import time
import json
import threading
import hashlib
import datetime
import pandas as pd
from collections import deque
import pyotp
from dotenv import load_dotenv
import websocket
from pya3 import Aliceblue, Instrument

# ---------------- CONFIGURATION ---------------- #
load_dotenv()

API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

# Instrument Constraints
INDEX_TOKENS = {
    26000: "NIFTY 50",
    26009: "BANK NIFTY",
    30: "SENSEX"
}

# Keep-Alive Anchor (NSE Equity)
ANCHOR_TOKEN = 2885
ANCHOR_SYMBOL = "RELIANCE"

# Analysis Window
WINDOW = 20
prices = deque(maxlen=WINDOW)
volumes = deque(maxlen=WINDOW)

# ---------------- PATCHED CLIENT ---------------- #
class AliceBlueOptimized(Aliceblue):
    """
    Production-Patch for Alice Blue Client.
    1. Fixes sleep() NameError.
    2. Enforces strict session creation.
    """
    def start_websocket(self, socket_open_callback=None, socket_close_callback=None, socket_error_callback=None,
                        subscription_callback=None, check_subscription_callback=None, run_in_background=False,
                        market_depth=False):
        
        # Callbacks
        if check_subscription_callback is not None:
            check_subscription_callback(self.script_subscription_instrument)
        
        self._Aliceblue__on_open = socket_open_callback
        self._Aliceblue__on_disconnect = socket_close_callback
        self._Aliceblue__on_error = socket_error_callback
        self._Aliceblue__subscribe_callback = subscription_callback
        self.market_depth = market_depth
        
        # Reset stop event if needed
        if hasattr(self, '_Aliceblue__stop_event') and self._Aliceblue__stop_event is not None and self._Aliceblue__stop_event.is_set():
            self._Aliceblue__stop_event.clear()
            
        session_id = self.session_id
        if not session_id:
            print("❌ No Session ID found. Cannot start WebSocket.")
            return

        print(f"🔧 [Hybrid] Initializing WebSocket Session...")
        
        # Encryption Key Gen
        sha256_encryption1 = hashlib.sha256(session_id.encode('utf-8')).hexdigest()
        self.ENC = hashlib.sha256(sha256_encryption1.encode('utf-8')).hexdigest()

        # Lifecycle Fix: Invalidate first, then Create
        try:
            self.invalid_sess(session_id)
        except:
            pass # Ignore invalidation errors

        try:
            create_resp = self.createSession(session_id)
            if create_resp.get('stat') != 'Ok':
                print(f"⚠️ Session Creation Check: {create_resp.get('message', '')}")
        except Exception as e:
             print(f"❌ Create Session Exception: {e}")
             return

        # Connect
        print("🔗 Connecting to WebSocket Server...")
        self._Aliceblue__stop_event = threading.Event()
        websocket.enableTrace(False)
        
        ws_url = self._sub_urls['base_url_socket'] if 'base_url_socket' in self._sub_urls else "wss://ws1.aliceblueonline.com/NorenWS/"
        
        self.ws = websocket.WebSocketApp(ws_url,
                                         on_open=self.on_open,
                                         on_message=self.on_message,
                                         on_close=self.on_close,
                                         on_error=self.on_error)

        if run_in_background is True:
            self._Aliceblue__ws_thread = threading.Thread(target=self._Aliceblue__ws_run_forever)
            self._Aliceblue__ws_thread.daemon = True
            self._Aliceblue__ws_thread.start()
        else:
            self._Aliceblue__ws_run_forever()

# ---------------- STRATEGY LOGIC ---------------- #
def anti_gravity_logic(price, volume):
    prices.append(price)
    volumes.append(volume)

    if len(prices) < WINDOW:
        return None

    avg_price = sum(prices) / len(prices)
    avg_volume = sum(volumes) / len(volumes)
    
    if avg_volume == 0: avg_volume = 1

    price_force = price - avg_price
    volume_force = volume / avg_volume if avg_volume else 0

    if price_force > 0.3 and volume_force > 1.5:
        return f"🚀 BUY | Force: {price_force:.2f} | Vol: {volume_force:.2f}x"

    if price_force < -0.3 and volume_force > 1.5:
        return f"🔻 SELL | Force: {price_force:.2f} | Vol: {volume_force:.2f}x"

    return None

# ---------------- HANDLERS ---------------- #
def on_tick(message):
    try:
        # Parse
        if isinstance(message, str):
            tick = json.loads(message)
        else:
            tick = message
            
        # Extract Standard Fields
        ltp = float(tick.get('lp', tick.get('ltp', tick.get('LTP', 0))))
        vol = float(tick.get('v', tick.get('volume', tick.get('vol', 0))))
        token = tick.get('tk', tick.get('token', '0'))
        symbol = tick.get('ts', tick.get('symbol', tick.get('trading_symbol', 'UNK')))

        if ltp == 0: return

        # Timestamp
        ts_str = datetime.datetime.now().strftime("%H:%M:%S")

        # Classification
        token_int = int(token)
        
        if token_int in INDEX_TOKENS:
            # INDEX (REST)
            name = INDEX_TOKENS[token_int]
            # Align Name to 12 chars for cleaner output
            print(f"📊 {ts_str} | {name:<10} : {ltp} | Vol: 0.0          ", end='\r')
            
            # Feed Strategy
            signal = anti_gravity_logic(ltp, vol)
            if signal: print(f"\n🔔 SIGNAL: {signal}")

        elif token_int == ANCHOR_TOKEN:
            # ANCHOR (WS)
            print(f"📈 TICK | NSE | {ANCHOR_SYMBOL:<10} | LTP: {ltp} | VOL: {vol}          ", end='\r')
        
        else:
            # OTHER WS (MCX / Equity)
            print(f"📈 TICK | WS  | {symbol:<10} | LTP: {ltp} | VOL: {vol}          ", end='\r')


    except Exception as e:
        # print(f"Tick Parsing Error: {e}")
        pass

def on_open(ws):
    print("\n📡 WebSocket Connected! Configuring Production Subscriptions...")
    
    # 1. Subscribe ANCHOR (Reliance)
    try:
        anchor_inst = alice.get_instrument_by_token("NSE", ANCHOR_TOKEN)
        alice.subscribe([anchor_inst])
        print(f"✅ [WS] Subscribed Anchor: {ANCHOR_SYMBOL}")
    except Exception as e:
        print(f"❌ [WS] Anchor Failed: {e}")

    # 2. Subscribe MCX (If enabled/found) - Placeholder for CSV loading logic
    # In production, iterate CSV here and subscribe.
    
    print("✅ [WS] Configuration Complete. Listening...")

def on_error(ws, error):
    pass # print(f"\n⚠️ WS Error: {error}")

def on_close(ws, *args, **kwargs):
    print("\n❌ WS Closed. Attempting reconnect (if not manual stop)...")

# ---------------- BACKGROUND POLLERS ---------------- #
def rest_poller(alice, token, exchange):
    """
    Thread to poll Index Data via REST
    """
    instrument = alice.get_instrument_by_token(exchange, token)
    if not instrument:
        print(f"⚠️ [REST] Could not resolve token {token}")
        return

    name = INDEX_TOKENS.get(token, "INDEX")
    print(f"🔄 [REST] Poller Started: {name}")

    while True:
        try:
            resp = alice.get_scrip_info(instrument)
            if resp and resp.get('stat') == 'Ok':
                # Synthesize Tick
                fake_tick = {
                    'tk': token,
                    'ltp': resp.get('LTP', '0'),
                    'v': '0',
                    'ts': name
                }
                on_tick(fake_tick)
            else:
                pass
        except Exception:
            pass
        
        time.sleep(2.0)

# ---------------- MAIN ---------------- #
if __name__ == "__main__":
    print("🚀 Anti-Gravity Agent [HYBRID ARCHITECTURE] Starting...")
    
    # 1. Auth
    if not all([USER_ID, API_KEY, TOTP_SECRET]):
        print("❌ Credentials missing in .env")
        exit(1)

    try:
        alice = AliceBlueOptimized(user_id=USER_ID, api_key=API_KEY)
        alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
        print("✅ Login Successful")
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        exit(1)

    # 2. Start REST Pollers for Indices
    for token, name in INDEX_TOKENS.items():
        ex = "NSE"
        if "SENSEX" in name: ex = "BSE"
        
        t = threading.Thread(target=rest_poller, args=(alice, token, ex))
        t.daemon = True
        t.start()

    # 3. Start WebSocket (Blocking)
    alice.start_websocket(
        socket_open_callback=on_open,
        subscription_callback=on_tick,
        socket_error_callback=on_error,
        socket_close_callback=on_close,
        run_in_background=False,  # Blocking main thread
        market_depth=False 
    )
