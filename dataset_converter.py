"""
🧠 Market Agent LLaMA Dataset Converter
Converts raw market CSV data → LLaMA-compatible JSONL format

CRITICAL: This generates agent-aware training data for Market Agent
"""

import json
import os
import pandas as pd
from pathlib import Path
from datetime import datetime
import numpy as np


class MarketDataLLaMAConverter:
    """Convert market data to LLaMA instruction format"""

    def __init__(self, raw_dir="dataset/raw", output_dir="dataset/llama"):
        self.raw_dir = raw_dir
        self.output_dir = output_dir
        self.instructions = []

        # Create directories
        Path(self.raw_dir).mkdir(parents=True, exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def analyze_market_condition(self, row):
        """
        🧠 Agent-Style Analysis
        Convert numeric data → market reasoning
        """
        
        price = float(row.get("price", row.get("close", 0)))
        prev_price = float(row.get("prev_close", price * 0.99))
        volume = float(row.get("volume", 0))
        high = float(row.get("high", price))
        low = float(row.get("low", price))
        
        # Calculate indicators
        price_change = price - prev_price
        price_change_pct = (price_change / prev_price * 100) if prev_price != 0 else 0
        volatility = ((high - low) / price * 100) if price != 0 else 0
        
        # Trend analysis
        if price_change_pct > 2:
            trend = "bullish"
            momentum = "strong upward"
        elif price_change_pct > 0.5:
            trend = "bullish"
            momentum = "mild upward"
        elif price_change_pct < -2:
            trend = "bearish"
            momentum = "strong downward"
        elif price_change_pct < -0.5:
            trend = "bearish"
            momentum = "mild downward"
        else:
            trend = "neutral"
            momentum = "sideways"

        # Volatility classification
        if volatility > 3:
            vol_desc = "high volatility"
        elif volatility > 1:
            vol_desc = "moderate volatility"
        else:
            vol_desc = "low volatility"

        # Volume analysis
        if volume > 1000000:
            vol_strength = "with strong buying/selling pressure"
        elif volume > 500000:
            vol_strength = "with moderate volume interest"
        else:
            vol_strength = "with weak volume confirmation"

        # Construct reasoning
        reasoning = (
            f"The market shows {trend} momentum ({momentum}) with {vol_desc}. "
            f"Price moved {abs(price_change_pct):.2f}% {('up' if price_change_pct > 0 else 'down')}, "
            f"trading {vol_strength}. "
            f"Day range: {low:.2f} - {high:.2f}. "
            f"Current price: {price:.2f}. "
            f"Market bias is {trend.upper()}. "
            f"Risk level: {'HIGH' if volatility > 3 else ('MEDIUM' if volatility > 1 else 'LOW')}."
        )

        return reasoning

    def row_to_instruction(self, row, symbol):
        """Convert single row → LLaMA instruction format"""
        
        timestamp = row.get("timestamp", row.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")))
        price = row.get("price", row.get("close", 0))
        open_price = row.get("open", price)
        high = row.get("high", price)
        low = row.get("low", price)
        volume = row.get("volume", 0)

        # Build input text (what agent sees)
        input_text = (
            f"Index/Symbol: {symbol} | "
            f"Timestamp: {timestamp} | "
            f"Open: {open_price:.2f} | "
            f"High: {high:.2f} | "
            f"Low: {low:.2f} | "
            f"Close: {price:.2f} | "
            f"Volume: {volume:.0f}"
        )

        # Generate agent reasoning
        output_text = self.analyze_market_condition(row)

        instruction = {
            "instruction": "Analyze the given market data and provide market condition assessment with trend, momentum, and volatility analysis.",
            "input": input_text,
            "output": output_text
        }

        return instruction

    def process_csv(self, csv_path, symbol_name):
        """Process single CSV file"""
        print(f"\n📊 Processing: {csv_path}")
        
        if not os.path.exists(csv_path):
            print(f"   ⚠️ File not found: {csv_path}")
            return 0

        try:
            df = pd.read_csv(csv_path)
            print(f"   ✅ Loaded {len(df)} rows")

            count = 0
            for idx, row in df.iterrows():
                try:
                    instruction = self.row_to_instruction(row, symbol_name)
                    self.instructions.append(instruction)
                    count += 1
                except Exception as e:
                    print(f"   ⚠️ Row {idx} skipped: {e}")
                    continue

            print(f"   ✅ Converted {count} rows")
            return count

        except Exception as e:
            print(f"   ❌ Error processing {csv_path}: {e}")
            return 0

    def save_jsonl(self, output_file=None):
        """Save as JSONL format"""
        if output_file is None:
            output_file = os.path.join(self.output_dir, "market_agent_llama.jsonl")

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, 'w') as f:
            for instruction in self.instructions:
                f.write(json.dumps(instruction) + '\n')

        print(f"\n✅ Saved {len(self.instructions)} instructions to: {output_file}")
        return output_file

    def generate_sample_data(self):
        """
        🎯 Generate sample market data for testing
        (Use this if you don't have raw CSV files yet)
        """
        print("\n🎯 Generating sample market data...")

        symbols = {
            "NIFTY 50": "nifty50.csv",
            "NIFTY BANK": "nifty_bank.csv",
            "SENSEX": "sensex.csv"
        }

        for symbol, filename in symbols.items():
            filepath = os.path.join(self.raw_dir, filename)
            
            # Generate 100 sample rows
            dates = pd.date_range(start='2026-01-01', periods=100, freq='H')
            base_price = np.random.uniform(15000, 22000)
            
            data = []
            for i, date in enumerate(dates):
                change = np.random.uniform(-2, 2)
                price = base_price + change
                
                data.append({
                    'timestamp': date.strftime("%Y-%m-%d %H:%M"),
                    'open': price - abs(np.random.uniform(0, 1)),
                    'high': price + abs(np.random.uniform(0, 2)),
                    'low': price - abs(np.random.uniform(0, 2)),
                    'close': price,
                    'volume': np.random.randint(100000, 5000000)
                })
                
                base_price = price

            df = pd.DataFrame(data)
            df.to_csv(filepath, index=False)
            print(f"   ✅ Created: {filepath}")

    def run(self, generate_samples=True):
        """Main execution"""
        print("=" * 60)
        print("🧠 MARKET AGENT LLAMA DATASET CONVERTER")
        print("=" * 60)

        # Optional: Generate sample data if raw files don't exist
        if generate_samples:
            self.generate_sample_data()

        # Process all CSV files in raw directory
        symbols = {
            "NIFTY 50": "nifty50.csv",
            "NIFTY BANK": "nifty_bank.csv",
            "SENSEX": "sensex.csv",
            "Commodities": "commodities_scaled.csv"
        }

        total_rows = 0
        for symbol, filename in symbols.items():
            csv_path = os.path.join(self.raw_dir, filename)
            count = self.process_csv(csv_path, symbol)
            total_rows += count

        # Save as JSONL
        if self.instructions:
            output_file = self.save_jsonl()
            
            # Show sample
            print("\n📋 SAMPLE OUTPUT (First instruction):")
            print(json.dumps(self.instructions[0], indent=2))
            
            return output_file
        else:
            print("❌ No data to save!")
            return None


def main():
    """Entry point"""
    converter = MarketDataLLaMAConverter(
        raw_dir="dataset/raw",
        output_dir="dataset/llama"
    )
    
    # Run conversion (with sample data generation)
    output_file = converter.run(generate_samples=True)
    
    if output_file:
        print("\n" + "=" * 60)
        print("✅ DATASET READY FOR LLAMA FINE-TUNING")
        print("=" * 60)
        print(f"📁 Output: {output_file}")
        print(f"📊 Total instructions: {len(converter.instructions)}")
        print("\n🚀 Next steps:")
        print("   1. Use for LLaMA fine-tuning (LoRA)")
        print("   2. Use with Ollama / llama.cpp")
        print("   3. Integrate into Market Agent")


if __name__ == "__main__":
    main()
