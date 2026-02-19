"""
Anti-Gravity Agent
Implements the core logic for detecting price movements that defy normal market gravity.

Core principles:
- Markets move due to force, not opinion.
- Price + Volume + Time = Truth.
- No prediction. Only reaction.

Logic:
- Analyzes last traded price, volume spikes, VWAP deviation, and momentum.
- Identifies "anti-gravity zones" (vertical price movement, volume expansion).
"""

from collections import deque
import statistics
from shared.data_bus import DataBus

class AntiGravityAgent:
    def __init__(self, window_size=20):
        self.window_size = window_size
        self.history = {}  # Stores deque of history per symbol
        self.data_bus = DataBus()
        self.active = True
        
        # Thresholds (configurable)
        self.PRICE_FORCE_THRESHOLD = 0.3
        self.VOLUME_FORCE_THRESHOLD = 1.5
        
        print(f"🚀 Anti-Gravity Agent Initialized (Window: {self.window_size})")

    def _get_history(self, symbol):
        if symbol not in self.history:
            self.history[symbol] = {
                'prices': deque(maxlen=self.window_size),
                'volumes': deque(maxlen=self.window_size)
            }
        return self.history[symbol]

    def process_tick(self, symbol, price, volume):
        """
        Process a new tick and return a signal if any.
        """
        if price <= 0:
            return None
            
        history = self._get_history(symbol)
        prices = history['prices']
        volumes = history['volumes']

        # Update history
        prices.append(price)
        volumes.append(volume)

        # Need enough data to calculate metrics
        if len(prices) < self.window_size:
            return None

        # ---------------- LOGIC ---------------- #
        # Calculate Rolling Averages
        avg_price = statistics.mean(prices)
        avg_volume = statistics.mean(volumes) if volumes else 1

        # Calculate Forces
        # Price Force: Deviation from average (Momentum)
        # Volume Force: Relative volume intensity
        
        # Avoid division by zero
        if avg_volume == 0: avg_volume = 1

        price_force = price - avg_price
        volume_force = volume / avg_volume

        # ---------------- SIGNAL GENERATION ---------------- #
        signal = None
        
        # BUY: Strong upward deviation with volume expansion
        if price_force > self.PRICE_FORCE_THRESHOLD and volume_force > self.VOLUME_FORCE_THRESHOLD:
            signal = {
                "type": "BUY",
                "reason": "ANTI-GRAVITY BREAKOUT",
                "price": price,
                "price_force": round(price_force, 2),
                "volume_force": round(volume_force, 2)
            }

        # SELL: Strong downward deviation with volume expansion
        elif price_force < -self.PRICE_FORCE_THRESHOLD and volume_force > self.VOLUME_FORCE_THRESHOLD:
            signal = {
                "type": "SELL",
                "reason": "DOWNWARD FORCE",
                "price": price,
                "price_force": round(price_force, 2),
                "volume_force": round(volume_force, 2)
            }
        
        # Log analysis for debugging (optional, can be verbose)
        # print(f"DEBUG: {symbol} | PF: {price_force:.2f} | VF: {volume_force:.2f}")

        return signal

    def run_cycle(self):
        """
        Checks the DataBus for the latest data and processes it.
        This is intended to be called in a loop.
        """
        all_data = self.data_bus.get_all_data()
        
        for symbol, data in all_data.items():
            price = data.get('price', 0)
            volume = data.get('volume', 0)
            
            if price > 0:
                signal = self.process_tick(symbol, price, volume)
                
                if signal:
                    timestamp = "" # Add timestamp if needed
                    icon = "🚀" if signal['type'] == 'BUY' else "🔻"
                    print(f"\n{icon} {signal['type']} SIGNAL [{symbol}]")
                    print(f"   Reason: {signal['reason']}")
                    print(f"   Price: {signal['price']}")
                    print(f"   Force: Price {signal['price_force']} | Vol {signal['volume_force']}x")
                    print("-" * 40)
                    
                    # Here we would send to Execution Engine
