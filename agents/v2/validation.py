
from .manager import AgentEvent

class ValidationAgent:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"

    def get_status(self):
        return self.status

    def validate(self, symbol, ltp, context_event, pattern_event):
        # 1. Rule Validation
        mood = context_event.get("context", {}).get("trend", "Sideways")
        signal = pattern_event.get("context", {}).get("pattern", "None")
        
        allowed = False
        state = "REJECTED"
        confidence = 45
        reason = "Awaiting Trend + Structure alignment for institutional execution."
        
        # Confluence Rules
        if mood == "Bullish" and signal == "BOS":
            allowed = True
            state = "APPROVED"
            confidence = 88
            reason = "Trend + Structure aligned; Bullish Breakout confirmed with high confluence."
        elif mood == "Bearish" and signal == "CHoCH":
            allowed = True
            state = "APPROVED"
            confidence = 85
            reason = "Market character change detected; Bearish momentum confirmed via structural shift."
        elif signal != "None":
            state = "FILTERED"
            confidence = 50
            reason = f"Filtered: {mood} context does not support {signal} structural signal at this time."
        
        # 2. Cross-Agent Consistency Check
        # If Pattern is APPROVED but Context is NEUTRAL, downgrade
        if pattern_event.get("state") == "APPROVED" and context_event.get("state") == "NEUTRAL":
            confidence = min(confidence, 65)
            reason += " (Confidence downgraded: Context remains neutral despite structural break)"

        context = {
            "trend_alignment": allowed,
            "risk_reward_ratio": "1:2.0 (Targeted)",
            "HTF_agreement": True if confidence > 80 else False,
            "volume_profile": "Standard"
        }
        
        event = AgentEvent(
            symbol=symbol,
            agent_name="ValidationAgent",
            state=state,
            reason=reason,
            context=context,
            confidence=confidence,
            payload={"allowed": allowed}
        )
        self.manager.emit_event(event)
        return event.to_dict()
