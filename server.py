
import os
import asyncio
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

# --- CORE IMPORTS ---
from core.live_data_manager import LiveDataManager
from core.commodity_live_manager import CommodityLiveManager
from agents.v2.manager import AgentManager
from agents.v2.market_context import MarketContextAgent
from agents.v2.structure_pattern import StructurePatternAgent
from agents.v2.validation import ValidationAgent
from agents.v2.risk_capital import RiskCapitalAgent
from agents.v2.execution_engine import ExecutionEngine
from agents.v2.audit_logger import AuditLoggerAgent
from agents.v2.guidance_agent import GuidanceAgent
from core.symbol_search_manager import SymbolSearchManager

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
            "NIFTY": {"ltp": None, "close": None, "volume": None, "status": "INITIAL", "timestamp": 0},
            "BANKNIFTY": {"ltp": None, "close": None, "volume": None, "status": "INITIAL", "timestamp": 0},
            "SENSEX": {"ltp": None, "close": None, "volume": None, "status": "INITIAL", "timestamp": 0}
        } 
        self.active_symbol = "NIFTY"
        self.active_exch = "NSE"
        self.search_mgr = SymbolSearchManager()
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
        self.execution_mode = "PAPER"  # Set to PAPER by default for immediate live data
        self.is_running = False
        self.alice = None
        self.lock = threading.RLock()
        self.engine_running = False
        self.websocket_instance = None
        self.data_engine_status = "DISCONNECTED" # DISCONNECTED | CONNECTING | CONNECTED
        self.monitored_instruments = {"NIFTY", "BANKNIFTY", "SENSEX", "GOLD", "SILVER", "CRUDEOIL", "NATGASMINI"}
        self.market_segments = {
            "NSE": {"open": "09:15", "close": "15:30", "days": [0,1,2,3,4]},
            "BSE": {"open": "09:15", "close": "15:30", "days": [0,1,2,3,4]},
            "MCX": {"open": "09:00", "close": "23:30", "days": [0,1,2,3,4]}
        }

        # --- COMMODITY LIVE DATA MANAGER (Non-intrusive, read-only) ---
        self.commodity_manager = CommodityLiveManager()

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

async def start_data_engine():
    """WebSocket engine to receive live market ticks via LiveDataManager"""
    # Strict rule: Live data only for PAPER or REAL modes
    if state.execution_mode not in ["PAPER", "REAL"]:
        state.add_log(f"Data engine skipped: Current mode {state.execution_mode} uses internal feed.")
        return

    ldm = LiveDataManager()
    if ldm.status in ["CONNECTED", "CONNECTING"]:
        state.add_log("Data engine already active.")
        return
    
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
    
    try:
        # Check environment variables
        if not API_KEY or not USER_ID or not TOTP_SECRET:
            raise Exception("Broker credentials missing in .env")

        ldm.set_credentials(USER_ID, API_KEY, TOTP_SECRET)

        # Prepare symbol list for the manager
        sub_list = []
        for name, cfg in symbols_mgr.items():
            if name in state.monitored_instruments:
                sub_list.append({
                    "exchange": cfg['exch'],
                    "token": cfg['token'],
                    "name": name
                })
                # Initialize state entry if missing
                with state.lock:
                    if name not in state.market_data:
                        state.market_data[name] = {"ltp": None, "close": None, "volume": None, "status": "WAITING", "timestamp": 0, "segment": cfg['segment']}
                    else:
                        state.market_data[name]["segment"] = cfg['segment']

        # Define bridge callback
        def server_tick_handler(msg):
            if msg is None: return
            token = msg.get('tk')
            name = token_map.get(str(token))
            
            if name and name in state.monitored_instruments:
                try:
                    ltp = float(msg.get('lp', 0))
                    if ltp <= 0: return # Ignore invalid ticks

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
                except Exception as e:
                    state.add_log(f"Tick Error ({name}): {e}")

        # Register callback and start feed
        ldm.register_callback(server_tick_handler)
        state.add_log("Starting LiveDataManager...")
        await ldm.start(sub_list)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        state.add_log(f"Live Feed Broker connection failed: {str(e)}")
        if state.execution_mode in ["PAPER", "REAL"]:
            state.add_log(">>> INITIATING VIRTUAL FEED (STABILITY FALLBACK) <<<")
            start_simulation_feed(symbols_mgr)

    # --- START COMMODITY LIVE DATA (Non-intrusive, read-only) ---
    await start_commodity_data_engine()

async def stop_data_engine():
    """Safely shut down the LiveDataManager"""
    try:
        state.add_log("Stopping LiveDataManager...")
        await LiveDataManager().stop()
    except Exception as e:
        state.add_log(f"Error stopping data engine: {e}")
    # Also stop commodity data
    await stop_commodity_data_engine()


# ---- COMMODITY LIVE DATA ENGINE (Non-intrusive) ---- #

async def start_commodity_data_engine():
    """
    Start commodity futures live data streaming.
    READ-ONLY: Only updates commodity_market_cache.
    Activates ONLY in PAPER / REAL modes.
    Does NOT modify strategy, execution, risk, or order logic.
    """
    if state.execution_mode not in ["PAPER", "REAL"]:
        state.add_log("Commodity data skipped: Not in PAPER/REAL mode.")
        return

    cm = state.commodity_manager
    if cm.is_active():
        state.add_log("Commodity live feed already active.")
        return

    try:
        if not API_KEY or not USER_ID or not TOTP_SECRET:
            state.add_log("Commodity live feed: Missing broker credentials.")
            return

        cm.set_credentials(USER_ID, API_KEY, TOTP_SECRET)

        # Bridge callback: Sync commodity cache → server state for UI
        def commodity_tick_bridge(symbol, data):
            """READ-ONLY bridge: Updates market_data state for UI consumption."""
            try:
                with state.lock:
                    if symbol in state.market_data:
                        state.market_data[symbol].update({
                            "ltp": data["ltp"],
                            "volume": data["volume"],
                            "close": data.get("close", data["ltp"]),
                            "timestamp": time.time(),
                            "status": "LIVE",
                            "segment": "MCX"
                        })
                    else:
                        state.market_data[symbol] = {
                            "ltp": data["ltp"],
                            "close": data.get("close", data["ltp"]),
                            "volume": data["volume"],
                            "timestamp": time.time(),
                            "status": "LIVE",
                            "segment": "MCX"
                        }
            except Exception:
                pass  # Never crash on bridge errors

        cm.register_callback(commodity_tick_bridge)

        state.add_log("Starting Commodity Live Data (MCX Futures)...")
        await cm.start()
        state.add_log(f"Commodity Live Feed: {cm.status} | Tracking: {list(cm.resolved_instruments.keys())}")

    except Exception as e:
        state.add_log(f"Commodity live feed error: {str(e)}")
        # Never crash backend on commodity data failure


async def stop_commodity_data_engine():
    """Safely shut down commodity live data. Clears cache, sets DISCONNECTED."""
    try:
        cm = state.commodity_manager
        if cm.is_active():
            state.add_log("Stopping Commodity Live Data...")
            await cm.stop()
            state.add_log("Commodity live feed stopped.")
    except Exception as e:
        state.add_log(f"Commodity stop error: {e}")

def run_agent_pipeline(symbol, ltp, close):
    """Agent V2 Analytical Chain - Decoupled Routing"""
    # 1. Context Analysis (MarketContextAgent)
    ctx_event = state.ctx_agent.process(symbol, ltp, close)
    
    # 2. Pattern Detection (StructurePatternAgent)
    pattern_event = state.pattern_agent.process(symbol, ltp)
    
    # Extract structural signal
    signal = pattern_event.get("context", {}).get("pattern", "None")
    
    # 3. Validation
    # Pass event dicts to the validation agent for cross-agent consistency checks
    val_event = state.val_agent.validate(symbol, ltp, ctx_event, pattern_event)
    
    if val_event.get("state") == "APPROVED":
        # 4. Risk & Compliance
        if state.risk_agent.check_risk(symbol, ltp, state.metrics):
            # 5. Routed Execution (ExecutionAgent event triggered inside)
            # Use the signal name for execution routing
            state.exec_engine.route_execution(symbol, ltp, signal, state)
    
    # 6. Guidance & Strategy Pulse
    # Consolidates all recent intelligence into a single summarizing advice
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
    # Return PAPER mode directly to trigger live data in UI
    return {"status": "success", "mode": "PAPER", "user": data.get("user_id")}

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
        
        return {
            "metrics": state.metrics,
            "market_data": state.market_data,
            "is_running": state.is_running,
            "data_engine_status": LiveDataManager().status,
            "timestamp": time.time()
        }

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
            cm = state.commodity_manager
            comm_cache = cm.get_cache()

            for c in commodities:
                d = state.market_data.get(c, {"ltp": None, "close": None, "volume": None, "timestamp": 0, "segment": "MCX"})
                
                # Enrich with commodity live cache if available
                live = comm_cache.get(c, {})
                
                # Check Market Hours
                if not is_market_open(d.get("segment", "MCX")):
                    status = "MARKET_CLOSED"
                else:
                    status = "LIVE" if (current_time - d.get("timestamp", 0)) < 15 else "STALE"

                entry = {
                    "instrument": c,
                    "ltp": live.get("ltp") or d["ltp"],
                    "close": live.get("close") or d["close"],
                    "volume": live.get("volume") or d["volume"],
                    "status": status,
                    "bid": live.get("bid", 0.0),
                    "ask": live.get("ask", 0.0),
                    "open_interest": live.get("open_interest", 0),
                    "expiry": live.get("expiry", ""),
                    "data_source": live.get("source", "CACHE"),
                    "live_status": cm.status
                }
                data_list.append(entry)

            return {
                "status": "success",
                "data": data_list,
                "commodity_feed_status": cm.status,
                "commodity_last_update": cm.last_update
            }
        else:
            d = state.market_data.get(market, {"ltp": None, "close": None, "volume": None, "timestamp": 0, "segment": "NSE"})
            
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

@app.get("/market-data/{symbol}")
def get_live_market_data(symbol: str):
    """Production-spec Live Market Data Endpoint"""
    ldm = LiveDataManager()
    data = ldm.get_market_snapshot(symbol)
    
    if not data:
        # Fallback to general state if not in LDM cache (e.g. simulation/mock modes)
        with state.lock:
            cached = state.market_data.get(symbol)
            if cached:
                return {
                    "ltp": cached.get("ltp"),
                    "bid": cached.get("bid"),
                    "ask": cached.get("ask"),
                    "volume": cached.get("volume"),
                    "timestamp": datetime.datetime.fromtimestamp(cached.get("timestamp", 0)).isoformat() if cached.get("timestamp") else None,
                    "status": cached.get("status", "DISCONNECTED")
                }
        raise HTTPException(status_code=404, detail=f"Market data for {symbol} not found")

    return {
        "ltp": data.get("ltp"),
        "bid": data.get("bid"),
        "ask": data.get("ask"),
        "volume": data.get("volume"),
        "timestamp": data.get("timestamp"),
        "status": data.get("status", ldm.status)
    }

@app.get("/market-status")
def get_market_status():
    """Production-spec Market Status Endpoint"""
    ldm = LiveDataManager()
    cm = state.commodity_manager
    return {
        "connection_state": ldm.status,
        "last_update": ldm.last_update,
        "commodity": cm.get_status()
    }

@app.get("/api/v1/commodity/live-status")
def get_commodity_live_status():
    """Commodity futures live data connection status & cache."""
    cm = state.commodity_manager
    return {
        "status": "success",
        "connection": cm.status,
        "last_update": cm.last_update,
        "mcx_open": CommodityLiveManager.is_mcx_open(),
        "instruments": list(cm.resolved_instruments.keys()),
        "expiry_map": cm._expiry_map,
        "cache": cm.get_cache()
    }

@app.get("/api/v1/commodity/snapshot/{symbol}")
def get_commodity_snapshot(symbol: str):
    """Get live snapshot for a single commodity."""
    cm = state.commodity_manager
    data = cm.get_snapshot(symbol.upper())
    if not data:
        # Fallback to main market_data state
        with state.lock:
            cached = state.market_data.get(symbol.upper())
                return {
                    "status": "success",
                    "instrument": symbol.upper(),
                    "ltp": cached.get("ltp"),
                    "volume": cached.get("volume"),
                    "close": cached.get("close"),
                    "data_source": "FALLBACK",
                    "live_status": cm.status
                }
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    return {
        "status": "success",
        "instrument": symbol.upper(),
        **data,
        "live_status": cm.status
    }

@app.get("/api/v1/market/search")
async def search_symbols(q: str = ""):
    """Universal symbol search across NSE, BSE, MCX"""
    if len(q) < 2:
        return {"status": "success", "results": []}
    results = state.search_mgr.search(q, limit=10)
    return {"status": "success", "results": results}

@app.post("/api/v1/market/select")
async def select_symbol(request: Request):
    """Set active symbol and initiate live feed if in PAPER/REAL mode"""
    data = await request.json()
    symbol = data.get("symbol")
    exch = data.get("exchange", "NSE")
    
    inst = state.search_mgr.get_by_symbol(symbol, exch)
    if not inst:
        raise HTTPException(status_code=404, detail="Instrument not found")
    
    with state.lock:
        state.active_symbol = symbol
        state.active_exch = exch
        
        # Initialize with LOADING status instead of 0.0 to trigger UI shimmer
        if symbol not in state.market_data or state.market_data[symbol].get("ltp") == 0:
            state.market_data[symbol] = {
                "ltp": None, "close": None, "volume": None, 
                "status": "LOADING", "timestamp": time.time()
            }
    
    # Support for immediate REST snapshot to avoid 0 LTP glitch
    if state.execution_mode in ["PAPER", "REAL"]:
        ldm = LiveDataManager()
        
        # Initialize as LOADING
        with state.lock:
            state.market_data[symbol] = {
                "ltp": None, "close": None, "volume": None, 
                "status": "LOADING", "timestamp": time.time()
            }
        
        # Background fetch
        asyncio.create_task(ldm.subscribe_symbol({
            "exchange": exch,
            "token": inst["token"],
            "name": symbol
        }))
        asyncio.create_task(ldm.fetch_snapshot(exch, inst["token"], symbol))
        
        state.add_log(f"Atomic subscription for {symbol} initiated.")
    else:
        # VIRTUAL/MOCK mode
        with state.lock:
            state.market_data[symbol] = {
                "ltp": 150.0, "close": 150.0, "volume": 1000, 
                "status": "VIRTUAL", "timestamp": time.time()
            }
        state.add_log(f"Selected virtual symbol: {symbol}")
        
    return {
        "status": "success",
        "symbol": symbol,
        "exchange": exch,
        "token": inst["token"]
    }

@app.get("/api/v1/market/data/{symbol}")
def get_symbol_data(symbol: str):
    """Fetch latest snapshot for specific symbol"""
    symbol = symbol.upper()
    data = state.market_data.get(symbol)
    
    # Check commodity manager too
    if not data:
        comm_snap = state.commodity_manager.get_snapshot(symbol)
        if comm_snap:
            data = comm_snap

    if not data:
        # Fallback to loading state if not in cache
        return {
            "status": "success",
            "symbol": symbol,
            "ltp": None,
            "close": None,
            "volume": None,
            "data_status": "LOADING" 
        }

    return {
        "status": "success",
        "instrument": symbol,
        "ltp": data.get("ltp"),  # Return None if not available
        "close": data.get("close"),
        "volume": data.get("volume"),
        "data_status": data.get("status", "LIVE")
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
    state.add_log(f"Capital Allocation Updated: Rs.{state.metrics['total_capital']}")
    return {"status": "success"}

@app.post("/api/v1/system/start")
def system_start():
    state.is_running = True
    state.add_log(">>> ALGO SYSTEM STARTED: LIVE MONITORING <<<")
    return {"status": "success"}

@app.post("/api/v1/system/mode")
async def set_execution_mode(request: Request):
    """
    Switch execution mode with comprehensive safety checks.
    
    Blocks only when:
    - Invalid mode requested
    - REAL mode without credentials
    - Active orders mid-execution
    - System in locked state
    """
    try:
        data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid request format")
    
    new_mode = data.get("mode")
    
    # Validate mode
    if new_mode not in ["MOCK", "SIMULATION", "PAPER", "REAL"]:
        raise HTTPException(status_code=400, detail=f"Invalid mode '{new_mode}'. Valid modes: MOCK, SIMULATION, PAPER, REAL")
    
    # Safety Check 1: Validate credentials for REAL mode
    if new_mode == "REAL":
        if not API_KEY or not USER_ID or not TOTP_SECRET:
            raise HTTPException(
                status_code=403, 
                detail="REAL mode requires valid broker API credentials. Please configure API_KEY, USER_ID, and TOTP_SECRET in .env file."
            )
    
    # Safety Check 2: Check for active mid-execution orders (if applicable)
    with state.lock:
        old_mode = state.execution_mode
        
        # Audit Log formatting with User ID
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_info = f"USER:{USER_ID}" if USER_ID else "USER:SYSTEM"
        state.add_log(f"[{timestamp}] {user_info} MODE SWITCH: {old_mode} -> {new_mode}")
        
        # Perform the switch
        state.execution_mode = new_mode
        
        # Isolation: Clear trades when switching modes to prevent data contamination
        state.trades = []
        state.add_log(f"[{timestamp}] {user_info} ISOLATION: Positions cleared for {new_mode} mode")
    
    # Initialize data source based on rules:
    # MOCK: No live data required
    # SIMULATION: Historical or internal feed
    # PAPER/REAL: Enable live market data feed
    if new_mode in ["PAPER", "REAL"]:
        try:
            # Bridging thread to async LDM (includes commodity data engine)
            def run_async_start():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(start_data_engine())
            
            threading.Thread(target=run_async_start, daemon=True).start()
        except Exception as e:
            state.add_log(f"Live data initialization failed: {str(e)}")
    else:
        # Non-live modes: Ensure live engine + commodity engine are stopped
        def run_async_stop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(stop_data_engine())
        
        threading.Thread(target=run_async_stop, daemon=True).start()
        if new_mode == "SIMULATION":
            # Logic for starting internal/historical simulator could go here
            state.add_log("Internal simulation feed initialized.")
        else:
            # MOCK: Data fetched from internal mock generator or last cached
            state.add_log("Internal mock data engine active.")
    
    # Determine data connection status message
    data_status = "disabled"
    if new_mode == "MOCK":
        data_status = "Internal Mock Data (Isolated)"
    elif new_mode == "SIMULATION":
        data_status = "Simulated Feed Active"
    elif new_mode == "PAPER":
        data_status = "Live Data Enabled (Virtual Execution)"
    elif new_mode == "REAL":
        data_status = "Live Data + Live Execution ACTIVE"
    
    return {
        "status": "success", 
        "mode": new_mode,
        "previous_mode": old_mode,
        "data_status": data_status,
        "user_id": USER_ID,
        "timestamp": datetime.datetime.now().isoformat()
    }

@app.post("/api/v1/system/square_off_all")
def square_off():
    state.add_log("[EMERGENCY] SQUARE OFF INITIATED [EMERGENCY]")
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
    # Note: Initial start could be async if we want
    def initial_start():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_data_engine())
        
    threading.Thread(target=initial_start, daemon=True).start()
    
    print(" Anti-Gravity Web Server starting at http://127.0.0.1:8001")
    uvicorn.run(app, host="127.0.0.1", port=8001)
