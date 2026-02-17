"""
COMMODITY FUTURES LIVE DATA MANAGER
====================================
Non-intrusive, read-only data layer for MCX commodity futures.

Design Principles:
  - Informational ONLY: supplies LTP, bid, ask, volume, OI, expiry
  - NEVER triggers strategy, places orders, or modifies execution state
  - Activates ONLY in PAPER / REAL modes
  - Auto-reconnects with exponential backoff (1s → 2s → 5s → 10s → max 30s)
  - WebSocket primary, REST polling fallback
  - Resolves nearest expiry contracts from MCX.csv

Safety:
  - No modification to order placement logic
  - No changes to existing trading flow
  - No removal of mock/simulation functionality
  - Live data is strictly read-only
"""

import os
import asyncio
import time
import json
import hashlib
import threading
import traceback
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

# --- PYA3 PATCH (same as broker_adapter.py) ---
try:
    import pya3.alicebluepy
    from datetime import time as dt_time
    from time import sleep as t_sleep
    if hasattr(pya3.alicebluepy, 'time') and not callable(pya3.alicebluepy.time):
        pya3.alicebluepy.time = dt_time
    if not hasattr(pya3.alicebluepy, 'sleep'):
        pya3.alicebluepy.sleep = t_sleep
except Exception:
    pass

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import pyotp
except ImportError:
    pyotp = None

try:
    from pya3 import Aliceblue
except ImportError:
    Aliceblue = None


# ============================================================
# CONSTANTS
# ============================================================

COMMODITY_SYMBOLS = ["GOLD", "SILVER", "CRUDEOIL", "NATGASMINI"]

# MCX market hours (IST)
MCX_OPEN_HOUR, MCX_OPEN_MIN = 9, 0
MCX_CLOSE_HOUR, MCX_CLOSE_MIN = 23, 30
MCX_TRADING_DAYS = {0, 1, 2, 3, 4}  # Mon-Fri

# Reconnection backoff schedule (seconds)
BACKOFF_SCHEDULE = [1, 2, 5, 10, 30]

LOG_PREFIX = "[COMMODITY-LDM]"


# ============================================================
# COMMODITY LIVE DATA MANAGER (Singleton)
# ============================================================

class CommodityLiveManager:
    """
    Singleton manager for live commodity futures market data.

    Strictly read-only:
      - Updates commodity_market_cache on every tick
      - Never overwrites execution state
      - Never places orders
      - Never triggers strategy automatically
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CommodityLiveManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # --- Connection State ---
        self.status = "DISCONNECTED"  # DISCONNECTED | CONNECTING | CONNECTED | RECONNECTING
        self.last_update: Optional[str] = None

        # --- Contract Resolution ---
        self.resolved_instruments: Dict[str, Any] = {}   # {symbol_name: instrument_obj}
        self.token_to_symbol: Dict[str, str] = {}         # {token_str: symbol_name}

        # --- In-Memory Cache (read-only output) ---
        self.commodity_market_cache: Dict[str, Dict[str, Any]] = {}
        # Structure per entry:
        # {
        #   "ltp": float,
        #   "bid": float,
        #   "ask": float,
        #   "volume": int,
        #   "open_interest": int,
        #   "expiry": str,
        #   "timestamp": datetime_iso_str
        # }

        # --- Thread Safety ---
        self._lock = threading.RLock()

        # --- Internal pointers ---
        self._alice = None
        self._ws_thread: Optional[threading.Thread] = None
        self._rest_threads: List[threading.Thread] = []
        self._reconnect_task = None
        self._running = False
        self._callbacks: List[Callable] = []

        # --- Credentials ---
        self._user_id = None
        self._api_key = None
        self._totp_secret = None

        # --- Expiry info cache ---
        self._expiry_map: Dict[str, str] = {}  # {symbol: expiry_date_str}

        print(f"{LOG_PREFIX} CommodityLiveManager initialized.")

    # ----------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------

    def set_credentials(self, user_id: str, api_key: str, totp_secret: str):
        """Set broker credentials. Does NOT connect."""
        self._user_id = user_id
        self._api_key = api_key
        self._totp_secret = totp_secret

    def register_callback(self, func: Callable):
        """Register a callback for raw tick data. Read-only consumption."""
        if func not in self._callbacks:
            self._callbacks.append(func)

    async def start(self):
        """
        Start live commodity data streaming.
        Only call this when execution_mode is PAPER or REAL.
        """
        with self._lock:
            if self.status in ["CONNECTED", "CONNECTING"]:
                print(f"{LOG_PREFIX} Already active ({self.status}). Skipping.")
                return
            self.status = "CONNECTING"

        print(f"{LOG_PREFIX} Starting commodity live feed...")

        try:
            # 1. Authenticate
            if not self._authenticate():
                raise Exception("Authentication failed")

            # 2. Resolve contracts
            self._resolve_contracts()

            if not self.resolved_instruments:
                raise Exception("No commodity contracts resolved")

            # 3. Start WebSocket (primary)
            self._start_websocket()

            # 4. Start REST pollers (fallback)
            self._start_rest_pollers()

            with self._lock:
                self.status = "CONNECTED"

            print(f"{LOG_PREFIX} ✅ Commodity live feed CONNECTED. "
                  f"Tracking: {list(self.resolved_instruments.keys())}")

        except Exception as e:
            print(f"{LOG_PREFIX} ❌ Start failed: {e}")
            traceback.print_exc()
            with self._lock:
                self.status = "DISCONNECTED"
            # Trigger reconnect loop in background
            self._schedule_reconnect()

    async def stop(self):
        """
        Stop commodity live data.
        - Unsubscribe all contracts
        - Close WebSocket
        - Clear volatile cache
        - Set state to DISCONNECTED
        """
        print(f"{LOG_PREFIX} Stopping commodity live feed...")
        self._running = False

        with self._lock:
            self.status = "DISCONNECTED"

            # Clear volatile cache
            self.commodity_market_cache.clear()

            # Clear internal state
            self.resolved_instruments.clear()
            self.token_to_symbol.clear()
            self._expiry_map.clear()

        # Stop WebSocket
        try:
            if self._alice:
                stopper = getattr(self._alice, "stop_websocket", None) or \
                          getattr(self._alice, "close_websocket", None)
                if callable(stopper):
                    stopper()
        except Exception as e:
            print(f"{LOG_PREFIX} WS stop error: {e}")

        self._alice = None
        self._ws_thread = None
        self._rest_threads = []

        print(f"{LOG_PREFIX} Commodity feed stopped. Cache cleared.")

    def get_cache(self) -> Dict[str, Dict[str, Any]]:
        """Return full commodity market cache (read-only snapshot)."""
        with self._lock:
            return dict(self.commodity_market_cache)

    def get_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get single commodity data snapshot."""
        with self._lock:
            return self.commodity_market_cache.get(symbol)

    def get_status(self) -> Dict[str, Any]:
        """Get connection status summary."""
        with self._lock:
            return {
                "status": self.status,
                "last_update": self.last_update,
                "instruments": list(self.resolved_instruments.keys()),
                "cache_size": len(self.commodity_market_cache),
                "expiry_map": dict(self._expiry_map)
            }

    def is_active(self) -> bool:
        return self.status in ["CONNECTED", "RECONNECTING", "CONNECTING"]

    # ----------------------------------------------------------
    # AUTHENTICATION
    # ----------------------------------------------------------

    def _authenticate(self) -> bool:
        """Authenticate with Alice Blue broker."""
        if not all([self._user_id, self._api_key, self._totp_secret]):
            print(f"{LOG_PREFIX} Missing credentials.")
            return False

        if Aliceblue is None:
            print(f"{LOG_PREFIX} pya3 library not available.")
            return False

        try:
            print(f"{LOG_PREFIX} Authenticating user {self._user_id}...")
            self._alice = Aliceblue(user_id=self._user_id, api_key=self._api_key)

            totp = pyotp.TOTP(self._totp_secret).now() if pyotp else None
            if not totp:
                print(f"{LOG_PREFIX} pyotp not available.")
                return False

            session_res = self._alice.get_session_id(totp)

            if not session_res or not isinstance(session_res, dict) or not session_res.get("sessionID"):
                print(f"{LOG_PREFIX} Login failed: {session_res}")
                return False

            if getattr(self._alice, 'session_id', None) is None:
                self._alice.session_id = session_res.get('sessionID')

            print(f"{LOG_PREFIX} ✅ Authentication successful.")
            return True

        except Exception as e:
            print(f"{LOG_PREFIX} Auth error: {e}")
            traceback.print_exc()
            return False

    # ----------------------------------------------------------
    # CONTRACT RESOLUTION
    # ----------------------------------------------------------

    def _resolve_contracts(self):
        """
        Resolve commodity symbols to their nearest expiry futures contracts.
        Uses MCX.csv for expiry-based lookup, falls back to generic symbol.
        """
        print(f"{LOG_PREFIX} 🔍 Resolving MCX commodity contracts...")

        mcx_df = self._load_mcx_csv()

        for base_sym in COMMODITY_SYMBOLS:
            resolved = False

            # Strategy 1: CSV-based expiry resolution (preferred)
            if mcx_df is not None:
                resolved = self._resolve_from_csv(base_sym, mcx_df)

            # Strategy 2: Generic symbol via API
            if not resolved:
                resolved = self._resolve_generic(base_sym)

            # Strategy 3: Hardcoded token fallback
            if not resolved:
                resolved = self._resolve_hardcoded(base_sym)

            if not resolved:
                print(f"{LOG_PREFIX} ❌ Could not resolve {base_sym}")

        print(f"{LOG_PREFIX} Resolved: {list(self.resolved_instruments.keys())}")

    def _load_mcx_csv(self):
        """Load MCX.csv for contract resolution."""
        if pd is None:
            return None

        csv_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'MCX.csv'),
            os.path.join(os.path.dirname(__file__), '..', '..', 'MCX.csv'),
        ]

        for csv_path in csv_paths:
            try:
                abs_path = os.path.abspath(csv_path)
                if os.path.exists(abs_path):
                    df = pd.read_csv(abs_path)
                    print(f"{LOG_PREFIX} Loaded MCX.csv from {abs_path}")
                    return df
            except Exception as e:
                print(f"{LOG_PREFIX} CSV load error ({csv_path}): {e}")

        return None

    def _resolve_from_csv(self, base_sym: str, mcx_df) -> bool:
        """Resolve from MCX.csv — nearest expiry FUTCOM contract."""
        try:
            # Filter for futures on this base symbol
            subset = mcx_df[
                (mcx_df['Symbol'] == base_sym) &
                (mcx_df['Exchange Segment'] == 'mcx_fo')
            ]

            # Filter for futures only (exclude options)
            if 'Instrument Type' in subset.columns:
                subset = subset[subset['Instrument Type'].str.contains('FUT', na=False)]

            if subset.empty:
                return False

            # Sort by expiry date to get nearest
            if 'Expiry Date' in subset.columns:
                subset = subset.copy()
                subset['Expiry Date'] = pd.to_datetime(subset['Expiry Date'], errors='coerce')
                # Filter out expired contracts
                now = pd.Timestamp.now()
                subset = subset[subset['Expiry Date'] >= now]
                if subset.empty:
                    return False
                subset = subset.sort_values('Expiry Date')

            nearest = subset.iloc[0]
            token = int(nearest['Token'])
            trading_symbol = nearest.get('Trading Symbol', base_sym)
            expiry_str = str(nearest.get('Expiry Date', ''))

            # Verify via API
            inst = self._alice.get_instrument_by_token("MCX", token)
            if inst:
                with self._lock:
                    self.resolved_instruments[base_sym] = inst
                    self.token_to_symbol[str(token)] = base_sym
                    self._expiry_map[base_sym] = expiry_str

                    # Initialize cache entry
                    self.commodity_market_cache[base_sym] = {
                        "ltp": None,
                        "bid": None,
                        "ask": None,
                        "volume": None,
                        "open_interest": None,
                        "expiry": expiry_str,
                        "timestamp": datetime.now().isoformat(),
                        "source": "INIT",
                        "status": "WAITING"
                    }

                print(f"{LOG_PREFIX} ✅ {base_sym} resolved via CSV "
                      f"(token={token}, ts={trading_symbol}, expiry={expiry_str})")
                return True

        except Exception as e:
            print(f"{LOG_PREFIX} CSV resolution error for {base_sym}: {e}")

        return False

    def _resolve_generic(self, base_sym: str) -> bool:
        """Resolve via generic API symbol lookup."""
        try:
            inst = self._alice.get_instrument_by_symbol("MCX", base_sym)
            if inst:
                with self._lock:
                    self.resolved_instruments[base_sym] = inst
                    self.token_to_symbol[str(inst.token)] = base_sym
                    self._expiry_map[base_sym] = ""

                    self.commodity_market_cache[base_sym] = {
                        "ltp": None, "bid": None, "ask": None,
                        "volume": None, "open_interest": None,
                        "expiry": "", "timestamp": datetime.now().isoformat(),
                        "source": "INIT", "status": "WAITING"
                    }

                print(f"{LOG_PREFIX} ✅ {base_sym} resolved via generic API (token={inst.token})")
                return True
        except Exception:
            pass
        return False

    def _resolve_hardcoded(self, base_sym: str) -> bool:
        """Last-resort fallback using hardcoded tokens."""
        HARDCODED_TOKENS = {
            "GOLD": 454819,
            "SILVER": 451667,
            "CRUDEOIL": 488292,
            "NATGASMINI": 488509
        }

        token = HARDCODED_TOKENS.get(base_sym)
        if not token:
            return False

        try:
            inst = self._alice.get_instrument_by_token("MCX", token)
            if inst:
                with self._lock:
                    self.resolved_instruments[base_sym] = inst
                    self.token_to_symbol[str(token)] = base_sym
                    self._expiry_map[base_sym] = ""

                    self.commodity_market_cache[base_sym] = {
                        "ltp": None, "bid": None, "ask": None,
                        "volume": None, "open_interest": None,
                        "expiry": "", "timestamp": datetime.now().isoformat(),
                        "source": "INIT", "status": "WAITING"
                    }

                print(f"{LOG_PREFIX} ⚠️ {base_sym} resolved via hardcoded token ({token})")
                return True
        except Exception:
            pass
        return False

    # ----------------------------------------------------------
    # WEBSOCKET ENGINE (Primary)
    # ----------------------------------------------------------

    def _start_websocket(self):
        """Start WebSocket in a background thread."""
        self._running = True

        def _ws_worker():
            try:
                # Subscribe to resolved instruments
                instruments = list(self.resolved_instruments.values())
                if not instruments:
                    return

                self._alice.start_websocket(
                    socket_open_callback=self._on_ws_open,
                    socket_close_callback=self._on_ws_close,
                    socket_error_callback=self._on_ws_error,
                    subscription_callback=self._on_ws_tick,
                    run_in_background=True
                )

                # Wait for connection then subscribe
                for _ in range(15):
                    if not self._running:
                        return
                    time.sleep(0.5)

                # Subscribe to all resolved instruments
                for sym, inst in self.resolved_instruments.items():
                    try:
                        try:
                            self._alice.subscribe([inst])
                        except Exception:
                            self._alice.subscribe(inst)
                        print(f"{LOG_PREFIX} 📡 WS subscribed: {sym}")
                    except Exception as e:
                        print(f"{LOG_PREFIX} WS subscribe error ({sym}): {e}")

            except Exception as e:
                print(f"{LOG_PREFIX} WS worker error: {e}")
                traceback.print_exc()
                self._handle_disconnect()

        self._ws_thread = threading.Thread(target=_ws_worker, daemon=True)
        self._ws_thread.start()

    def _on_ws_open(self):
        print(f"{LOG_PREFIX} 📡 WebSocket CONNECTED")

    def _on_ws_close(self):
        print(f"{LOG_PREFIX} WebSocket CLOSED")
        if self._running:
            self._handle_disconnect()

    def _on_ws_error(self, error):
        print(f"{LOG_PREFIX} WebSocket ERROR: {error}")

    def _on_ws_tick(self, message):
        """
        Process incoming WebSocket tick.
        READ-ONLY: Updates cache only. No strategy, no orders.
        """
        if message is None:
            return

        try:
            if isinstance(message, str):
                message = json.loads(message)
            if not isinstance(message, dict):
                return

            token = str(message.get('tk', ''))
            symbol = self.token_to_symbol.get(token)

            if not symbol:
                return

            ltp = float(message.get('lp', 0))
            if ltp <= 0:
                return

            # Extract data fields
            bid = float(message.get('bp1', 0))
            ask = float(message.get('sp1', 0))
            volume = int(float(message.get('v', 0)))
            oi = int(float(message.get('oi', 0)))
            close = float(message.get('c', 0))

            now_iso = datetime.now().isoformat()

            with self._lock:
                self.commodity_market_cache[symbol] = {
                    "ltp": ltp,
                    "bid": bid,
                    "ask": ask,
                    "volume": volume,
                    "open_interest": oi,
                    "close": close,
                    "expiry": self._expiry_map.get(symbol, ""),
                    "timestamp": now_iso,
                    "source": "WS",
                    "status": "LIVE"
                }
                self.last_update = now_iso

            # Fire registered callbacks (read-only consumers)
            for cb in self._callbacks:
                try:
                    cb(symbol, self.commodity_market_cache[symbol])
                except Exception as e:
                    print(f"{LOG_PREFIX} Callback error: {e}")

        except Exception as e:
            # Silently handle bad ticks — never crash
            pass

    # ----------------------------------------------------------
    # REST POLLING ENGINE (Fallback)
    # ----------------------------------------------------------

    def _start_rest_pollers(self):
        """Start REST polling threads for each commodity (fallback when WS is silent)."""
        self._running = True

        for sym, inst in self.resolved_instruments.items():
            t = threading.Thread(
                target=self._rest_poll_worker,
                args=(sym, inst),
                daemon=True
            )
            t.start()
            self._rest_threads.append(t)
            print(f"{LOG_PREFIX} 🔄 REST poller started: {sym}")

    def _rest_poll_worker(self, symbol: str, instrument):
        """
        Independent REST polling worker for a single commodity.
        Only polls when WebSocket has been silent for >3 seconds.
        """
        while self._running:
            try:
                # Check if WS is providing data
                with self._lock:
                    cached = self.commodity_market_cache.get(symbol, {})
                    last_ts = cached.get("timestamp", "")

                ws_fresh = False
                if last_ts and cached.get("source") == "WS":
                    try:
                        last_dt = datetime.fromisoformat(last_ts)
                        ws_fresh = (datetime.now() - last_dt).total_seconds() < 3.0
                    except Exception:
                        pass

                # Only poll if WS is stale
                if not ws_fresh and self._alice:
                    try:
                        res = self._alice.get_scrip_info(instrument)
                        if res and res.get('stat') == 'Ok':
                            ltp = float(res.get('LTP', 0) or 0)
                            if ltp > 0:
                                now_iso = datetime.now().isoformat()
                                with self._lock:
                                    self.commodity_market_cache[symbol] = {
                                        "ltp": ltp,
                                        "bid": float(res.get('bp1', 0) or 0),
                                        "ask": float(res.get('sp1', 0) or 0),
                                        "volume": int(float(res.get('v', 0) or 0)),
                                        "open_interest": int(float(res.get('oi', 0) or 0)),
                                        "close": float(res.get('c', 0) or 0),
                                        "expiry": self._expiry_map.get(symbol, ""),
                                        "timestamp": now_iso,
                                        "source": "REST",
                                        "status": "LIVE"
                                    }
                                    self.last_update = now_iso
                    except Exception:
                        pass  # Never crash on REST failure

            except Exception:
                pass

            # Poll interval: 1.5 seconds
            time.sleep(1.5)

    # ----------------------------------------------------------
    # RECONNECTION LOGIC
    # ----------------------------------------------------------

    def _handle_disconnect(self):
        """Handle unexpected disconnection — trigger reconnect."""
        with self._lock:
            if self.status == "DISCONNECTED":
                return  # Already stopped intentionally
            self.status = "RECONNECTING"

        print(f"{LOG_PREFIX} ⚠️ Connection lost. Initiating reconnect...")
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        """Schedule async reconnection with exponential backoff."""
        def _reconnect_bg():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._reconnect_loop())

        t = threading.Thread(target=_reconnect_bg, daemon=True)
        t.start()

    async def _reconnect_loop(self):
        """
        Exponential backoff reconnection:
        1s → 2s → 5s → 10s → max 30s
        Restores previous subscriptions on success.
        """
        idx = 0

        while self._running or self.status == "RECONNECTING":
            wait_time = BACKOFF_SCHEDULE[min(idx, len(BACKOFF_SCHEDULE) - 1)]
            print(f"{LOG_PREFIX} 🔄 Reconnect attempt in {wait_time}s...")
            await asyncio.sleep(wait_time)

            # Check if we've been intentionally stopped
            with self._lock:
                if self.status == "DISCONNECTED":
                    print(f"{LOG_PREFIX} Reconnect cancelled (stopped).")
                    return
                self.status = "RECONNECTING"

            # Attempt reconnection
            try:
                if self._authenticate():
                    self._resolve_contracts()
                    if self.resolved_instruments:
                        self._start_websocket()
                        self._start_rest_pollers()

                        with self._lock:
                            self.status = "CONNECTED"

                        print(f"{LOG_PREFIX} ✅ Reconnected successfully!")
                        return
            except Exception as e:
                print(f"{LOG_PREFIX} Reconnect attempt failed: {e}")

            idx += 1

            # Safety cap
            if idx > 50:
                print(f"{LOG_PREFIX} Max reconnect attempts reached. Giving up.")
                with self._lock:
                    self.status = "DISCONNECTED"
                return

    # ----------------------------------------------------------
    # UTILITY
    # ----------------------------------------------------------

    @staticmethod
    def is_mcx_open() -> bool:
        """Check if MCX market is currently open (IST)."""
        now = datetime.now()
        if now.weekday() not in MCX_TRADING_DAYS:
            return False
        market_open = now.replace(hour=MCX_OPEN_HOUR, minute=MCX_OPEN_MIN, second=0, microsecond=0)
        market_close = now.replace(hour=MCX_CLOSE_HOUR, minute=MCX_CLOSE_MIN, second=0, microsecond=0)
        return market_open <= now <= market_close
