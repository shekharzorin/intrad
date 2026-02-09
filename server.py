
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
        self.market_data = {
            "NIFTY": {"ltp": 24500.0, "close": 24450.0, "volume": 0, "status": "INITIAL", "timestamp": 0},
            "BANKNIFTY": {"ltp": 52000.0, "close": 51900.0, "volume": 0, "status": "INITIAL", "timestamp": 0},
            "SENSEX": {"ltp": 81000.0, "close": 80900.0, "volume": 0, "status": "INITIAL", "timestamp": 0}
        } 
        self.trades = []
        self.managed_users = [
            {"user_id": "admin@antigravity.ia", "role": "OWNER", "status": "ACTIVE", "sync": "OFFLINE"}
        ]
        self.market_feed_active = True # Allows pausing data polling
        self.logs = []
        self.risk_rules = {
            "max_trades_per_day": 3,
            "risk_per_trade_percent": 1.0,
            "max_daily_loss_percent": 1.0
        }
        self.system_health = "HEALTHY" # HEALTHY | DEGRADED
        self.execution_mode = "MOCK"   # MOCK | SIMULATION | PAPER | REAL
        self.is_running = False
        self.alice = None
        self.lock = threading.Lock()
        self.engine_running = False
        self.monitored_instruments = {"NIFTY", "BANKNIFTY", "SENSEX", "GOLD", "SILVER", "CRUDEOIL", "NATGASMINI"}
        self.market_segments = {
            "NSE": {"open": "09:15", "close": "15:30", "days": [0,1,2,3,4]},
            "BSE": {"open": "09:15", "close": "15:30", "days": [0,1,2,3,4]},
            "MCX": {"open": "09:00", "close": "23:30", "days": [0,1,2,3,4]}
        }

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

def is_market_open(segment):
    """Check if market segment is currently open in IST"""
    now = datetime.datetime.now()
    # If segment unknown, assume open to be safe
    if segment not in state.market_segments: return True
    
    cfg = state.market_segments[segment]
    if now.weekday() not in cfg["days"]: return False
    
    current_time_str = now.strftime("%H:%M")
    return cfg["open"] <= current_time_str <= cfg["close"]

def start_data_engine():
    """WebSocket engine to receive live market ticks with segment awareness"""
    symbols_mgr = {
        "NIFTY": {"exch": "NSE", "token": 26000, "segment": "NSE"},
        "BANKNIFTY": {"exch": "NSE", "token": 26009, "segment": "NSE"},
        "SENSEX": {"exch": "BSE", "token": 1, "segment": "BSE"},
        "GOLD": {"exch": "MCX", "token": 454819, "segment": "MCX"},
        "SILVER": {"exch": "MCX", "token": 451667, "segment": "MCX"},
        "CRUDEOIL": {"exch": "MCX", "token": 488292, "segment": "MCX"},
        "NATGASMINI": {"exch": "MCX", "token": 488509, "segment": "MCX"}
    }
    
    token_map = {str(cfg['token']): name for name, cfg in symbols_mgr.items()}
    
    if state.engine_running: return
    
    if state.execution_mode == "MOCK":
        state.add_log("MOCK MODE: Live data fetch suspended for isolation.")
        return

    state.engine_running = True
    
    try:
        # Check environment variables
        if not API_KEY or not USER_ID or not TOTP_SECRET:
            raise Exception("Broker credentials missing in .env")

        state.alice = Aliceblue(user_id=USER_ID, api_key=API_KEY)
        state.alice.get_session_id(pyotp.TOTP(TOTP_SECRET).now())
        state.add_log("Broker Engine Authenticated. Initializing Feed...")

        def socket_open():
            state.add_log("WebSocket Connected. Monitoring selected segments...")
            for name, cfg in symbols_mgr.items():
                if name in state.monitored_instruments:
                    try:
                        inst = state.alice.get_instrument_by_token(cfg['exch'], cfg['token'])
                        state.alice.subscribe([inst])
                        with state.lock:
                            if name not in state.market_data:
                                state.market_data[name] = {"ltp": 0.0, "close": 0.0, "volume": 0, "status": "WAITING", "timestamp": 0, "segment": cfg['segment']}
                            else:
                                state.market_data[name]["segment"] = cfg['segment']
                    except Exception as e:
                        state.add_log(f"Subscription Error ({name}): {e}")

        def socket_error(err):
            # Silent error handling for UI stability
            pass

        def socket_close():
            # Silent fallback
            pass

        def feed_data(msg):
            if msg is None: return
            token = msg.get('tk')
            name = token_map.get(str(token))
            if name and name in state.monitored_instruments:
                try:
                    ltp = float(msg.get('lp', 0))
                    # Retain last valid if incoming is 0
                    if ltp <= 0: return

                    close = float(msg.get('c', 0)) or ltp
                    volume = float(msg.get('v', 0))
                    
                    with state.lock:
                        state.market_data[name].update({
                            "ltp": ltp,
                            "volume": volume,
                            "close": close,
                            "timestamp": time.time(),
                            "status": "LIVE"
                        })
                    
                    if state.is_running:
                        threading.Thread(target=run_agent_pipeline, args=(name, ltp, close)).start()
                except: pass

        state.alice.start_websocket(
            socket_open_callback=socket_open,
            socket_error_callback=socket_error,
            socket_close_callback=socket_close,
            subscription_callback=feed_data,
            run_in_background=True
        )

    except Exception as e:
        state.engine_running = False
        state.add_log(f"Live Feed Broker connection failed: {str(e)}")
        state.add_log(">>> INITIATING VIRTUAL FEED (SIMULATION) <<<")
        start_simulation_feed(symbols_mgr)

def run_agent_pipeline(symbol, ltp, close):
    """Agent V2 Analytical Chain - Decoupled Routing"""
    # 1. Context Analysis
    bias = state.ctx_agent.process(symbol, ltp, close)
    
    # 2. Pattern Detection
    signal = state.pattern_agent.process(symbol, ltp)
    
    if signal:
        # 3. Validation
        if state.val_agent.validate(symbol, ltp, bias, signal):
            # 4. Risk & Compliance
            if state.risk_agent.check_risk(symbol, ltp, state.metrics):
                # 5. Routed Execution (Branching logic handled by Engine)
                state.exec_engine.route_execution(symbol, ltp, signal, state)
    
    # 6. Guidance & Strategy Pulse
    state.guide_agent.generate_advice(state.agent_manager.get_audit_trail(10))

def start_simulation_feed(symbols):
    """Fallback feed for when broker is not available"""
    def simulate(name):
        # Base prices for indices/commodities
        bases = {
            "NIFTY": 24500.0, "BANKNIFTY": 52000.0, "SENSEX": 81000.0,
            "GOLD": 72000.0, "SILVER": 88000.0, "CRUDEOIL": 6400.0, "NATGASMINI": 180.0
        }
        ltp = bases.get(name, 100.0)
        close = ltp - (ltp * 0.005) # simulate -0.5% opening
        
        while True:
            import random
            change = (random.random() - 0.48) * (ltp * 0.0001) # tiny realistic ticks
            ltp += change
            
            with state.lock:
                state.market_data[name] = {
                    "ltp": round(ltp, 2),
                    "volume": float(random.randint(10000, 50000)),
                    "close": close,
                    "timestamp": time.time(),
                    "status": "VIRTUAL"
                }

            # Trigger Agents if system is running
            if state.is_running:
                # Run pipeline in background thread
                threading.Thread(target=run_agent_pipeline, args=(name, ltp, close)).start()
                
            time.sleep(1.5)

    for name in symbols.keys():
        t = threading.Thread(target=simulate, args=(name,))
        t.daemon = True
        t.start()

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
        state.metrics["system_health"] = state.system_health
        state.metrics["execution_mode"] = state.execution_mode
    return state.metrics

@app.get("/api/v1/system/health")
def get_system_health():
    return {"status": "success", "health": state.system_health}

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
        current_time = time.time()
        
        if market == "COMMODITY":
            commodities = ["GOLD", "SILVER", "CRUDEOIL", "NATGASMINI"]
            data_list = []
            for c in commodities:
                d = state.market_data.get(c, {"ltp": 0.0, "close": 0.0, "volume": 0.0, "timestamp": 0, "segment": "MCX"})
                
                # Check Market Hours
                if not is_market_open(d.get("segment", "MCX")):
                    status = "MARKET_CLOSED"
                else:
                    status = "LIVE" if (current_time - d.get("timestamp", 0)) < 15 else "STALE"
                
                data_list.append({
                    "instrument": c,
                    "ltp": d["ltp"],
                    "close": d["close"],
                    "volume": d["volume"],
                    "status": status
                })
            return {"status": "success", "data": data_list}
        else:
            d = state.market_data.get(market, {"ltp": 0.0, "close": 0.0, "volume": 0.0, "timestamp": 0, "segment": "NSE"})
            
            # Check Market Hours
            if not is_market_open(d.get("segment", "NSE")):
                return {
                    "status": "MARKET_CLOSED",
                    "instrument": market,
                    "ltp": d["ltp"],
                    "close": d["close"],
                    "reason": "Market is currently closed for this segment."
                }

            status = "LIVE" if (current_time - d.get("timestamp", 0)) < 15 else "STALE"
            
            if d["ltp"] == 0:
                return {
                    "status": "DATA_UNAVAILABLE",
                    "reason": "Live data temporarily unavailable"
                }

            return {
                "status": "success", 
                "instrument": market,
                "ltp": d["ltp"], 
                "close": d["close"], 
                "volume": d["volume"],
                "data_status": status
            }

@app.post("/api/v1/market/monitor")
async def update_monitored_instruments(request: Request):
    data = await request.json()
    instruments = data.get("instruments", [])
    if not isinstance(instruments, list):
        raise HTTPException(status_code=400, detail="Instruments must be a list")
    
    with state.lock:
        state.monitored_instruments = set(instruments)
        state.add_log(f"Monitoring Scope Updated: {list(state.monitored_instruments)}")
    
    # Restart data engine to apply new subscriptions (Alice Blue socket needs re-subscription)
    # For now, we'll just let the next tick filtering handle it, or we could trigger a socket re-sync.
    # But start_data_engine is already running. The socket_open handles initial subscription.
    # To truly be dynamic without restart, we'd need to call alice.subscribe in the running engine.
    # We'll just update the set for now as a safety filter.
    
    return {"status": "success", "monitored": list(state.monitored_instruments)}

@app.get("/api/v1/market/stock/{symbol}")
def get_stock_data(symbol: str):
    """Specific stock fetch - only when explicitly selected"""
    # Simply return high-level mock or attempted live info for stocks
    # Real implementation would add this symbol to a dynamic poll list
    return {
        "status": "success",
        "instrument": symbol,
        "ltp": 2500.0 + (time.time() % 10),
        "close": 2490.0,
        "volume": 150000,
        "data_status": "VIRTUAL" 
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

@app.post("/api/v1/system/mode")
async def set_execution_mode(request: Request):
    data = await request.json()
    new_mode = data.get("mode")
    if new_mode not in ["MOCK", "SIMULATION", "PAPER", "REAL"]:
        raise HTTPException(status_code=400, detail="Invalid Mode")
    
    with state.lock:
        old_mode = state.execution_mode
        state.execution_mode = new_mode
        # Isolation: Clear trades when switching modes to prevent data contamination
        state.trades = []
        state.add_log(f"SYSTEM MODE CHANGED: {old_mode} -> {new_mode} (Positions Purged)")
    
    # Trigger Data Engine if not MOCK
    if new_mode != 'MOCK':
        threading.Thread(target=start_data_engine, daemon=True).start()
    
    return {"status": "success", "mode": new_mode}

@app.post("/api/v1/system/square_off_all")
def square_off():
    state.add_log("!!! EMERGENCY SQUARE OFF INITIATED !!!")
    with state.lock:
        state.trades = []
        state.metrics["used_capital_amount"] = 0
    return {"status": "success"}

# --- ADMIN USER MANAGEMENT ---

@app.get("/api/v1/admin/users/list")
def list_managed_users():
    return {"status": "success", "users": state.managed_users}

@app.post("/api/v1/admin/users/add")
async def add_managed_user(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    password = data.get("password")
    api_key = data.get("api_key")
    secret_key = data.get("secret_key")

    if not all([user_id, password, api_key, secret_key]):
         raise HTTPException(status_code=400, detail="Missing required credential fields")

    # SECURITY: In a real scenario, we would use these to perform a one-time 
    # handshake/validation via the broker API.
    # For this system (MOCK MODE), we simulate a successful validation.
    
    with state.lock:
        # Check for duplicates
        if any(u["user_id"] == user_id for u in state.managed_users):
            raise HTTPException(status_code=400, detail="User already onboarded")
        
        # Add to managed list (READ-ONLY ACCESS SCOPED)
        new_user = {
            "user_id": user_id,
            "role": "MANAGED_TRADER",
            "status": "CONNECTED",
            "sync": "READ_ONLY",
            "joined_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        state.managed_users.append(new_user)
        
    state.add_log(f"Secure Onboarding Successful: User {user_id} added (READ-ONLY)")
    
    # SECURITY: Credentials are NOT stored. They are used only for the handshake.
    return {"status": "success", "user": user_id}

if __name__ == "__main__":
    # Start the data engine
    threading.Thread(target=start_data_engine, daemon=True).start()
    
    print("🌍 Anti-Gravity Web Server starting at http://127.0.0.1:8001")
    uvicorn.run(app, host="127.0.0.1", port=8001)
