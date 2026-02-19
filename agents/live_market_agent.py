"""Live Market Agent
Connects to Alice Blue via WebSocket and streams live market data
Uses cleaner callback pattern for reliability
"""
import time
from datetime import datetime, timezone, timedelta
import inspect
# Attempt to import LiveFeedType from known packages
try:
    from alice_blue import LiveFeedType
except Exception:
    try:
        from pya3 import LiveFeedType
    except Exception:
        LiveFeedType = None

try:
    import pya3.alicebluepy
    from datetime import time as dt_time
    if hasattr(pya3.alicebluepy, 'time') and not callable(pya3.alicebluepy.time):
        pya3.alicebluepy.time = dt_time
except Exception:
    pass

from shared.data_bus import DataBus

# Global state
# Use singleton DataBus for consistent shared storage across agents
data_bus = DataBus()  # singleton for ticks
tick_count = 0
is_connected = False
callbacks = []  # List of functions to call on new tick
token_name_map = {} # Maps token strings to user-friendly names

def register_callback(func):
    """Register a function to be called on every tick"""
    if func not in callbacks:
        callbacks.append(func)


# -------------------------------------------------------------------------------
# CALLBACKS
# -------------------------------------------------------------------------------

def socket_open():
    """Called when WebSocket connects"""
    global is_connected
    is_connected = True
    print("[OK] WebSocket Connected")


def socket_close():
    """Called when WebSocket disconnects"""
    global is_connected
    is_connected = False
    print("[CLOSE] WebSocket Closed")


def socket_error(error):
    """Called on WebSocket error"""
    print(f"[WARN] WebSocket Error: {error}")


def feed_data(message):
    """
    Called for each live market tick
    This is where live data arrives
    """
    global tick_count
    
    if isinstance(message, str):
        try:
            import json
            message = json.loads(message)
        except Exception:
            pass

    if not isinstance(message, dict):
        if message: print(f"[DEBUG] NON-DICT MSG: {message} (type: {type(message)})")
        return
    
    tick_count += 1
    
    # Extract key fields
    try:
        token = str(message.get("tk", ""))
        symbol = message.get("ts")
        
        # Fallback to token if symbol name is missing (common in indices)
        if not symbol:
            symbol = token_name_map.get(token, token)
            if not symbol or symbol == "":
                symbol = "UNKNOWN"
        
        # Debug: print every incoming message for the first 10 messages
        if tick_count <= 10:
            print(f"DEBUG MSG #{tick_count}: {message} -> Resolved Symbol: {symbol}")
        
        # Get existing data for fallback
        existing = data_bus.get_data(symbol) or {}
        
        price = message.get("lp", existing.get("price", 0))
        volume = message.get("v", existing.get("volume", 0))
        
        # Normalize numeric types to avoid formatting errors
        try:
            price = float(price)
        except Exception:
            price = existing.get("price", 0.0)
        try:
            volume = int(volume)
        except Exception:
            volume = existing.get("volume", 0)

        
        # Store in the singleton DataBus (keyed by symbol)
        try:
            data_bus.update_data(symbol, {"price": price, "volume": volume, "raw": message})
        except Exception:
            # Fallback to item assignment if update_data is unavailable
            data_bus[symbol] = {"price": price, "volume": volume, "raw": message}

        if tick_count <= 3:
            print("DEBUG RAW TICK:", message)

        if tick_count % 10 == 0:
            print(f"TICK #{tick_count}: {symbol} @ {price:.2f}")
        
        # Execute registered callbacks
        for callback in callbacks:
            try:
                callback(message)
            except Exception as cb_err:
                print(f"[WARN] Callback error: {cb_err}")
        
    except Exception as e:
        print(f"[WARN] Tick parsing error: {e}")


# -------------------------------------------------------------------------------
# MAIN FUNCTIONS
# -------------------------------------------------------------------------------

def start_market_feed(alice, symbols_to_subscribe=None):
    """
    Start WebSocket and subscribe to live data

    Args:
        alice: Authenticated Alice Blue client
        symbols_to_subscribe: List of dicts with 'exchange' and 'token' keys
                             Example: [{"exchange": "NSE", "token": 26000}]
    """
    global is_connected

    # Check market hours (IST: 09:15 - 15:30)
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    market_open = ist_now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = ist_now.replace(hour=15, minute=30, second=0, microsecond=0)
    is_market_open = market_open <= ist_now <= market_close and ist_now.weekday() < 5

    if not is_market_open:
        print(f"[WARN] Market is CLOSED (IST: {ist_now.strftime('%H:%M:%S')})")
        print("   Live data only available 09:15 - 15:30 IST (Mon-Fri)")
    else:
        print(f"[OK] Market is OPEN (IST: {ist_now.strftime('%H:%M:%S')})")

    print("[START] Starting WebSocket...")
    
    # DEBUG: Print session information and try explicit session creation to catch server responses
    try:
        sess = getattr(alice, 'session_id', None)
        print(f"DEBUG: alice.session_id = {sess}")
        try:
            invalid = alice.invalid_sess(sess)
            print(f"DEBUG: invalid_sess -> {invalid}")
        except Exception as _e:
            print(f"DEBUG: invalid_sess failed: {_e!r}")
        try:
            create_sess = alice.createSession(sess)
            print(f"DEBUG: createSession -> {create_sess}")
        except Exception as _e:
            print(f"DEBUG: createSession failed: {_e!r}")
    except Exception:
        # Non-fatal debug error
        pass

    # Step 1: Start WebSocket with callbacks (try multiple common parameter sets for compatibility)
    try:
        alice.start_websocket(
            socket_open_callback=socket_open,
            socket_close_callback=socket_close,
            socket_error_callback=socket_error,
            subscription_callback=feed_data,
            run_in_background=True
        )
    except TypeError:
        try:
            alice.start_websocket(
                on_open=socket_open,
                on_close=socket_close,
                on_error=socket_error,
                on_data=feed_data,
                run_in_background=True
            )
        except Exception as e:
            print(f"⚠️  Failed to start WebSocket: {e}")
            return
    
    # Step 2: Wait for socket to stabilize
    time.sleep(2)
    
    if not is_connected:
        print("[WARN] WebSocket may not be connected yet")
    
    # Step 3: Subscribe to symbols if provided
    if symbols_to_subscribe:
        for symbol_data in symbols_to_subscribe:
            try:
                exchange = symbol_data.get("exchange", "NSE")
                token = symbol_data.get("token")
                symbol = symbol_data.get("symbol")
                name = symbol_data.get("name", f"{symbol or token}")

                # Prefer token lookup (more reliable); fall back to symbol lookup
                if token:
                    instrument = alice.get_instrument_by_token(exchange, token)
                    print(f"DEBUG: Got instrument by token {token}: {instrument}")
                elif symbol:
                    instrument = alice.get_instrument_by_symbol(exchange, symbol)
                    print(f"DEBUG: Got instrument by symbol {symbol}: {instrument}")
                else:
                    raise ValueError("No token or symbol provided for subscription")

                # Store mapping for tick resolver
                if token:
                    token_name_map[str(token)] = name
                elif instrument and hasattr(instrument, 'token'):
                    token_name_map[str(instrument.token)] = name

                # Subscribe to the instrument with robust signature handling
                is_index = (symbol and symbol.startswith("^")) or ("NIFTY" in name.upper()) or ("SENSEX" in name.upper())
                feed_type = None
                if LiveFeedType:
                    # Try to find a suitable feed type
                    priority = ["TICK_DATA", "MARKET_DATA", "INDEX", "MARKET_INDEX"] if is_index else ["TICK_DATA", "MARKET_DATA", "DEPTH_DATA"]
                    for attr in priority:
                        if hasattr(LiveFeedType, attr):
                            feed_type = getattr(LiveFeedType, attr)
                            break
                    
                    if not feed_type:
                        # Fallback to first available member if possible
                        members = [m for m in dir(LiveFeedType) if not m.startswith('_')]
                        if members:
                            feed_type = getattr(LiveFeedType, members[0])
                            print(f"[WARN] Using fallback feed_type: {members[0]}")

                # Debug: print available LiveFeedType members and subscribe signature
                try:
                    if LiveFeedType:
                        print("DEBUG LiveFeedType members:", [m for m in dir(LiveFeedType) if m.isupper()])
                except Exception:
                    pass
                try:
                    print("DEBUG subscribe signature:", inspect.signature(alice.subscribe))
                except Exception:
                    pass

                subscribed = False
                try:
                    # Preferred modern API: list of instruments
                    alice.subscribe([instrument])
                    subscribed = True
                    print("INFO: subscribe([instrument]) succeeded")
                except TypeError as e1:
                    try:
                        # Older API: single instrument
                        alice.subscribe(instrument)
                        subscribed = True
                        print("INFO: subscribe(instrument) succeeded")
                    except TypeError as e2:
                        # If we have a feed_type try as keyword argument (some SDKs support this)
                        if feed_type is not None:
                            try:
                                alice.subscribe([instrument], feed_type=feed_type)
                                subscribed = True
                                print("INFO: subscribe([instrument], feed_type=...) succeeded")
                            except Exception as e3:
                                print(f"[WARN] Subscription call failed: {e1!r}, {e2!r}, {e3!r}")
                        else:
                            print(f"[WARN] Subscription call failed: {e1!r}, {e2!r}")

                if subscribed:
                    # Try printing subscribed instruments if supported by the client
                    try:
                        getter = getattr(alice, "get_subscribed_instruments", None) or getattr(alice, "get_subscribed", None)
                        if callable(getter):
                            try:
                                print("INFO: Subscribed instruments:", getter())
                            except Exception:
                                print("INFO: Subscribed instruments (could not retrieve list)")
                    except Exception as _e:
                        print(f"[WARN] Could not get subscribed instruments: {_e!r}")

                if subscribed:
                    # Try printing subscribed instruments if supported by the client
                    try:
                        getter = getattr(alice, "get_subscribed_instruments", None) or getattr(alice, "get_subscribed", None)
                        if callable(getter):
                            try:
                                print("INFO: Subscribed instruments:", getter())
                            except Exception:
                                print("INFO: Subscribed instruments (could not retrieve list)")
                    except Exception as _e:
                        print(f"[WARN] Could not get subscribed instruments: {_e!r}")

                print(f"STATUS: Subscribed to {name} ({exchange}, {token or symbol})")
            except Exception as e:
                # Print detailed subscription error for debugging
                import traceback
                print(f"[WARN] Subscription warning for {name}: {e!r}")
                traceback.print_exc()
    else:
        print("STATUS: WebSocket active - ready for subscriptions")


def get_market_data(symbol=None):
    """Get latest market data from data_bus"""
    if symbol:
        return data_bus.get_data(symbol)
    return data_bus.get_all_data()


def get_tick_count():
    """Get number of ticks received"""
    return tick_count


def is_websocket_connected():
    """Check if WebSocket is connected"""
    return is_connected


def analyze_market():
    all_data = data_bus.get_all_data()
    if not all_data:
        print("WAIT: Waiting for live tick...")
        print(f"DEBUG: DataBus contents: {data_bus.get_all_data()}")
        return None

    # Pop the first available symbol's data for analysis
    symbol, data = next(iter(all_data.items()))
    data_bus.delete_data(symbol)
    print("📈 Analyzing:", {symbol: data})
    return {symbol: data}


def stop_market_feed(alice_client=None):
    """
    Stop the market feed and reset state.
    
    Args:
        alice_client: Optional Alice Blue client instance to try stopping websocket on
    """
    global is_connected
    
    print("🛑 Stopping Market Feed...")
    
    if alice_client:
        try:
            # Try to stop websocket on the client if available
            stopper = getattr(alice_client, "stop_websocket", None) or getattr(alice_client, "close_websocket", None)
            if callable(stopper):
                stopper()
                print("✅ WebSocket stopped via client method")
        except Exception as e:
            print(f"⚠️  Error stopping websocket: {e}")

    # Force disconnect flag
    is_connected = False
    callbacks.clear()  # Remove registered callbacks to prevents duplicates on restart
    print("[STOP] Market Feed disconnected")
