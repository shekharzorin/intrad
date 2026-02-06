
"""
ANTI-GRAVITY AGENT - PROFESSIONAL HYBRID LIVE MARKET ENGINE
===========================================================
Strict Requirements:
1. NIFTY 50, BANK NIFTY: WS (Primary) / REST (Failover after 2s)
2. SENSEX: REST ONLY (Polling 500-1000ms)
3. COMMODITY (MCX): Hybrid WS/REST (Polling 500-1000ms)
4. Independent update cycles for ALL instruments.
5. Strict Format: 📊 HH:MM:SS | INSTRUMENT : LAST_PRICE | Vol: VOLUME | Src: WS/REST
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

# Instrument Mapping
# Mode determines the operational behavior
INDICES = {
    "NIFTY 50": {"exchange": "NSE", "token": 26000, "mode": "HYBRID"},
    "BANK NIFTY": {"exchange": "NSE", "token": 26009, "mode": "HYBRID"},
    "SENSEX": {"exchange": "BSE", "token": 30, "mode": "REST_LIVE"}
}

COMMODITIES_SYMBOLS = {
    "GOLD MCX": "GOLD",
    "SILVER MCX": "SILVER",
    "CRUDEOIL MCX": "CRUDEOIL"
}
COMMODITY_TOKENS = {} # {token: display_name}

# State Management
last_tick_time = {}   # {name: unix_timestamp}
last_printed_price = {} # {name: last_price}
lock = threading.Lock()

# ---------------- PATCHED CLIENT ---------------- #
class AliceBlueProfessionalEngine(Aliceblue):
    def start_websocket(self, socket_open_callback=None, socket_close_callback=None, socket_error_callback=None,
                        subscription_callback=None, run_in_background=False):
        
        self._Aliceblue__on_open = socket_open_callback
        self._Aliceblue__on_disconnect = socket_close_callback
        self._Aliceblue__on_error = socket_error_callback
        self._Aliceblue__subscribe_callback = subscription_callback
        
        session_id = self.session_id
        if not session_id: return

        sha256_encryption1 = hashlib.sha256(session_id.encode('utf-8')).hexdigest()
        self.ENC = hashlib.sha256(sha256_encryption1.encode('utf-8')).hexdigest()

        try: self.invalid_sess(session_id)
        except: pass
        try: self.createSession(session_id)
        except: pass

        self._Aliceblue__stop_event = threading.Event()
        ws_url = "wss://ws1.aliceblueonline.com/NorenWS/"
        
        self.ws = websocket.WebSocketApp(ws_url,
                                         on_open=self.on_open,
                                         on_message=self.on_message,
                                         on_close=self.on_close,
                                         on_error=self.on_error)

        if run_in_background:
            t = threading.Thread(target=self._Aliceblue__ws_run_forever)
            t.daemon = True
            t.start()
        else:
            self._Aliceblue__ws_run_forever()

# ---------------- CORE LOGIC ---------------- #

def is_market_open():
    """Checks if Indian Market is currently open (09:15 - 15:30 IST)"""
    now = datetime.datetime.now()
    if now.weekday() > 4: return False
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_start <= now <= market_end

def emit_tick(instrument, price, volume, source):
    """Prints the tick if the price has changed"""
    try:
        new_price = float(price)
        if new_price == 0: return

        with lock:
            if last_printed_price.get(instrument) == new_price:
                return # Skip redundant updates
            last_printed_price[instrument] = new_price
            last_tick_time[instrument] = time.time()

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        v_float = float(volume) if volume else 0.0
        vol_str = f"{v_float:.1f}" if v_float > 0 else "0.0"
        
        # Align Output
        print(f"📊 {ts} | {instrument:<10} : {new_price:<10.2f} | Vol: {vol_str:<8} | Src: {source}")
    except:
        pass

def handle_ws_message(message):
    try:
        data = json.loads(message) if isinstance(message, str) else message
        token = str(data.get('tk'))
        lp = data.get('lp')
        v = data.get('v', 0)
        
        if lp is None or float(lp) == 0: return

        name = None
        # Check Indices (Hybrid)
        for k, v_meta in INDICES.items():
            if v_meta.get('mode') == "HYBRID" and str(v_meta['token']) == token:
                name = k
                break
        
        # Check Commodities
        if not name:
            name = COMMODITY_TOKENS.get(token)
            
        if name:
            emit_tick(name, lp, v, "WS")
    except:
        pass

def rest_poller_worker(alice, name, exchange, token, interval):
    """Independent worker thread for REST updates"""
    is_hybrid = False
    if name in INDICES and INDICES[name]['mode'] == "HYBRID":
        is_hybrid = True
    elif name.endswith("MCX"):
        is_hybrid = True # Commodities are hybrid

    while True:
        try:
            should_poll = False
            
            if not is_hybrid:
                # Direct REST (SENSEX)
                should_poll = True
            else:
                # Hybrid Logic: Check if WS has been silent for 2 seconds
                with lock:
                    if time.time() - last_tick_time.get(name, 0) > 2.0:
                        should_poll = True

            if should_poll:
                inst = alice.get_instrument_by_token(exchange, token)
                res = alice.get_scrip_info(inst)
                if res and res.get('stat') == 'Ok':
                    lp = res.get('LTP', 0)
                    v = res.get('v', 0)
                    if float(lp) > 0:
                        emit_tick(name, lp, v, "REST")
        except:
            pass
        time.sleep(interval)

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    if not is_market_open():
        print("⚠️ Market Closed — Live data available 09:15–15:30 IST")
        exit()

    print("🚀 Anti-Gravity Agent [HYBRID ARCHITECTURE] Starting...")
    
    try:
        alice = AliceBlueProfessionalEngine(user_id=USER_ID, api_key=API_KEY)
        alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
        print("✅ Login Successful")
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        exit(1)

    print("🔧 [Hybrid] Initializing WebSocket Session...")

    # Log Pollers
    for name in INDICES: print(f"🔄 [REST] Poller Started: {name}")
    print("🔄 [REST] Poller Started: COMMODITY")

    # 1. Resolve & Start Indices Pollers
    for name, meta in INDICES.items():
        last_tick_time[name] = 0
        last_printed_price[name] = 0
        # SENSEX: 0.5s, others 1s
        delay = 0.5 if name == "SENSEX" else 1.0
        t = threading.Thread(target=rest_poller_worker, args=(alice, name, meta['exchange'], meta['token'], delay))
        t.daemon = True
        t.start()

    # 2. Resolve & Start Commodity Pollers (Independent for each)
    for display_name, search_sym in COMMODITIES_SYMBOLS.items():
        try:
            inst = alice.get_instrument_by_symbol("MCX", search_sym)
            if inst:
                COMMODITY_TOKENS[str(inst.token)] = display_name
                last_tick_time[display_name] = 0
                last_printed_price[display_name] = 0
                # Commodity: 0.7s independent polling for each
                t = threading.Thread(target=rest_poller_worker, args=(alice, display_name, "MCX", inst.token, 0.7))
                t.daemon = True
                t.start()
        except:
            pass

    print("🔗 Connecting to WebSocket Server...")

    def on_ws_open(ws):
        subs = []
        for name, meta in INDICES.items():
            if meta.get('mode') == "HYBRID":
                subs.append(alice.get_instrument_by_token(meta['exchange'], meta['token']))
        for token_str, name in COMMODITY_TOKENS.items():
            subs.append(alice.get_instrument_by_token("MCX", int(token_str)))
        alice.subscribe(subs)

    # Start WebSocket
    try:
        alice.start_websocket(
            socket_open_callback=on_ws_open,
            subscription_callback=handle_ws_message,
            run_in_background=False
        )
    except KeyboardInterrupt:
        print("\n🛑 Shutting down Engine...")
