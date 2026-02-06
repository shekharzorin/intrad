
import os
import time
import threading
import pyotp
import json
from datetime import datetime
from dotenv import load_dotenv
from pya3 import Aliceblue, Instrument
from agents.auth_agent import AuthAgent
from agents.live_market_agent import start_market_feed, data_bus
from agents.anti_gravity_agent import AntiGravityAgent

load_dotenv()

def start_dashboard():
    print("🚀 ALICE TRADING - LIVE MARKET DASHBOARD [ENABLED]")
    print("-" * 50)
    
    # 1. Login
    try:
        auth = AuthAgent()
        alice = auth.login()
    except Exception as e:
        print(f"❌ Login Failed: {e}")
        return

    # 2. Define High-Priority Symbols (Indices + Commodities)
    symbols_to_subscribe = [
        {"exchange": "NSE", "token": 26000, "name": "NIFTY 50"},
        {"exchange": "NSE", "token": 26009, "name": "BANK NIFTY"},
        {"exchange": "BSE", "token": 30, "name": "SENSEX"},
        {"exchange": "MCX", "token": 488292, "name": "CRUDE OIL"},
        {"exchange": "MCX", "token": 488507, "name": "NATURAL GAS"},
        {"exchange": "MCX", "token": 454819, "name": "GOLD"},
        {"exchange": "MCX", "token": 451667, "name": "SILVER"},
    ]

    # 3. Start Live WebSocket Feed in Background
    print("\n[PHASE 1] Initializing Market Data Stream...")
    feed_thread = threading.Thread(target=start_market_feed, args=(alice, symbols_to_subscribe))
    feed_thread.daemon = True
    feed_thread.start()
    
    # 4. Start Anti-Gravity AI Agent
    print("[PHASE 2] Starting AI Strategy Engine...")
    agent = AntiGravityAgent()
    
    # 5. Dashboard Execution Loop
    print("\n" + "="*75)
    print(f"{'SYMBOL':<15} | {'LTP':<10} | {'VOLUME':<12} | {'SIGNAL'}")
    print("="*75)
    
    # Map tokens to names for clean display
    symbol_map = {str(s['token']): s['name'] for s in symbols_to_subscribe}

    try:
        while True:
            # 1. Run analysis cycle (detect signals)
            agent.run_cycle()
            
            # 2. Fetch all current snapshots from the data bus
            all_data = data_bus.get_all_data()
            
            # 3. Dynamic Console Output
            for sym, data in all_data.items():
                ltp = data.get('price', 0)
                vol = data.get('volume', 0)
                
                # Check for signals (re-processing for UI purposes)
                signal = agent.process_tick(sym, ltp, vol)
                sig_text = f"[{signal['type']}]" if signal else ""
                
                # Format output row
                # Note: 'sym' might be the trading symbol from the SDK or the token
                display_name = sym # Fallback
                
                print(f"📈 {display_name:<12} | {ltp:<10} | {vol:<12} | {sig_text}")
            
            # Wait for next update
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n🛑 Dashboard Halted by User.")
    except Exception as e:
        print(f"⚠️ Dashboard Error: {e}")

if __name__ == "__main__":
    start_dashboard()
