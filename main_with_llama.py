"""
🧠 MAIN TRADING LOOP WITH LLAMA INTEGRATION

This shows how to use the LLaMA-trained dataset in your live trading
"""

from agents.auth_agent import AuthAgent
from agents.live_market_agent import start_market_feed, tick_count, data_bus
from agents.market_context_agent import MarketContextAgent
from agents.llama_integration_agent import MarketAgentLLaMAIntegration
from shared.data_bus import DataBus
import time
import threading


class TradingLoopWithLLaMA:
    """
    Complete trading loop:
    Live Data → Market Analysis → LLaMA Insight → Strategy
    """

    def __init__(self):
        self.alice = None
        self.data_bus = DataBus()
        self.market_agent = MarketContextAgent()
        self.llama_agent = MarketAgentLLaMAIntegration()
        self.running = False

    def start(self):
        """Initialize and start all components"""
        print("=" * 70)
        print("🚀 ALICE TRADING - LIVE MARKET AGENT WITH LLAMA")
        print("=" * 70)

        # Step 1: Login
        print("\n[1/4] AUTHENTICATION")
        auth = AuthAgent()
        self.alice = auth.login()

        # Step 2: Start WebSocket
        print("\n[2/4] LIVE MARKET DATA")
        start_market_feed(self.alice)
        print("✅ WebSocket + Subscription Active")

        # Step 3: Load LLaMA Dataset
        print("\n[3/4] LLAMA INTEGRATION")
        print(f"✅ LLaMA Agent Ready ({len(self.llama_agent.instructions)} instructions loaded)")

        # Step 4: Start Analysis Loop
        print("\n[4/4] STARTING ANALYSIS LOOP")
        self.running = True
        self.analysis_loop()

    def analysis_loop(self):
        """Main trading analysis loop"""
        iteration = 0
        last_tick_count = 0

        while self.running:
            iteration += 1
            print(f"\n{'─' * 70}")
            print(f"[ITERATION #{iteration}] {time.strftime('%H:%M:%S')}")
            print(f"{'─' * 70}")

            # Check for new market data
            current_ticks = tick_count
            if current_ticks == last_tick_count:
                print("⏳ Waiting for market data...")
                time.sleep(5)
                continue

            last_tick_count = current_ticks

            # Step A: Get latest market data
            print(f"\n📊 STEP A: MARKET DATA")
            print(f"   Ticks received: {current_ticks}")
            market_data = self.data_bus.get_all_data()
            if market_data:
                for symbol, data in market_data.items():
                    print(f"   {symbol}: Price={data.get('price'):.2f}, Vol={data.get('volume'):.0f}")

            # Step B: Market Context Analysis
            print(f"\n📈 STEP B: MARKET CONTEXT ANALYSIS")
            self.market_agent.analyze_market_context()

            # Step C: Get LLaMA Insight
            print(f"\n🧠 STEP C: LLAMA AGENT INSIGHT")
            if market_data:
                for symbol, data in market_data.items():
                    insight = self.llama_agent.get_agent_insight(data)
                    if insight:
                        print(f"   {symbol}:")
                        print(f"   → {insight['analysis'][:100]}...")

            # Step D: Strategy Decision
            print(f"\n⚡ STEP D: STRATEGY DECISION")
            print(f"   Status: Awaiting trade signals...")

            # Sleep before next iteration
            time.sleep(10)

    def stop(self):
        """Stop trading loop"""
        self.running = False
        print("\n❌ Trading loop stopped")


def main():
    """Entry point"""
    try:
        trader = TradingLoopWithLLaMA()
        trader.start()
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
        trader.stop()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
