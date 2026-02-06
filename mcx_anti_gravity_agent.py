
"""
MCX ANTI-GRAVITY AGENT - HIGH PERFORMANCE COMMODITY ENGINE
==========================================================
Strict Requirements:
1. Instruments: GOLD, SILVER, CRUDEOIL, NATGASMINI (MCX)
2. Auto-resolve nearest expiry contracts.
3. Hybrid WS/REST with 1s Polling.
4. Independent updates only on price change.
5. Strict Format: 📊 HH:MM:SS | COMMODITY | LAST_PRICE | Vol: VOLUME | Src: WS/REST
"""

import os
import time
import json
import threading
import hashlib
import datetime
import pyotp
import pandas as pd
from dotenv import load_dotenv
import websocket
from pya3 import Aliceblue, Instrument

# ---------------- CONFIGURATION ---------------- #
load_dotenv()

API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

# Target Commodities
COMMODITIES = ["GOLD", "SILVER", "CRUDEOIL", "NATGASMINI"]
RESOLVED_COMMODITIES = {} # {token_str: display_name}
RESOLVED_INSTRUMENTS = {} # {display_name: instrument_obj}

# State Management
last_printed_price = {} # {name: price}
last_tick_time = {}     # {name: unix_timestamp}
lock = threading.Lock()

# ---------------- CORE LOGIC ---------------- #

def get_ist_now():
    return datetime.datetime.now()

def is_mcx_market_open():
    """Checks if MCX Market is open (09:00 - 11:30/11:55 PM IST)"""
    now = get_ist_now()
    if now.weekday() > 4: return False
    
    # Simple check: 9 AM to 11:30 PM
    start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=30, second=0, microsecond=0)
    return start <= now <= end

def emit_tick(name, price, vol, source):
    """Prints tick strictly when price changes"""
    try:
        p = float(price)
        if p <= 0: return

        with lock:
            if last_printed_price.get(name) == p:
                return # Only on price change
            last_printed_price[name] = p
            last_tick_time[name] = time.time()

        ts = get_ist_now().strftime("%H:%M:%S")
        v_float = float(vol) if vol else 0.0
        vol_str = f"{v_float:.1f}" if v_float > 0 else "0.0"

        # Format: 📊 HH:MM:SS | COMMODITY | LAST_PRICE | Vol: VOLUME | Src: WS/REST
        print(f"📊 {ts} | {name:<10} | {p:>10.2f} | Vol: {vol_str:<8} | Src: {source}")
    except:
        pass

def rest_worker(alice, name, token):
    """Independent worker thread for REST polling"""
    while True:
        try:
            should_poll = False
            with lock:
                # Hybrid check: fallback if WS is silent for 2s
                if time.time() - last_tick_time.get(name, 0) > 2.0:
                    should_poll = True
            
            if should_poll:
                inst = RESOLVED_INSTRUMENTS.get(name)
                if inst:
                    res = alice.get_scrip_info(inst)
                    if res and res.get('stat') == 'Ok':
                        emit_tick(name, res.get('LTP', 0), res.get('v', 0), "REST")
        except:
            pass
        time.sleep(1.0) # Poll every 1 second

# ---------------- RESOLUTION ---------------- #

def resolve_mcx_instruments(alice):
    """Resolves target commodities to their nearest expiry tokens using CSV filter and API verification"""
    print("🔍 Resolving MCX Expiry Contracts...")
    
    try:
        # Load MCX.csv for helper search
        mcx_df = pd.read_csv('MCX.csv')
        # Standard columns: Exch,Exchange Segment,Symbol,Token,Trading Symbol,Expiry Date, ...
    except Exception as e:
        print(f"⚠️ MCX.csv not found or corrupted: {e}")
        mcx_df = None

    for base_sym in COMMODITIES:
        found = False
        
        # 1. Try generic symbol first via API
        try:
            inst = alice.get_instrument_by_symbol("MCX", base_sym)
            if inst:
                RESOLVED_INSTRUMENTS[base_sym] = inst
                RESOLVED_COMMODITIES[str(inst.token)] = base_sym
                last_tick_time[base_sym] = 0
                print(f"✅ Found {base_sym} (Generic): {inst.token}")
                found = True
        except:
            pass
            
        # 2. If generic fails, check CSV for nearest expiry
        if not found and mcx_df is not None:
            try:
                # Filter for futures on this base symbol
                subset = mcx_df[(mcx_df['Symbol'] == base_sym) & 
                                (mcx_df['Exchange Segment'] == 'mcx_fo')]
                
                # Exclude options (if they have CE/PE in trading symbol or instrument type)
                # Some CSVs have 'Instrument Type' - check for FUTCOM or similar
                if 'Instrument Type' in subset.columns:
                     subset = subset[subset['Instrument Type'].str.contains('FUT', na=False)]
                
                if not subset.empty:
                    # Sort by expiry date to get the nearest one
                    if 'Expiry Date' in subset.columns:
                        subset = subset.sort_values('Expiry Date')
                    
                    nearest = subset.iloc[0]
                    token = int(nearest['Token'])
                    trading_symbol = nearest['Trading Symbol']
                    
                    # Verify via API
                    inst = alice.get_instrument_by_token("MCX", token)
                    if inst:
                        RESOLVED_INSTRUMENTS[base_sym] = inst
                        RESOLVED_COMMODITIES[str(inst.token)] = base_sym
                        last_tick_time[base_sym] = 0
                        print(f"✅ Found {base_sym} (Expiry: {trading_symbol}): {inst.token}")
                        found = True
            except Exception as e:
                print(f"⚠️ CSV Resolution Error for {base_sym}: {e}")

        if not found:
            print(f"❌ Could not resolve {base_sym}")

# ---------------- WS ENGINE ---------------- #

class MCXWSClient:
    def __init__(self, alice):
        self.alice = alice
        self.running = True

    def on_message(self, ws, msg):
        try:
            d = json.loads(msg) if isinstance(msg, str) else msg
            tk = str(d.get('tk'))
            lp = d.get('lp')
            v = d.get('v', 0)
            
            if lp and tk in RESOLVED_COMMODITIES:
                emit_tick(RESOLVED_COMMODITIES[tk], lp, v, "WS")
        except:
            pass

    def on_open(self, ws):
        subs = list(RESOLVED_INSTRUMENTS.values())
        if subs:
            self.alice.subscribe(subs)

    def run(self):
        ws_url = "wss://ws1.aliceblueonline.com/NorenWS/"
        # Re-gen encryption for fresh connection
        session_id = self.alice.session_id
        sha256_encryption1 = hashlib.sha256(session_id.encode('utf-8')).hexdigest()
        self.alice.ENC = hashlib.sha256(sha256_encryption1.encode('utf-8')).hexdigest()

        try: self.alice.invalid_sess(session_id); self.alice.createSession(session_id)
        except: pass

        self.ws = websocket.WebSocketApp(ws_url,
                                         on_open=self.on_open,
                                         on_message=self.on_message)
        self.ws.run_forever()

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    if not is_mcx_market_open():
        # Even if open, we print what's requested
        # print("⚠️ Market Closed — Live data available during MCX hours")
        pass

    print("🚀 Anti-Gravity Agent [MCX LIVE ENGINE] Starting...")

    try:
        alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
        alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
        print("✅ Login Successful")
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        exit(1)

    # 1. Resolve Contracts
    resolve_mcx_instruments(alice)

    # 2. Start REST Pollers
    for name in RESOLVED_INSTRUMENTS:
        t = threading.Thread(target=rest_worker, args=(alice, name, RESOLVED_INSTRUMENTS[name].token))
        t.daemon = True
        t.start()

    # 3. Start WS Client
    try:
        client = MCXWSClient(alice)
        client.run()
    except KeyboardInterrupt:
        print("\n🛑 MCX Engine Stopped.")
