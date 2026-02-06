"""
✅ Test script for the improved live market agent
Run this to verify WebSocket connection works
"""

from agents.auth_agent import AuthAgent
from agents.live_market_agent import start_market_feed, get_market_data, get_tick_count, is_websocket_connected
import time


def test_websocket():
    """Test WebSocket connection"""
    print("=" * 70)
    print("🧪 TESTING LIVE MARKET AGENT")
    print("=" * 70)
    
    # Step 1: Login
    print("\n[1/4] Authenticating...")
    try:
        alice = AuthAgent().login()
        print("✅ Authentication successful")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return
    
    # Step 2: Start WebSocket
    print("\n[2/4] Starting WebSocket...")
    try:
        # Subscribe to NIFTY 50 (token: 26000)
        symbols = [
            {"exchange": "NSE", "token": 26000, "name": "NIFTY 50"}
        ]
        start_market_feed(alice, symbols_to_subscribe=symbols)
        print("✅ WebSocket started")
    except Exception as e:
        print(f"❌ WebSocket start failed: {e}")
        return
    
    # Step 3: Wait for data
    print("\n[3/4] Waiting for live market data (30 seconds)...")
    print("─" * 70)
    
    start_time = time.time()
    prev_tick_count = 0
    
    while time.time() - start_time < 30:
        current_ticks = get_tick_count()
        is_connected = is_websocket_connected()
        
        # Print status every 5 seconds
        if int((time.time() - start_time) % 5) < 1:
            status = "🔌 CONNECTED" if is_connected else "❌ DISCONNECTED"
            print(f"{status} | Ticks: {current_ticks}")
        
        # Check for new data
        data = get_market_data()
        if data and current_ticks > prev_tick_count:
            for symbol, info in data.items():
                print(f"📈 {symbol}: {info['price']:.2f} (Vol: {info['volume']})")
            prev_tick_count = current_ticks
        
        time.sleep(1)
    
    # Step 4: Summary
    print("\n[4/4] Test Summary")
    print("─" * 70)
    total_ticks = get_tick_count()
    final_data = get_market_data()
    
    print(f"✅ Total ticks received: {total_ticks}")
    print(f"✅ Symbols with data: {len(final_data)}")
    
    if total_ticks > 0:
        print("✅ TEST PASSED - Live data is flowing!")
    else:
        print("⚠️  No ticks received - check market hours (9:15 AM - 3:30 PM IST)")
    
    print("=" * 70)


if __name__ == "__main__":
    test_websocket()
