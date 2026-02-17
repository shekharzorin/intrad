import datetime
from .manager import AgentEvent

class ExecutionEngine:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"
        self.last_trade_id = 0

    def get_status(self):
        return self.status

    def route_execution(self, symbol, ltp, signal, state):
        """Primary router based on global system state"""
        mode = state.execution_mode
        
        if mode == "MOCK":
            return self.execute_mock(symbol, ltp, signal, state)
        elif mode == "SIMULATION":
            return self.execute_simulation(symbol, ltp, signal, state)
        elif mode == "PAPER":
            return self.execute_paper(symbol, ltp, signal, state)
        elif mode == "REAL":
            return self.execute_real(symbol, ltp, signal, state)
        return None

    def execute_mock(self, symbol, ltp, signal, state):
        state.add_log(f"[MOCK] Signal {signal} detected for {symbol} @ {ltp}. No action taken.")
        return "MOCK-MODE"

    def execute_simulation(self, symbol, ltp, signal, state):
        return self._place_virtual_order(symbol, ltp, signal, state, "SIMULATION")

    def execute_paper(self, symbol, ltp, signal, state):
        return self._place_virtual_order(symbol, ltp, signal, state, "PAPER")

    def execute_real(self, symbol, ltp, signal, state):
        if not state.alice:
            state.add_log("[REAL] CRITICAL: Broker not connected. Order BLOCKED for safety.")
            return None
            
        try:
            # Placeholder for actual Alice Blue order placement
            # res = state.alice.place_order(transaction_type=BuySell.Buy if signal=='BUY' else BuySell.Sell, ...)
            state.add_log(f"[REAL] >>> PLACING LIVE BROKER ORDER: {symbol} | {signal} @ {ltp}")
            # In real, we would wait for broker response and update state
            return "LIVE-ORD"
        except Exception as e:
            state.add_log(f"[REAL] BROKER REJECTION: {str(e)}")
            return None

    def _place_virtual_order(self, symbol, ltp, signal, state, mode_label):
        self.last_trade_id += 1
        prefix = "SIM" if mode_label == "SIMULATION" else "PAP"
        trade_id = f"{prefix}-{self.last_trade_id:03}"
        
        # Isolated Trade Object
        new_trade = {
            "id": trade_id,
            "instrument": symbol,
            "direction": "LONG" if signal == "BUY" else "SHORT",
            "lots": 1,
            "quantity": 50,
            "entry_price": ltp,
            "current_price": ltp,
            "pnl": 0.0,
            "status": "OPEN",
            "mode": mode_label,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with state.lock:
            state.trades.append(new_trade)
            if len(state.trades) > 50: state.trades.pop(0)

        # Emit audit event
        self.manager.emit_event(AgentEvent(
            symbol=symbol,
            agent_name="ExecutionAgent",
            state="APPROVED",
            reason=f"Virtual order {trade_id} executed at {ltp}. Institutional fill simulation complete.",
            context={
                "trade_id": trade_id,
                "mode": mode_label,
                "signal": signal,
                "entry_price": ltp
            },
            confidence=100,
            payload={
                "trade_id": trade_id, 
                "mode": mode_label, 
                "signal": signal, 
                "entry": ltp,
                "note": "Virtual fill executed"
            }
        ))
        
        state.add_log(f"[{mode_label}] Virtual fill confirmed: {trade_id} for {symbol}")
        return trade_id
