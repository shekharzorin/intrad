from agents.auth_agent import AuthAgent
from agents.live_market_agent import start_market_feed, data_bus
from agents.anti_gravity_agent import AntiGravityAgent
import time
import threading

def login():
    alice = AuthAgent().login()
    print("✅ Login Successful")
    return alice

def start_live_feed(alice):
    """Start WebSocket and subscribe to live market data"""
    # Define symbols to subscribe to
    symbols_to_subscribe = [
        {"exchange": "NSE", "token": 26000, "name": "NIFTY50"},
        {"exchange": "NSE", "token": 26009, "name": "NIFTY BANK"},
        {"exchange": "BSE", "token": 30, "name": "SENSEX"},
        {"exchange": "NSE", "symbol": "RELIANCE", "name": "RELIANCE"}
    ]
    start_market_feed(alice, symbols_to_subscribe)

    # Heartbeat: print status every 5 seconds
    print("⏳ Waiting for live market ticks...")
    while True:
        current_data = data_bus.get_all_data()
        tick_count = len(current_data)
        # Detailed heartbeat to show we rely on data_bus
        # time.sleep(5) 

def anti_gravity_loop():
    """Run Anti-Gravity analysis in a loop"""
    agent = AntiGravityAgent()
    print("🌌 Starting Anti-Gravity Agent...")

    try:
        while True:
            agent.run_cycle()
            time.sleep(1)  # Analyze every second (fast reaction)
    except KeyboardInterrupt:
        print("\n❌ Analysis stopped")

def main():
    alice = login()

    # Start live feed in background thread
    live_thread = threading.Thread(target=start_live_feed, args=(alice,))
    live_thread.daemon = True
    live_thread.start()

    # Start analysis in background thread
    analysis_thread = threading.Thread(target=anti_gravity_loop)
    analysis_thread.daemon = True
    analysis_thread.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n❌ Shutting down...") 

