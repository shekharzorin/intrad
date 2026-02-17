
import asyncio
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from .broker_adapter import AliceBlueAdapter, BrokerDataAdapter

class LiveDataManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LiveDataManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._initialized = True
        
        # State Management
        self.status = "DISCONNECTED" # DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING
        self.last_update = None
        self.subscriptions = []
        self.market_cache: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        
        # Internal Event Handlers
        self.callbacks: List[Callable] = []
        
        # Adapter Management
        self.adapter: Optional[BrokerDataAdapter] = None
        
        # Config (will be set from environment)
        self.credentials = {}
        
        print("[LDM] LiveDataManager initialized.")

    def set_credentials(self, user_id, api_key, totp_secret):
        self.credentials = {
            "user_id": user_id,
            "api_key": api_key,
            "totp_secret": totp_secret
        }

    def register_callback(self, func: Callable):
        if func not in self.callbacks:
            self.callbacks.append(func)

    async def start(self, symbols: List[Dict[str, Any]]):
        """Connect and subscribe"""
        async with self.lock:
            if self.status in ["CONNECTED", "CONNECTING"]:
                print("[LDM] Already active or connecting.")
                return

            self.status = "CONNECTING"
            self.subscriptions = symbols
            
            # Initialize Adapter
            self.adapter = AliceBlueAdapter(
                user_id=self.credentials.get("user_id"),
                api_key=self.credentials.get("api_key"),
                totp_secret=self.credentials.get("totp_secret"),
                callback=self._handle_raw_tick
            )

        # Attempt Connection
        connected = await self.adapter.connect()
        
        async with self.lock:
            if connected:
                self.status = "CONNECTED"
                print("[LDM] Connection established.")
                # Perform Subscriptions
                await self.adapter.subscribe(self.subscriptions)
            else:
                self.status = "DISCONNECTED"
                print("[LDM] Connection failed.")
                # Start reconnection task in background
                asyncio.create_task(self._reconnect_loop())

    async def stop(self):
        """Shutdown connection"""
        async with self.lock:
            self.status = "DISCONNECTED"
            if self.adapter:
                await self.adapter.disconnect()
            self.market_cache.clear()
            self.subscriptions = []
            print("[LDM] Shutdown complete.")

    async def subscribe_symbol(self, symbol_config: Dict[str, Any]):
        """Dynamically add a symbol to current subscription list"""
        async with self.lock:
            # Check if already subscribed
            if any(s.get('token') == symbol_config.get('token') for s in self.subscriptions):
                return
            self.subscriptions.append(symbol_config)
            if self.adapter and self.status == "CONNECTED":
                await self.adapter.subscribe([symbol_config])

    async def unsubscribe_symbol(self, token: int):
        """Remove a symbol from current subscription list"""
        async with self.lock:
            self.subscriptions = [s for s in self.subscriptions if s.get('token') != token]
            # Adapter usually doesn't support easy unsubscription in older pya3, 
            # but we update our internal tracking.
            if self.adapter and self.status == "CONNECTED":
                # We could call unsubscribe if implemented, but often it's ignored.
                pass

    async def fetch_snapshot(self, exchange: str, token: int, symbol_name: str) -> Optional[Dict[str, Any]]:
        """Force an immediate REST snapshot fetch and update cache"""
        if not self.adapter:
            return None
        
        snap = await self.adapter.get_snapshot(exchange, token)
        if snap:
            tick_data = {
                **snap,
                "timestamp": datetime.now().isoformat(),
                "status": "LIVE"
            }
            async with self.lock:
                self.market_cache[symbol_name] = tick_data
            
            # Bridge to callbacks if needed
            pseudo_msg = {"tk": token, "ts": symbol_name, "lp": snap["ltp"], "v": snap["volume"], "c": snap["close"]}
            for cb in self.callbacks:
                try: cb(pseudo_msg)
                except: pass
                
            return tick_data
        return None

    def _handle_raw_tick(self, message):
        """Standard tick processing bridged from Adapter"""
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except:
                return

        if not isinstance(message, dict):
            return

        # Extract basic info
        token = message.get("tk")
        # We need a token-to-symbol map if we want named keys in cache
        # For now, let's use token as key if name is missing
        symbol = message.get("ts", str(token))
        
        tick_data = {
            "ltp": float(message.get("lp", 0)),
            "bid": float(message.get("bp1", 0)),
            "ask": float(message.get("sp1", 0)),
            "volume": float(message.get("v", 0)),
            "timestamp": datetime.now().isoformat(),
            "raw": message
        }

        if tick_data["ltp"] <= 0: return

        # Update Cache
        self.market_cache[symbol] = tick_data
        self.last_update = datetime.now().isoformat()

        # Update legacy DataBus for backward compatibility
        try:
            from shared.data_bus import DataBus
            DataBus().update_data(symbol, tick_data)
        except:
            pass

        # Execute Callbacks
        for cb in self.callbacks:
            try:
                cb(message)
            except Exception as e:
                print(f"[LDM] Callback error: {e}")

    async def _reconnect_loop(self):
        """Exponential backoff reconnection"""
        delays = [1, 2, 5, 10, 30]
        idx = 0
        
        while self.status == "DISCONNECTED":
            wait_time = delays[idx]
            print(f"[LDM] Retrying connection in {wait_time}s...")
            await asyncio.sleep(wait_time)
            
            idx = min(idx + 1, len(delays) - 1)
            
            # Check if mode is still applicable (someone else might have stopped us)
            if self.status != "DISCONNECTED": break
            
            async with self.lock:
                self.status = "RECONNECTING"
            
            connected = await self.adapter.connect()
            
            async with self.lock:
                if connected:
                    self.status = "CONNECTED"
                    print("[LDM] Reconnected successfully.")
                    await self.adapter.subscribe(self.subscriptions)
                    break
                else:
                    self.status = "DISCONNECTED"

    def get_status(self):
        return {
            "status": self.status,
            "last_update": self.last_update,
            "cache_size": len(self.market_cache)
        }

    def get_market_snapshot(self, symbol: str = None):
        if symbol:
            return self.market_cache.get(symbol)
        return self.market_cache
