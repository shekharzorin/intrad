
import os
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

    def get_status(self):
        return self.status

    def generate_gpt_response(self, prompt):
        if not self.client:
            return "AI Advisor offline: API Key missing or invalid."
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional Institutional Trading AI Advisor. Your tone is technical, strategic, and protective of capital. Explain trading decisions clearly."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Strategic Link Interrupted: {str(e)}"

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
