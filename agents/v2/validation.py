
from .manager import AgentEvent

class ValidationAgent:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"

    def get_status(self):
        return self.status

    def validate(self, symbol, ltp, mood, signal):
        # Entry validation rules
        allowed = False
        reason = "Awaiting Trend + VWAP alignment."
        
        if mood == "Bullish" and signal == "BOS":
            allowed = True
            reason = "Trend + Structure aligned; Bullish Breakout confirmed."
        elif mood == "Bearish" and signal == "CHoCH":
            allowed = True
            reason = "Market character change detected; Bearish momentum confirmed."
        else:
            reason = f"Filtered: {mood} context does not support {signal} signal."

        payload = {
            "symbol": symbol,
            "entry_allowed": allowed,
            "reason": reason
        }
        
        event = AgentEvent(
            symbol=symbol,
            agent_name="ValidationAgent",
            payload=payload,
            confidence=0.9
        )
        self.manager.emit_event(event)
        return allowed
