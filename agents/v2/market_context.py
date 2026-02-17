
from .manager import AgentEvent

class MarketContextAgent:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"

    def get_status(self):
        return self.status

    def process(self, symbol, ltp, close, volume=0, vwap=0):
        # 1. Trend Analysis
        diff_pct = (ltp - close) / close if close > 0 else 0
        trend = "Sideways"
        state = "NEUTRAL"
        confidence = 55  # Base confidence for neutral
        
        if diff_pct > 0.002:
            trend = "Bullish"
            state = "APPROVED"
            confidence = 82
        elif diff_pct < -0.002:
            trend = "Bearish"
            state = "APPROVED"
            confidence = 82
        
        # 2. Volatility Analysis (Simulated regime)
        volatility = "Low"
        if abs(diff_pct) > 0.01:
            volatility = "High"
        elif abs(diff_pct) > 0.005:
            volatility = "Moderate"

        # 3. Liquidity & Session (Contextual metadata)
        liquidity = "High" if volume > 1000 or volume == 0 else "Moderate"
        session_bias = "Neutral"
        
        reason = f"Market is in a {trend.lower()} phase with {volatility.lower()} volatility."
        if state == "NEUTRAL":
            reason = "Market is in a neutral consolidation phase. Awaiting volatility expansion."
            confidence = min(confidence, 60)

        context = {
            "trend": trend,
            "volatility": volatility,
            "liquidity": liquidity,
            "session_bias": session_bias
        }
        
        event = AgentEvent(
            symbol=symbol,
            agent_name="MarketContextAgent",
            state=state,
            reason=reason,
            context=context,
            confidence=confidence,
            payload={"ltp": ltp, "close": close}
        )
        self.manager.emit_event(event)
        return event.to_dict()
