from agents.live_market_agent import data_bus

class MarketContextAgent:
    def __init__(self):
        self.role = 'Market Context Analyst'
        self.goal = 'Anlalyze the overall market context and trends to inform trading decisions'
        self.backstory = 'An expert in macroeconomic analysis and market sentiment evaluation.'
        self.tools = []

    def analyze_market_context(self):
        all_data = data_bus.get_all_data()
        if all_data:
            print("📊 Market Context Analysis:")
            for symbol, tick in all_data.items():
                print(f"{symbol}: {tick}")
        else:
            print("No live data available for analysis.")
