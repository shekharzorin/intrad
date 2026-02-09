import os
import time
from openai import OpenAI
from .manager import AgentEvent

class GuidanceAgent:
    def __init__(self, manager):
        self.manager = manager
        self.status = "ACTIVE"
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = None
        
        if self.api_key:
            try:
                self.client = OpenAI(api_key=self.api_key)
            except Exception as e:
                print(f"❌ Failed to initialize OpenAI client: {e}")
        
        # Exponential Backoff & Cooldown
        self.last_retry_time = 0
        self.cooldown_period = 60 # Start with 60s cooldown for 429

    def get_status(self):
        return self.status

    def generate_gpt_response(self, prompt):
        if not self.client:
            return "AI Advisor offline: API Key missing or invalid."
        
        # Check Cooldown
        if "PAUSED" in self.status:
            if time.time() - self.last_retry_time < self.cooldown_period:
                return "Strategic Insight Paused: Re-evaluating API capacity... (Cooldown Active)"
        
        try:
            self.last_retry_time = time.time()
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional Institutional Trading AI Advisor. Your tone is technical, strategic, and protective of capital. Explain trading decisions clearly."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.3
            )
            # Reset status if it was paused
            if self.status == "PAUSED (QUOTA LIMIT)":
                self.status = "ACTIVE"
                self.manager.state.system_health = "HEALTHY"
                self.cooldown_period = 60 # Reset to base
            return response.choices[0].message.content
        except Exception as e:
            err_msg = str(e)
            if "insufficient_quota" in err_msg or "429" in err_msg:
                self.status = "PAUSED (QUOTA LIMIT)"
                self.manager.state.system_health = "DEGRADED"
                # Exponential Backoff
                self.cooldown_period = min(self.cooldown_period * 2, 3600) # Max 1 hour
                return "Strategic Insight Paused: Awaiting API quota refresh or plan upgrade. Core system operations remain unaffected."
            return f"Strategic Link Interrupted: {err_msg}"

    def generate_advice(self, last_events):
        # Default Logic
        basic_advice = "System is scanning for high-probability setups."
        
        for e in reversed(last_events):
            if e['agent'] == 'RiskAgent' and e['payload'].get('allowed') == False:
                basic_advice = f"🚨 ADVICE: Trade blocked because {e['payload'].get('reason')}. This protects your remaining capital."
                break
            if e['agent'] == 'ValidationAgent' and e['payload'].get('entry_allowed') == False:
                basic_advice = f"ℹ️ ADVICE: Entry rejected! {e['payload'].get('reason')} Wait for higher-confidence confluence."
                break
            if e['agent'] == 'ExecutionAgent':
                basic_advice = f"🎯 ADVICE: Trade executed! Monitoring SL/TP targets based on structural volatility."
                break

        # If GPT is enabled, we could potentially enrich this, 
        # but for the "automatic" mode we'll stick to basic to save tokens.
        # User explicitly asked to respond when clicked.

        payload = {
            "advice": basic_advice,
            "style": "ChatGPT-Guide"
        }
        
        event = AgentEvent(
            symbol="GLOBAL",
            agent_name="GuidanceAgent",
            payload=payload,
            confidence=1.0
        )
        self.manager.emit_event(event)
        return basic_advice

    def get_on_demand_advice(self, context_summary):
        prompt = f"Analyze this current trading state and provide a 2-sentence institutional advice: {context_summary}"
        gpt_advice = self.generate_gpt_response(prompt)
        
        payload = {
            "advice": gpt_advice,
            "style": "ChatGPT-Premium"
        }
        
        event = AgentEvent(
            symbol="GLOBAL",
            agent_name="GuidanceAgent",
            payload=payload,
            confidence=1.0
        )
        self.manager.emit_event(event)
        return gpt_advice
