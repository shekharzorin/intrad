
import os
import json
import threading
import time
import datetime
import hashlib
import pyotp
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
from dotenv import load_dotenv
import websocket
from pya3 import Aliceblue

# --- AGENT V2 IMPORTS ---
from agents.v2.manager import AgentManager
from agents.v2.market_context import MarketContextAgent
from agents.v2.structure_pattern import StructurePatternAgent
from agents.v2.validation import ValidationAgent
from agents.v2.risk_capital import RiskCapitalAgent
from agents.v2.execution_engine import ExecutionEngine
from agents.v2.audit_logger import AuditLoggerAgent
from agents.v2.guidance_agent import GuidanceAgent

# ---------------- CONFIG & STATE ---------------- #
load_dotenv()
API_KEY = os.getenv("ALICEBLUE_API_KEY")
USER_ID = os.getenv("ALICEBLUE_USER_ID")
TOTP_SECRET = os.getenv("ALICEBLUE_TOTP_SECRET")

class GlobalExchangeState:
    def __init__(self):
        self.metrics = {
            "total_capital": 100000.0,
            "used_capital_amount": 0.0,
            "daily_pnl": 0.0,
            "max_drawdown": 0.0,
            "risk_used_percent": 0.0
        }
        self.market_data = {} # {symbol: {ltp, volume, close}}
        self.trades = []
        self.logs = []
        self.risk_rules = {
            "max_trades_per_day": 3,
            "risk_per_trade_percent": 1.0,
            "max_daily_loss_percent": 1.0
        }
        self.is_running = False
        self.alice = None
        self.lock = threading.Lock()

        # --- AGENT V2 CORE ---
        self.agent_manager = AgentManager(self)
        self.ctx_agent = MarketContextAgent(self.agent_manager)
        self.pattern_agent = StructurePatternAgent(self.agent_manager)
        self.val_agent = ValidationAgent(self.agent_manager)
        self.risk_agent = RiskCapitalAgent(self.agent_manager)
        self.exec_engine = ExecutionEngine(self.agent_manager)
        self.audit_agent = AuditLoggerAgent(self.agent_manager)
        self.guide_agent = GuidanceAgent(self.agent_manager)

        self.agent_manager.register_agent("MarketContext", self.ctx_agent)
        self.agent_manager.register_agent("StructurePattern", self.pattern_agent)
        self.agent_manager.register_agent("Validation", self.val_agent)
        self.agent_manager.register_agent("RiskCapital", self.risk_agent)
        self.agent_manager.register_agent("Execution", self.exec_engine)
        self.agent_manager.register_agent("AuditLogger", self.audit_agent)
        self.agent_manager.register_agent("Guidance", self.guide_agent)

    def add_log(self, message):
        ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        with self.lock:
            self.logs.append({"timestamp": ts, "message": message})
            if len(self.logs) > 100: self.logs.pop(0)

state = GlobalExchangeState()

# ---------------- ALICE BLUE ENGINE ---------------- #

def start_data_engine():
    """Background thread to fetch live data"""
    try:
        state.alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
        state.alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
        state.add_log("Broker Engine Connected Successfully")
        
        # Define trackable symbols
        symbols = {
            "NIFTY": {"exch": "NSE", "token": 26000},
            "BANKNIFTY": {"exch": "NSE", "token": 26009},
            "SENSEX": {"exch": "BSE", "token": 1},
            "GOLD": {"exch": "MCX", "token": 454819},
            "SILVER": {"exch": "MCX", "token": 451667},
            "CRUDEOIL": {"exch": "MCX", "token": 488292},
            "NATGASMINI": {"exch": "MCX", "token": 488509}
        }

        # Independent Poller for each
        def poll_instrument(name, exch, token):
            inst = state.alice.get_instrument_by_token(exch, token)
            while True:
                try:
                    res = state.alice.get_scrip_info(inst)
                    if res and res.get('stat') == 'Ok':
                        ltp = float(res.get('LTP', 0))
                        close = float(res.get('c', 0)) or ltp
                        with state.lock:
                            state.market_data[name] = {
                                "ltp": ltp,
                                "volume": float(res.get('v', 0)),
                                "close": close
                            }
                        
                        # Trigger Agent V2 Pipeline
                        if state.is_running:
                            threading.Thread(target=run_agent_pipeline, args=(name, ltp, close)).start()
                except: pass
                time.sleep(1.0)

        def run_agent_pipeline(symbol, ltp, close):
            """Agent V2 Analytical Chain (Simulation Only)"""
            # 1. Context
            bias = state.ctx_agent.process(symbol, ltp, close)
            
            # 2. Pattern
            signal = state.pattern_agent.process(symbol, ltp)
            
            if signal:
                # 3. Validation
                if state.val_agent.validate(symbol, ltp, bias, signal):
                    # 4. Risk
                    if state.risk_agent.check_risk(symbol, ltp, state.metrics):
                        # 5. Execution (SIMULATION)
                        state.exec_engine.execute_paper_trade(symbol, ltp, signal, state)
            
            # 6. Final Advisory
            state.guide_agent.generate_advice(state.agent_manager.get_audit_trail(10))

        for name, cfg in symbols.items():
            t = threading.Thread(target=poll_instrument, args=(name, cfg['exch'], cfg['token']))
            t.daemon = True
            t.start()

    except Exception as e:
        state.add_log(f"Broker connection failed: {str(e)}")

# ---------------- WEB SERVER ---------------- #

app = FastAPI()

# Ensure static directory exists
if not os.path.exists("static"):
    os.makedirs("static")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def get_index():
    return FileResponse("static/index.html")

@app.post("/api/v1/auth/login")
async def login(request: Request):
    data = await request.json()
    # Accept anything for local dashboard demo
    return {"status": "success", "mode": "MOCK", "user": data.get("user_id")}

@app.post("/api/v1/auth/register")
async def register(request: Request):
    return {"status": "success", "message": "OTP Sent Successfully (Mock)"}

@app.post("/api/v1/auth/forgot-password")
async def forgot_password(request: Request):
    return {"status": "success", "message": "Recovery link sent (Mock)"}

@app.get("/api/v1/dashboard/metrics")
def get_metrics():
    # Update pnl simulation based on market
    with state.lock:
        # Simulate some PnL fluctuation
        state.metrics["daily_pnl"] += (time.time() % 10 - 5) * 10 
    return state.metrics

@app.get("/api/v1/trades/open")
def get_trades():
    return state.trades

@app.get("/api/v1/alerts/logs")
def get_logs():
    return state.logs

@app.get("/api/v1/risk/rules")
def get_rules():
    return state.risk_rules

@app.get("/api/v1/market/ohlc/{market}")
def get_market_ohlc(market: str):
    with state.lock:
        if market == "COMMODITY":
            # Return all commodities for the frontend to filter
            commodities = ["GOLD", "SILVER", "CRUDEOIL", "NATGASMINI"]
            data_list = []
            for c in commodities:
                d = state.market_data.get(c, {"ltp": 0.0, "close": 0.0, "volume": 0.0})
                data_list.append({
                    "instrument": c,
                    "ltp": d["ltp"],
                    "close": d["close"],
                    "volume": d["volume"]
                })
            return {"status": "success", "data": data_list}
        else:
            d = state.market_data.get(market, {"ltp": 25000.0, "close": 24950.0, "volume": 0.0})
            return {
                "status": "success", 
                "instrument": market,
                "ltp": d["ltp"], 
                "close": d["close"], 
                "volume": d["volume"]
            }

@app.get("/api/v1/account/balance")
def get_balance():
    # Return simulated balance based on total_capital
    return {"status": "success", "balance": state.metrics["total_capital"]}

@app.get("/api/v1/agents/status")
def get_agent_status():
    return state.agent_manager.get_agent_statuses()

@app.get("/api/v1/agents/audit")
def get_audit_trail():
    return state.agent_manager.get_audit_trail()

@app.post("/api/v1/agents/guidance/on-demand")
async def get_on_demand_guidance():
    # Collect some context for the prompt
    recent_events = state.agent_manager.get_audit_trail(15)
    context_str = json.dumps(recent_events)
    advice = state.guide_agent.get_on_demand_advice(context_str)
    return {"status": "success", "advice": advice}

@app.post("/api/v1/settings/risk")
async def update_risk(request: Request):
    data = await request.json()
    with state.lock:
        state.risk_rules.update(data)
        state.metrics["total_capital"] = data.get("total_capital", state.metrics["total_capital"])
    state.add_log("Risk Protocols Updated via API")
    return {"status": "success"}

@app.post("/api/v1/settings/capital")
async def update_capital(request: Request):
    data = await request.json()
    with state.lock:
        state.metrics["total_capital"] = data.get("amount", state.metrics["total_capital"])
    state.add_log(f"Capital Allocation Updated: ₹{state.metrics['total_capital']}")
    return {"status": "success"}

@app.post("/api/v1/system/start")
def system_start():
    state.is_running = True
    state.add_log(">>> ALGO SYSTEM STARTED: LIVE MONITORING <<<")
    return {"status": "success"}

@app.post("/api/v1/system/square_off_all")
def square_off():
    state.add_log("!!! EMERGENCY SQUARE OFF INITIATED !!!")
    with state.lock:
        state.trades = []
        state.metrics["used_capital_amount"] = 0
    return {"status": "success"}

if __name__ == "__main__":
    # Start the data engine
    threading.Thread(target=start_data_engine, daemon=True).start()
    
    print("🌍 Anti-Gravity Web Server starting at http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
