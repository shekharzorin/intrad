
import asyncio
import datetime
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

# --- PYA3 PATCH START ---
try:
    import pya3.alicebluepy
    from datetime import time as dt_time
    from time import sleep as t_sleep
    if hasattr(pya3.alicebluepy, 'time') and not callable(pya3.alicebluepy.time):
        pya3.alicebluepy.time = dt_time
    if not hasattr(pya3.alicebluepy, 'sleep'):
        pya3.alicebluepy.sleep = t_sleep
    print("[CORE] pya3 library patched successfully (time + sleep)")
except Exception as e:
    print(f"[CORE] pya3 patch skipped: {e}")
# --- PYA3 PATCH END ---

from pya3 import Aliceblue, LiveFeedType

class BrokerDataAdapter(ABC):
    @abstractmethod
    async def connect(self) -> bool:
        pass

    @abstractmethod
    async def disconnect(self):
        pass

    @abstractmethod
    async def subscribe(self, symbols: List[Dict[str, Any]]):
        pass

    @abstractmethod
    async def unsubscribe(self, symbols: List[Dict[str, Any]]):
        pass

class AliceBlueAdapter(BrokerDataAdapter):
    def __init__(self, user_id, api_key, totp_secret, callback):
        self.user_id = user_id
        self.api_key = api_key
        self.totp_secret = totp_secret
        self.callback = callback
        self.alice: Optional[Aliceblue] = None
        self.is_connected = False

    async def connect(self) -> bool:
        import pyotp
        try:
            print(f"[ADAPTER] Authenticating user {self.user_id}...")
            self.alice = Aliceblue(user_id=self.user_id, api_key=self.api_key)
            session_res = self.alice.get_session_id(pyotp.TOTP(self.totp_secret).now())
            
            if not session_res or not isinstance(session_res, dict) or not session_res.get("sessionID"):
                print(f"[ADAPTER] Login failed: {session_res}")
                return False
            
            # Set session ID explicitly if library doesn't
            if getattr(self.alice, 'session_id', None) is None:
                self.alice.session_id = session_res.get('sessionID')
            
            print("[ADAPTER] Authentication successful. Starting WebSocket...")
            
            # Wrap standard pya3 callbacks to bridge to our async Manager if needed
            # Support multiple pya3 versions (some use socket_open_callback, others use on_open)
            try:
                self.alice.start_websocket(
                    socket_open_callback=self._on_open,
                    socket_close_callback=self._on_close,
                    socket_error_callback=self._on_error,
                    subscription_callback=self.callback,
                    run_in_background=True
                )
            except TypeError:
                try:
                    self.alice.start_websocket(
                        on_open=self._on_open,
                        on_close=self._on_close,
                        on_error=self._on_error,
                        on_data=self.callback,
                        run_in_background=True
                    )
                except Exception as e:
                    print(f"[ADAPTER] Failed to start WebSocket: {e}")
                    return False
            
            # Wait for connection
            for _ in range(10):
                if self.is_connected: break
                await asyncio.sleep(0.5)
            
            return self.is_connected
        except Exception as e:
            print(f"[ADAPTER] Connection error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _on_open(self):
        self.is_connected = True
        print("[ADAPTER] WebSocket Connected")

    def _on_close(self):
        self.is_connected = False
        print("[ADAPTER] WebSocket Closed")

    def _on_error(self, error):
        print(f"[ADAPTER] WebSocket Error: {error}")

    async def disconnect(self):
        if self.alice:
            try:
                # Try multiple possible method names
                stopper = getattr(self.alice, "stop_websocket", None) or getattr(self.alice, "close_websocket", None)
                if callable(stopper):
                    stopper()
            except Exception as e:
                print(f"[ADAPTER] Error during disconnect: {e}")
        self.is_connected = False

    async def subscribe(self, symbols: List[Dict[str, Any]]):
        if not self.alice or not self.is_connected:
            return

        for sym in symbols:
            try:
                exchange = sym.get("exchange", "NSE")
                token = sym.get("token")
                name = sym.get("name", str(token))
                
                instrument = self.alice.get_instrument_by_token(exchange, token)
                
                # Intelligent feed type selection
                is_index = "NIFTY" in name.upper() or "SENSEX" in name.upper()
                feed_type = None
                priority = ["TICK_DATA", "MARKET_DATA", "INDEX"] if is_index else ["TICK_DATA", "MARKET_DATA", "DEPTH_DATA"]
                
                for attr in priority:
                    if hasattr(LiveFeedType, attr):
                        feed_type = getattr(LiveFeedType, attr)
                        break
                
                # Standard subscription call
                try:
                    self.alice.subscribe([instrument])
                    print(f"[ADAPTER] Subscribed to {name}")
                except Exception:
                    # Fallback for older SDK versions
                    self.alice.subscribe(instrument)
                    print(f"[ADAPTER] Subscribed to {name} (fallback method)")
                    
            except Exception as e:
                print(f"[ADAPTER] Subscription error for {sym}: {e}")

    async def get_snapshot(self, exchange: str, token: int) -> Optional[Dict[str, Any]]:
        """Fetch a single scrip data snapshot via REST."""
        if not self.alice:
            return None
        
        try:
            instrument = self.alice.get_instrument_by_token(exchange, token)
            res = self.alice.get_scrip_info(instrument)
            
            if res and res.get('stat') == 'Ok':
                # Explicitly check for presence of data to avoid false 0.0
                ltp_str = res.get('LTP')
                if ltp_str is None or ltp_str == "" or ltp_str == "0" or ltp_str == "0.0":
                    # Placeholder or no-data state
                    return None

                return {
                    "ltp": float(ltp_str),
                    "bid": float(res.get('bp1', 0) or 0),
                    "ask": float(res.get('sp1', 0) or 0),
                    "volume": float(res.get('v', 0) or 0),
                    "close": float(res.get('c', 0) or 0)
                }
        except Exception as e:
            print(f"[ADAPTER] Snapshot error: {e}")
        return None

    async def unsubscribe(self, symbols: List[Dict[str, Any]]):
        # pya3 doesn't have a direct unsubscribe for all, but we can try
        pass
