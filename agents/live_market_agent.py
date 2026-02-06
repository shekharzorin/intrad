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

from shared.data_bus import DataBus

# Global state
# Use singleton DataBus for consistent shared storage across agents
data_bus = DataBus()  # singleton for ticks
tick_count = 0
is_connected = False


# ═══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

def socket_open():
    """Called when WebSocket connects"""
    global is_connected
    is_connected = True
    print("✅ WebSocket Connected")


def socket_close():
    """Called when WebSocket disconnects"""
    global is_connected
    is_connected = False
    print("❌ WebSocket Closed")


def socket_error(error):
    """Called on WebSocket error"""
    print(f"⚠️  WebSocket Error: {error}")


def feed_data(message):
    """
    Called for each live market tick
    This is where live data arrives
    """
    global tick_count
    
    if not isinstance(message, dict):
        return
    
    tick_count += 1
    
    # Extract key fields
    try:
        symbol = message.get("ts", "UNKNOWN")
        price = message.get("lp", 0)
        volume = message.get("v", 0)
        
        # Normalize numeric types to avoid formatting errors
        try:
            price = float(price)
        except Exception:
            price = 0.0
        try:
            volume = int(volume)
        except Exception:
            volume = 0
        
        # Store in the singleton DataBus (keyed by symbol)
        try:
            data_bus.update_data(symbol, {"price": price, "volume": volume, "raw": message})
        except Exception:
            # Fallback to item assignment if update_data is unavailable
            data_bus[symbol] = {"price": price, "volume": volume, "raw": message}
        
        # Debug: print the raw first few ticks to inspect structure
        if tick_count <= 3:
            print("🔍 RAW TICK:", message)

        if tick_count % 10 == 0:  # Log every 10th tick to reduce output
            print(f"📥 TICK #{tick_count}: {symbol} @ {price:.2f} (stored in DataBus)")
        
    except Exception as e:
        print(f"⚠️  Tick parsing error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

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
        print(f"⚠️  WARNING: Market is CLOSED (IST: {ist_now.strftime('%H:%M:%S')})")
        print("   Live data only available 09:15 - 15:30 IST (Mon-Fri)")
    else:
        print(f"✅ Market is OPEN (IST: {ist_now.strftime('%H:%M:%S')})")

    print("🚀 Starting WebSocket...")
    
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
        print("⚠️  WebSocket may not be connected yet")
    
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
                    print(f"🔍 DEBUG: Got instrument by token {token}: {instrument}")
                elif symbol:
                    instrument = alice.get_instrument_by_symbol(exchange, symbol)
                    print(f"🔍 DEBUG: Got instrument by symbol {symbol}: {instrument}")
                else:
                    raise ValueError("No token or symbol provided for subscription")

                # Subscribe to the instrument with robust signature handling
                is_index = (symbol and symbol.startswith("^")) or ("NIFTY" in name.upper()) or ("SENSEX" in name.upper())
                feed_type = None
                if LiveFeedType:
                    if is_index:
                        for idx_attr in ("INDEX", "MARKET_INDEX", "INDEX_DATA"):
                            if hasattr(LiveFeedType, idx_attr):
                                feed_type = getattr(LiveFeedType, idx_attr)
                                break
                        else:
                            feed_type = getattr(LiveFeedType, "MARKET_DATA", None)
                            print("⚠️  LiveFeedType lacks INDEX attribute; falling back to MARKET_DATA")
                    else:
                        feed_type = getattr(LiveFeedType, "MARKET_DATA", None)

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
                    print("🔁 subscribe([instrument]) succeeded")
                except TypeError as e1:
                    try:
                        # Older API: single instrument
                        alice.subscribe(instrument)
                        subscribed = True
                        print("🔁 subscribe(instrument) succeeded")
                    except TypeError as e2:
                        # If we have a feed_type try as keyword argument (some SDKs support this)
                        if feed_type is not None:
                            try:
                                alice.subscribe([instrument], feed_type=feed_type)
                                subscribed = True
                                print("🔁 subscribe([instrument], feed_type=...) succeeded")
                            except Exception as e3:
                                print(f"⚠️  Subscription call failed: {e1!r}, {e2!r}, {e3!r}")
                        else:
                            print(f"⚠️  Subscription call failed: {e1!r}, {e2!r}")

                if subscribed:
                    # Try printing subscribed instruments if supported by the client
                    try:
                        getter = getattr(alice, "get_subscribed_instruments", None) or getattr(alice, "get_subscribed", None)
                        if callable(getter):
                            try:
                                print("ℹ️  Subscribed instruments:", getter())
                            except Exception:
                                print("ℹ️  Subscribed instruments (could not retrieve list)")
                    except Exception as _e:
                        print(f"⚠️  Could not get subscribed instruments: {_e!r}")

                if subscribed:
                    # Try printing subscribed instruments if supported by the client
                    try:
                        getter = getattr(alice, "get_subscribed_instruments", None) or getattr(alice, "get_subscribed", None)
                        if callable(getter):
                            try:
                                print("ℹ️  Subscribed instruments:", getter())
                            except Exception:
                                print("ℹ️  Subscribed instruments (could not retrieve list)")
                    except Exception as _e:
                        print(f"⚠️  Could not get subscribed instruments: {_e!r}")

                print(f"📊 Subscribed to {name} ({exchange}, {token or symbol})")
            except Exception as e:
                # Print detailed subscription error for debugging
                import traceback
                print(f"⚠️  Subscription warning for {name}: {e!r}")
                traceback.print_exc()
    else:
        print("📊 WebSocket active - ready for subscriptions")


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
        print("⏳ Waiting for live tick...")
        print(f"🔍 DEBUG: DataBus contents: {data_bus.get_all_data()}")
        return None

    # Pop the first available symbol's data for analysis
    symbol, data = next(iter(all_data.items()))
    data_bus.delete_data(symbol)
    print("📈 Analyzing:", {symbol: data})
    return {symbol: data}
