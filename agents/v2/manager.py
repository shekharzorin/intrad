
import json
import datetime
import threading
import time

class AgentEvent:
    def __init__(self, symbol, agent_name, state, reason, context, confidence, payload=None):
        self.symbol = symbol
        self.timestamp = datetime.datetime.now().isoformat()
        self.agent = agent_name
        self.state = state  # APPROVED | FILTERED | NEUTRAL | REJECTED
        self.reason = reason
        self.context = context  # trend, volatility, pattern, risk_condition
        self.confidence = confidence # 0-100
        self.payload = payload or {}

    def to_dict(self):
        return {
            "agent": self.agent,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "state": self.state,
            "reason": self.reason,
            "context": self.context,
            "confidence": self.confidence,
            "payload": self.payload
        }

class AgentManager:
    def __init__(self, state):
        self.state = state
        self.agents = {}
        self.event_history = []
        self.lock = threading.Lock()

    def register_agent(self, name, agent_instance):
        self.agents[name] = agent_instance
        print(f"[AGENT] Registered: {name}")

    def emit_event(self, event):
        with self.lock:
            # We add a 'type' internally for easier UI filtering if needed, 
            # but keep the structure as requested.
            event_dict = event.to_dict()
            self.event_history.append(event_dict)
            if len(self.event_history) > 500:
                self.event_history.pop(0)
        
        # Sequentially trigger reactors if any (though we use a pipeline in server.py)
        pass

    def get_audit_trail(self, limit=50):
        with self.lock:
            return self.event_history[-limit:]

    def get_agent_statuses(self):
        statuses = {}
        for name, agent in self.agents.items():
            statuses[name] = agent.get_status()
        return statuses
