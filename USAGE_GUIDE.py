"""
🚀 QUICK GUIDE: Using the Improved Live Market Agent
"""

# Example 1: Basic Usage with Token-based Subscription
# ────────────────────────────────────────────────────

from agents.auth_agent import AuthAgent
from agents.live_market_feed import start_market_feed, get_market_data, get_tick_count
import time

# Login
alice = AuthAgent().login()

# Start WebSocket with specific tokens
symbols = [
    {"exchange": "NSE", "token": 26000, "name": "NIFTY 50"},       # NIFTY
    {"exchange": "NSE", "token": 26009, "name": "NIFTY BANK"},     # NIFTY BANK  
    {"exchange": "BSE", "token": 30, "name": "SENSEX"},            # SENSEX
]

start_market_feed(alice, symbols_to_subscribe=symbols)

# Listen for data
while True:
    data = get_market_data()
    if data:
        print(f"Latest data for {len(data)} symbols:")
        for symbol, info in data.items():
            print(f"  {symbol}: Price={info['price']:.2f}, Vol={info['volume']}")
    
    print(f"Ticks received: {get_tick_count()}")
    time.sleep(5)


# Example 2: With Market Context Analysis
# ────────────────────────────────────────

from agents.auth_agent import AuthAgent
from agents.live_market_agent import start_market_feed, get_market_data
from agents.market_context_agent import MarketContextAgent
import time

alice = AuthAgent().login()
start_market_feed(alice, symbols_to_subscribe=[
    {"exchange": "NSE", "token": 26000, "name": "NIFTY 50"}
])

analyzer = MarketContextAgent()

while True:
    analyzer.analyze_market_context()
    time.sleep(10)


# Example 3: With LLaMA Integration
# ──────────────────────────────────

from agents.auth_agent import AuthAgent
from agents.live_market_agent import start_market_feed, get_market_data
from agents.llama_integration_agent import MarketAgentLLaMAIntegration
import time

alice = AuthAgent().login()
start_market_feed(alice, symbols_to_subscribe=[
    {"exchange": "NSE", "token": 26000, "name": "NIFTY 50"}
])

llama_agent = MarketAgentLLaMAIntegration()

while True:
    market_data = get_market_data()
    
    for symbol, data in market_data.items():
        insight = llama_agent.get_agent_insight(data)
        if insight:
            print(f"{symbol}: {insight['analysis']}")
    
    time.sleep(10)


# KEY IMPROVEMENTS
# ────────────────

"""
✅ Simpler callback structure
✅ Uses token-based subscription (more reliable)
✅ Better error handling
✅ Works with data_bus singleton
✅ Reduced output noise (logs every 10th tick)
✅ Better state management
✅ Integrates cleanly with existing agents
"""


# COMMON NSE TOKENS
# ─────────────────

NSE_TOKENS = {
    "NIFTY 50": 26000,
    "NIFTY BANK": 26009,
    "NIFTY IT": 26037,
    "NIFTY PHARMA": 26045,
    "NIFTY 100": 26048,
    "NIFTY 200": 26010,
    "NIFTY PSU BANK": 26055,
    "NIFTY INFRA": 26060,
    "NIFTY ENERGY": 26062,
    "NIFTY CONSUMPTION": 26051,
    "RELIANCE": 741,
    "TCS": 3456,
    "INFY": 3420,
    "HDFC BANK": 2885,
}

# Usage:
# symbols = [
#     {"exchange": "NSE", "token": NSE_TOKENS["NIFTY 50"], "name": "NIFTY 50"},
#     {"exchange": "NSE", "token": NSE_TOKENS["NIFTY BANK"], "name": "NIFTY BANK"},
# ]
# start_market_feed(alice, symbols_to_subscribe=symbols)
