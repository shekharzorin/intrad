
from .manager import AgentEvent

class RiskCapitalAgent:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"

    def get_status(self):
        return self.status

    def check_risk(self, symbol, ltp, metrics):
        # Rules: 1% max loss per trade, 1% max daily loss
        total_cap = metrics.get("total_capital", 100000)
        daily_pnl = metrics.get("daily_pnl", 0)
        
        allowed = True
        reason = "Risk checks passed."
        
        # 1% Daily Loss Limit
        if daily_pnl < - (total_cap * 0.01):
            allowed = False
            reason = "Daily loss limit (1%) reached. Trading suspended."
            self.status = "BLOCKED"
        
        # No duplicate entries (Mock check)
        # In a real system we'd check state.trades
        
        lot_size = 1
        capital_used_pct = round((ltp * 1 / total_cap) * 100, 2)

        payload = {
            "symbol": symbol,
            "lot_size": lot_size,
            "capital_used_pct": capital_used_pct,
            "allowed": allowed,
            "reason": reason
        }
        
        event = AgentEvent(
            symbol=symbol,
            agent_name="RiskAgent",
            state="APPROVED" if allowed else "REJECTED",
            reason=reason,
            context={
                "daily_pnl": daily_pnl,
                "capital_limit_pct": 1.0,
                "utilization_pct": capital_used_pct,
                "risk_condition": "Nominal" if allowed else "Critical"
            },
            confidence=100,
            payload=payload
        )
        self.manager.emit_event(event)
        return allowed
