
import random
from .manager import AgentEvent

class ExecutionEngine:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"
        self.last_trade_id = 0

    def get_status(self):
        return self.status

    def execute_paper_trade(self, symbol, ltp, signal, state):
        self.last_trade_id += 1
        trade_id = f"SIM-{self.last_trade_id:03}"
        
        # Open virtual position
        entry_price = ltp
        # For simulation, we'll immediately "close" or track it
        # Here we just emit the execution event 
        
        payload = {
            "trade_id": trade_id,
            "symbol": symbol,
            "entry": entry_price,
            "signal": signal,
            "status": "OPEN",
            "mode": "SIMULATION"
        }
        
        # Add to state.trades for UI display
        new_trade = {
            "id": trade_id,
            "instrument": symbol,
            "direction": "LONG", # Simplified
            "lots": 1,
            "quantity": 50,
            "entry_price": entry_price,
            "current_price": entry_price,
            "pnl": 0,
            "status": "OPEN",
            "timestamp": "ISO..."
        }
        
        with state.lock:
            state.trades.append(new_trade)
            if len(state.trades) > 50: state.trades.pop(0)

        event = AgentEvent(
            symbol=symbol,
            agent_name="ExecutionAgent",
            payload=payload,
            confidence=1.0
        )
        self.manager.emit_event(event)
        return trade_id
