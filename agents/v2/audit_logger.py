
import json
from .manager import AgentEvent

class AuditLoggerAgent:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"

    def get_status(self):
        return self.status

    def log_decision(self, event):
        # We already store everything in AgentManager.event_history
        # This agent can perform additional formatting or persistence
        pass

    def get_audit_summary(self):
        return self.manager.get_audit_trail()
