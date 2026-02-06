
from .manager import AgentEvent

class MarketContextAgent:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"

    def get_status(self):
        return self.status

    def process(self, symbol, ltp, close, volume=0, vwap=0):
        # Professional AI evaluation logic
        # In a real CrewAI setup, this would use a LLM or advanced stats.
        # Here we mimic the logic with price action context.
        
        mood = "Range"
        confidence = 0.5
        reason = "Market is in a neutral consolidation phase."

        if ltp > close * 1.002:
            mood = "Bullish"
            confidence = 0.82
            reason = "Higher price levels sustained above yesterday's close with positive momentum."
        elif ltp < close * 0.998:
            mood = "Bearish"
            confidence = 0.82
            reason = "Price action showing weakness and trading below key psychological levels."
        
        payload = {
            "symbol": symbol,
            "market_mood": mood,
            "confidence": confidence,
            "reason": reason
        }
        
        event = AgentEvent(
            symbol=symbol,
            agent_name="MarketContextAgent",
            payload=payload,
            confidence=confidence
        )
        self.manager.emit_event(event)
        return mood
