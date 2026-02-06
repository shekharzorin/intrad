"""
🧠 Market Agent LLaMA Integration Agent

This agent loads the LLaMA-trained dataset and uses it to inform
live market analysis decisions.
"""

import json
import os
from pathlib import Path


class MarketAgentLLaMAIntegration:
    """Load and use LLaMA-trained market data"""

    def __init__(self, jsonl_path="dataset/llama/market_agent_llama.jsonl"):
        self.jsonl_path = jsonl_path
        self.instructions = []
        self.load_dataset()

    def load_dataset(self):
        """Load JSONL dataset"""
        if not os.path.exists(self.jsonl_path):
            print(f"⚠️ Dataset not found: {self.jsonl_path}")
            return

        with open(self.jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    self.instructions.append(json.loads(line))

        print(f"✅ Loaded {len(self.instructions)} LLaMA instructions")

    def find_similar_market_condition(self, current_input):
        """
        Find similar market conditions from training data
        This would use embedding similarity in production
        """
        # For now, return top match
        if not self.instructions:
            return None

        return self.instructions[0]

    def get_agent_insight(self, market_data):
        """
        Get agent-style insight based on LLaMA training
        
        Args:
            market_data: dict with price, volume, timestamp, etc.
        
        Returns:
            Market condition analysis
        """
        if not self.instructions:
            return "No training data available"

        # Find similar condition
        similar = self.find_similar_market_condition(market_data)
        
        if similar:
            return {
                "instruction": similar["instruction"],
                "analysis": similar["output"],
                "training_input": similar["input"]
            }

        return None

    def batch_analyze(self, live_data_list):
        """Analyze batch of live market data"""
        results = []
        for data in live_data_list:
            insight = self.get_agent_insight(data)
            if insight:
                results.append(insight)
        return results


def main():
    """Test the integration"""
    print("=" * 60)
    print("🧠 MARKET AGENT LLAMA INTEGRATION")
    print("=" * 60)

    agent = MarketAgentLLaMAIntegration()

    # Test with sample market data
    test_market_data = {
        "symbol": "NIFTY 50",
        "price": 21000,
        "volume": 2000000,
        "timestamp": "2026-01-29 10:30"
    }

    insight = agent.get_agent_insight(test_market_data)

    if insight:
        print("\n📊 TEST ANALYSIS:")
        print(f"Instruction: {insight['instruction']}")
        print(f"Analysis: {insight['analysis']}")
    else:
        print("❌ No insight available")


if __name__ == "__main__":
    main()
