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
        # 1. Analyze Reasoning Hierarchy
        weakest_confidence = 100
        primary_reason = "System is scanning for high-probability setups."
        decision = "NEUTRAL"
        conflicting_factors = []
        
        # Agents we care about in the chain
        relevant_agents = ["MarketContextAgent", "StructurePatternAgent", "ValidationAgent", "RiskAgent"]
        contributing_events = [e for e in last_events if e['agent'] in relevant_agents]
        
        if contributing_events:
            # Sort by timestamp to get latest context
            contributing_events.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # Find the weakest link
            for e in contributing_events:
                conf = e.get('confidence', 0)
                if conf < weakest_confidence and conf > 0:
                    weakest_confidence = conf
                
                # Check for rejections/filters
                if e.get('state') in ['REJECTED', 'FILTERED'] or e.get('payload', {}).get('allowed') == False:
                    decision = "REJECTED"
                    primary_reason = e.get('reason', "Filtered by logic engine.")
                    if e['agent'] not in conflicting_factors:
                        conflicting_factors.append(e['agent'])

            # If none rejected, check if approved
            if decision != "REJECTED":
                validation = next((e for e in contributing_events if e['agent'] == 'ValidationAgent'), None)
                if validation and validation.get('state') == 'APPROVED':
                    decision = "APPROVED"
                    primary_reason = validation.get('reason', "Confluence detected.")
                
        # 2. Finalize Advice
        summary = f"Decision: {decision} | {primary_reason}"
        if conflicting_factors:
            summary += f" (Conflicts: {', '.join(conflicting_factors)})"
        
        # Confidence Calibration Rules
        final_confidence = min(weakest_confidence, 95)
        if decision == "NEUTRAL":
            final_confidence = min(final_confidence, 60)

        context = {
            "decision": decision,
            "primary_reason": primary_reason,
            "conflicting_factors": conflicting_factors,
            "reasoning_hierarchy": "MarketContext -> Structure -> Validation -> Risk"
        }
        
        event = AgentEvent(
            symbol="GLOBAL",
            agent_name="GuidanceAgent",
            state=decision,
            reason=summary,
            context=context,
            confidence=final_confidence,
            payload={"advice": summary}
        )
        self.manager.emit_event(event)
        return summary

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
            state="APPROVED",
            reason=gpt_advice,
            context={
                "decision": "ON_DEMAND_INSIGHT",
                "source": "GPT-CORE",
                "reasoning_hierarchy": "Ad-Hoc Analysis"
            },
            confidence=90,
            payload={"advice": gpt_advice, "style": "ChatGPT-Premium"}
        )
        self.manager.emit_event(event)
        return gpt_advice
