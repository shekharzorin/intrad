
"""
ANTI-GRAVITY AGENT - NON-STOP LIVE MARKET ENGINE
================================================
Fault-tolerant, continuous streaming for Indian markets.
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

# Full Instrument Configuration
CONFIG = {
    "NIFTY 50":   {"exchange": "NSE", "token": 26000, "hybrid": True},
    "BANK NIFTY": {"exchange": "NSE", "token": 26009, "hybrid": True},
    "SENSEX":     {"exchange": "BSE", "token": 1,     "hybrid": False},
}

COMMODITIES = ["GOLD", "SILVER", "CRUDEOIL", "NATGASMINI"]
RESOLVED_TOKENS = {} # {token_str: display_name}
RESOLVED_INSTS = {}  # {name: inst_obj}

# State Tracking
last_data = {} # {name: {"price": float, "vol": float, "ts": timestamp, "src": str, "last_print": float}}
lock = threading.Lock()

# ---------------- CORE LOGIC ---------------- #

def is_market_open():
    """Checks if any relevant market (NSE/MCX) is currently open."""
    now = datetime.datetime.now()
    if now.weekday() > 4: return False
    
    # Standard Market Hours (09:15 - 15:30)
    market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    # MCX Hours (09:00 - 23:30) - For this agent, we follow the user's specific exit condition
    # User said: stop ONLY IF Time > 15:30 IST (NSE) Or MCX market closed
    # We will favor continuing if NSE is open or MCX is open.
    mcx_end = now.replace(hour=23, minute=30, second=0, microsecond=0)
    
    return market_start <= now <= max(market_end, mcx_end)

def log_tick(name, price, vol, source):
    """Handles price updates and heartbeat logging"""
    try:
        p = float(price)
        v = float(vol) if vol else 0.0
        now_ts = time.time()
        
        with lock:
            if name not in last_data:
                last_data[name] = {"price": 0.0, "vol": 0.0, "last_print": 0.0}
            
            data = last_data[name]
            price_changed = (data["price"] != p)
            time_since_print = now_ts - data["last_print"]

            # Rule: Print on change OR every 5 seconds (heartbeat)
            if price_changed or time_since_print >= 5.0:
                data.update({"price": p, "vol": v, "last_print": now_ts})
                
                # Format: 📊 HH:MM:SS | INSTRUMENT | LAST_PRICE | Vol: VOLUME | Src: WS/REST
                ts_str = datetime.datetime.now().strftime("%H:%M:%S")
                vol_str = f"{v:.1f}" if v > 0 else "0.0"
                print(f"📊 {ts_str} | {name:<10} | {p:>10.2f} | Vol: {vol_str:<8} | Src: {source}")
    except:
        pass

# ---------------- WORKERS ---------------- #

def poller_worker(alice, name, exchange, token):
    """Independent looping poller for each instrument"""
    is_hybrid = CONFIG.get(name, {}).get("hybrid", True) or name.endswith("MCX") or name in COMMODITIES

    while is_market_open():
        try:
            should_poll = False
            if name == "SENSEX":
                should_poll = True
            else:
                # Hybrid Logic: Fallback if WebSocket data is silent
                # We use a 2s silence window
                with lock:
                    if time.time() - last_data.get(name, {}).get("last_tick", 0) > 2.0:
                        should_poll = True
            
            if should_poll:
                inst = RESOLVED_INSTS.get(name)
                if not inst:
                    inst = alice.get_instrument_by_token(exchange, token)
                    RESOLVED_INSTS[name] = inst
                
                res = alice.get_scrip_info(inst)
                if res and res.get('stat') == 'Ok':
                    log_tick(name, res.get('LTP', 0), res.get('v', 0), "REST")
        except:
            pass
        time.sleep(1.0) # 1s Polling interval as requested

def supervisor(alice):
    """Main supervisor thread to ensure workers and WS are running"""
    print("🚀 Anti-Gravity Agent [HYBRID ARCHITECTURE] Starting...")
    
    # Resolve Symbols
    for name, c in CONFIG.items():
        print(f"🔄 [REST] Poller Started: {name}")
        t = threading.Thread(target=poller_worker, args=(alice, name, c['exchange'], c['token']))
        t.daemon = True
        t.start()
        if c.get("hybrid"):
            RESOLVED_TOKENS[str(c['token'])] = name

    print("🔄 [REST] Poller Started: COMMODITY")
    for sym in COMMODITIES:
        try:
            inst = alice.get_instrument_by_symbol("MCX", sym)
            if inst:
                RESOLVED_TOKENS[str(inst.token)] = sym
                RESOLVED_INSTS[sym] = inst
                t = threading.Thread(target=poller_worker, args=(alice, sym, "MCX", inst.token))
                t.daemon = True
                t.start()
        except: pass

    # WebSocket Start (Self-Restarting)
    def run_ws():
        while is_market_open():
            try:
                print("🔧 [Hybrid] Initializing WebSocket Session...")
                session_id = alice.session_id
                sha256_encryption1 = hashlib.sha256(session_id.encode('utf-8')).hexdigest()
                alice.ENC = hashlib.sha256(sha256_encryption1.encode('utf-8')).hexdigest()
                
                try: alice.invalid_sess(session_id); alice.createSession(session_id)
                except: pass

                def on_msg(ws, msg):
                    try:
                        d = json.loads(msg)
                        tk = str(d.get('tk'))
                        lp = d.get('lp')
                        if lp and tk in RESOLVED_TOKENS:
                            with lock:
                                if RESOLVED_TOKENS[tk] not in last_data: last_data[RESOLVED_TOKENS[tk]] = {}
                                last_data[RESOLVED_TOKENS[tk]]["last_tick"] = time.time()
                            log_tick(RESOLVED_TOKENS[tk], lp, d.get('v', 0), "WS")
                    except: pass

                def on_open(ws):
                    print("🔗 Connecting to WebSocket Server...")
                    subs = [RESOLVED_INSTS[n] for n in RESOLVED_TOKENS.values() if n in RESOLVED_INSTS]
                    if subs: alice.subscribe(subs)

                ws = websocket.WebSocketApp("wss://ws1.aliceblueonline.com/NorenWS/",
                                             on_open=on_open, on_message=on_msg)
                ws.run_forever()
            except:
                time.sleep(5) # Delay before reconnect

    ws_thread = threading.Thread(target=run_ws)
    ws_thread.daemon = True
    ws_thread.start()

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    if not is_market_open():
        print("⚠️ Market Closed — Live feed stopped safely")
        exit()

    try:
        alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
        alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
        print("✅ Login Successful")
        
        # Start supervision
        supervisor(alice)

        # Keep main thread alive
        while is_market_open():
            time.sleep(1)
            
        print("\n⚠️ Market Closed — Live feed stopped safely")

    except KeyboardInterrupt:
        print("\n🛑 Manual Interruption Detected. Shutting down...")
    except Exception as e:
        print(f"❌ Error: {e}")
