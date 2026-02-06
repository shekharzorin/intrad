
"""
ANTI-GRAVITY AGENT - PROFESSIONAL LIVE MARKET ENGINE V3 [REFINED]
================================================================
Strict Compliance:
1. NIFTY 50, BANK NIFTY: HYBRID (WS Primary)
2. SENSEX: REST ONLY (Polling 1s)
3. MCX (GOLD, SILVER, CRUDEOIL, NATGASMINI): HYBRID
4. Status Logging only on Price Change.
5. Format: 📊 HH:MM:SS | INSTRUMENT | LAST_PRICE | Vol: VOLUME | Src: WS/REST
"""

import os
import time
import json
import threading
import hashlib
import datetime
import pyotp
from dotenv import load_dotenv
import websocket
from pya3 import Aliceblue, Instrument

# ---------------- CONFIGURATION ---------------- #
load_dotenv()

API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

# Configured Instruments
INDICES = {
    "NIFTY 50":   {"exchange": "NSE", "token": 26000, "mode": "HYBRID"},
    "BANK NIFTY": {"exchange": "NSE", "token": 26009, "mode": "HYBRID"},
    "SENSEX":     {"exchange": "BSE", "token": 1,     "mode": "REST_ONLY"}
}

COMMODITY_SYMBOLS = ["GOLD", "SILVER", "CRUDEOIL", "NATGASMINI"]
RESOLVED_TOKENS = {} # {token_str: display_name}
RESOLVED_INSTRUMENTS = {}

# State Management
last_printed_price = {}
last_tick_time = {}
lock = threading.Lock()

# ---------------- CORE LOGIC ---------------- #

def is_market_open():
    now = datetime.datetime.now()
    if now.weekday() > 4: return False
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_start <= now <= market_end

def emit_tick(name, price, vol, source):
    try:
        p = float(price)
        if p <= 0: return
        
        with lock:
            if last_printed_price.get(name) == p:
                return
            last_printed_price[name] = p
            last_tick_time[name] = time.time()

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        v_float = float(vol) if vol else 0.0
        vol_str = f"{v_float:.1f}" if v_float > 0 else "0.0"
        
        print(f"📊 {ts} | {name:<10} | {p:>10.2f} | Vol: {vol_str:<8} | Src: {source}")
    except:
        pass

# ---------------- PATCHED CLIENT ---------------- #
class AliceBlueV3Engine(Aliceblue):
    """Refined Engine with robust WebSocket/REST handling"""
    def start_websocket_v3(self, socket_open_callback=None, subscription_callback=None):
        session_id = self.session_id
        if not session_id: return
        
        # Security Handshake
        sha256_encryption1 = hashlib.sha256(session_id.encode('utf-8')).hexdigest()
        self.ENC = hashlib.sha256(sha256_encryption1.encode('utf-8')).hexdigest()

        try: self.invalid_sess(session_id); self.createSession(session_id)
        except: pass

        def on_open(ws):
            print("🔗 Connecting to WebSocket Server...")
            if socket_open_callback: socket_open_callback(ws)

        def on_msg(ws, msg):
            if subscription_callback: subscription_callback(msg)

        def on_error(ws, err): pass
        def on_close(ws, close_status_code, close_msg): pass

        self.ws = websocket.WebSocketApp("wss://ws1.aliceblueonline.com/NorenWS/",
                                         on_open=on_open,
                                         on_message=on_msg,
                                         on_error=on_error,
                                         on_close=on_close)
        self.ws.run_forever()

def rest_worker(alice, name, exchange, token):
    is_hybrid = (name != "SENSEX")
    while True:
        try:
            should_poll = False
            if name == "SENSEX":
                should_poll = True
            else:
                with lock:
                    if time.time() - last_tick_time.get(name, 0) > 2.0:
                        should_poll = True
            
            if should_poll:
                inst = RESOLVED_INSTRUMENTS.get(name)
                if not inst:
                    inst = alice.get_instrument_by_token(exchange, token)
                    RESOLVED_INSTRUMENTS[name] = inst
                
                res = alice.get_scrip_info(inst)
                if res and res.get('stat') == 'Ok':
                    emit_tick(name, res.get('LTP', 0), res.get('v', 0), "REST")
        except: pass
        time.sleep(1.0)

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    if not is_market_open():
        print("⚠️ Market Closed — Live data available 09:15–15:30 IST")
        exit()

    print("🚀 Anti-Gravity Agent [HYBRID ARCHITECTURE] Starting...")

    try:
        alice = AliceBlueV3Engine(user_id=USER_ID, api_key=API_KEY)
        alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
        print("✅ Login Successful")
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        exit(1)

    print("🔧 [Hybrid] Initializing WebSocket Session...")
    
    # 1. Start Index Pollers
    for name, m in INDICES.items():
        print(f"🔄 [REST] Poller Started: {name}")
        last_tick_time[name] = 0
        t = threading.Thread(target=rest_worker, args=(alice, name, m['exchange'], m['token']))
        t.daemon = True
        t.start()
        if m['mode'] == "HYBRID":
            RESOLVED_TOKENS[str(m['token'])] = name

    # 2. Resolve Commodities & Start Pollers
    ws_subs = []
    # Add Hybrid Index tokens to WS subs
    ws_subs.append(alice.get_instrument_by_token("NSE", 26000))
    ws_subs.append(alice.get_instrument_by_token("NSE", 26009))

    print("🔄 [REST] Poller Started: COMMODITY")
    for sym in COMMODITY_SYMBOLS:
        try:
            inst = alice.get_instrument_by_symbol("MCX", sym)
            if inst:
                RESOLVED_TOKENS[str(inst.token)] = sym
                RESOLVED_INSTRUMENTS[sym] = inst
                last_tick_time[sym] = 0
                ws_subs.append(inst)
                t = threading.Thread(target=rest_worker, args=(alice, sym, "MCX", inst.token))
                t.daemon = True
                t.start()
        except: pass

    # 3. WS Handlers
    def handle_msg(msg):
        try:
            d = json.loads(msg) if isinstance(msg, str) else msg
            tk = str(d.get('tk'))
            lp = d.get('lp')
            if lp and tk in RESOLVED_TOKENS:
                emit_tick(RESOLVED_TOKENS[tk], lp, d.get('v', 0), "WS")
        except: pass

    def handle_open(ws):
        alice.subscribe(ws_subs)

    # Start Engine
    try:
        alice.start_websocket_v3(socket_open_callback=handle_open, subscription_callback=handle_msg)
    except KeyboardInterrupt:
        print("\n🛑 Engine Stopped.")
