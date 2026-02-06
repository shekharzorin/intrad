
"""
ANTI-GRAVITY AGENT - LIVE TERMINAL ENGINE
=========================================
Strict Requirements:
1. Fixed lines for: NIFTY 50, BANK NIFTY, SENSEX, GOLD MCX, SILVER MCX, CRUDEOIL, NATGAS.
2. In-place terminal updates.
3. Hybrid WS/REST architecture.
"""

import os
import time
import json
import threading
import hashlib
import datetime
import pyotp
import sys
from dotenv import load_dotenv
import websocket
from pya3 import Aliceblue, Instrument

# ---------------- CONFIGURATION ---------------- #
load_dotenv()

API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

# Instrument Mapping
INSTRUMENTS_CONFIG = {
    "NIFTY 50":    {"exchange": "NSE", "token": 26000, "name": "NIFTY 50"},
    "BANK NIFTY":  {"exchange": "NSE", "token": 26009, "name": "BANK NIFTY"},
    "SENSEX":      {"exchange": "BSE", "token": 30,    "name": "SENSEX"},
    "GOLD MCX":    {"exchange": "MCX", "symbol": "GOLD", "name": "GOLD MCX"},
    "SILVER MCX":  {"exchange": "MCX", "symbol": "SILVER", "name": "SILVER MCX"},
    "CRUDEOIL":    {"exchange": "MCX", "symbol": "CRUDEOIL", "name": "CRUDEOIL"},
    "NATGAS":      {"exchange": "MCX", "symbol": "NATURALGAS", "name": "NATGAS"}
}

DISPLAY_ORDER = ["NIFTY 50", "BANK NIFTY", "SENSEX", "GOLD MCX", "SILVER MCX", "CRUDEOIL", "NATGAS"]

# ---------------- STATE ---------------- #
state = {name: {"price": 0.0, "vol": 0.0, "src": "INIT", "ts": "--:--:--"} for name in DISPLAY_ORDER}
token_to_name = {} # token_str: display_name
last_ws_tick = {name: 0 for name in DISPLAY_ORDER}
lock = threading.Lock()

# ---------------- TERMINAL UI ---------------- #
def refresh_ui():
    """Renders the fixed terminal UI using ANSI cursor control"""
    # Move cursor up by N lines to overwrite
    sys.stdout.write(f"\033[{len(DISPLAY_ORDER)}A") 
    for name in DISPLAY_ORDER:
        s = state[name]
        p_val = s['price']
        p_str = f"{p_val:<10.2f}"
        v_str = f"{float(s['vol']):.0f}" if s['vol'] > 0 else "0.0"
        line = f"📊 {s['ts']} | {name:<10}: {p_str} | Vol: {v_str:<8} | Src: {s['src']}"
        # \033[K clears the line from cursor to end
        sys.stdout.write(f"\033[K{line}\n")
    sys.stdout.flush()

# ---------------- LOGIC ---------------- #

def update_instrument(name, price, vol, source):
    try:
        p = float(price)
        if p <= 0: return # Filter zero/invalid
        
        changed = False
        with lock:
            if state[name]["price"] != p:
                state[name].update({
                    "price": p,
                    "vol": vol,
                    "src": source,
                    "ts": datetime.datetime.now().strftime("%H:%M:%S")
                })
                changed = True
            if source == "WS":
                last_ws_tick[name] = time.time()

        if changed:
            refresh_ui()
    except Exception:
        pass

def poller_task(alice, name, config):
    is_hybrid = (name != "SENSEX")
    exchange = config['exchange']
    
    # Resolve instrument
    instrument = None
    try:
        if 'token' in config:
            instrument = alice.get_instrument_by_token(exchange, config['token'])
        else:
            instrument = alice.get_instrument_by_symbol(exchange, config['symbol'])
    except: pass

    if not instrument: return

    while True:
        try:
            should_poll = False
            if not is_hybrid:
                should_poll = True
            else:
                with lock:
                    if time.time() - last_ws_tick.get(name, 0) > 2.0:
                        should_poll = True
            
            if should_poll:
                res = alice.get_scrip_info(instrument)
                if res and res.get('stat') == 'Ok':
                    update_instrument(name, res.get('LTP', 0), res.get('v', 0), "REST")
        except: pass
        
        # SENSEX/Indices poll fast (500ms), Commodities (800ms)
        time.sleep(0.5 if "NIFTY" in name or "SENSEX" in name else 0.8)

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    # 1. Login
    try:
        alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
        alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
    except Exception as e:
        print(f"Login Failed: {e}")
        exit(1)

    # 2. Prepare Terminal
    os.system('cls' if os.name == 'nt' else 'clear')
    print("🚀 Anti-Gravity Agent [LIVE TERMINAL ENGINE] Starting...\n")
    
    # Pre-render empty lines
    for _ in DISPLAY_ORDER: print("")
    
    # 3. Initialize Pollers & Resolve Tokens
    ws_subs = []
    for name in DISPLAY_ORDER:
        config = INSTRUMENTS_CONFIG[name]
        
        # Start Poller Thread
        t = threading.Thread(target=poller_task, args=(alice, name, config))
        t.daemon = True
        t.start()
        
        # Collect for WS
        if name != "SENSEX":
            try:
                if 'token' in config:
                    inst = alice.get_instrument_by_token(config['exchange'], config['token'])
                else:
                    inst = alice.get_instrument_by_symbol(config['exchange'], config['symbol'])
                
                if inst:
                    token_to_name[str(inst.token)] = name
                    ws_subs.append(inst)
            except: pass

    # 4. WebSocket Callbacks
    def on_message(msg):
        try:
            d = json.loads(msg)
            tk = str(d.get('tk'))
            lp = d.get('lp')
            if lp and tk in token_to_name:
                update_instrument(token_to_name[tk], lp, d.get('v', 0), "WS")
        except: pass

    def on_open():
        alice.subscribe(ws_subs)

    # 5. Start WebSocket (Blocking)
    class WSClient:
        def __init__(self, alice):
            self.alice = alice
            self.enc = hashlib.sha256(hashlib.sha256(alice.session_id.encode()).hexdigest().encode()).hexdigest()
        
        def run(self):
            ws_url = "wss://ws1.aliceblueonline.com/NorenWS/"
            self.ws = websocket.WebSocketApp(ws_url,
                                             on_open=lambda ws: on_open(),
                                             on_message=lambda ws, msg: on_message(msg))
            self.ws.run_forever()

    try:
        ws_client = WSClient(alice)
        ws_client.run()
    except KeyboardInterrupt:
        sys.stdout.write("\n\n🛑 Market Stream Stopped.\n")
