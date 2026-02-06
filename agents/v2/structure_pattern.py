
from .manager import AgentEvent

class StructurePatternAgent:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"

    def get_status(self):
        return self.status

    def process(self, symbol, ltp):
        # Detect technical events (Simulated)
        # We'll trigger a 'BOS' or 'None' based on price volatility
        
        pattern = "None"
        price_level = round(ltp, 2)
        valid = False
        
        if ltp % 10 < 1: # Random-ish trigger for demo
            pattern = "BOS"
            valid = True
        elif ltp % 10 > 9:
            pattern = "CHoCH"
            valid = True

        payload = {
            "symbol": symbol,
            "pattern": pattern,
            "price_level": price_level,
            "valid": valid
        }
        
        event = AgentEvent(
            symbol=symbol,
            agent_name="StructurePatternAgent",
            payload=payload,
            confidence=0.75 if valid else 0.0
        )
        self.manager.emit_event(event)
        return pattern if valid else None
