import threading

class DataBus:
    """
    Shared data bus for live market data across agents.
    Thread-safe implementation.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DataBus, cls).__new__(cls)
                cls._instance.data = {}
                cls._instance.lock = threading.Lock()
        return cls._instance

    def __setitem__(self, key, value):
        with self.lock:
            self.data[key] = value

    def __getitem__(self, key):
        with self.lock:
            return self.data.get(key, None)

    def update_data(self, symbol, data):
        with self.lock:
            self.data[symbol] = data

    def get_data(self, symbol):
        with self.lock:
            return self.data.get(symbol, None)

    def get_all_data(self):
        with self.lock:
            return self.data.copy()

    def delete_data(self, symbol):
        with self.lock:
            if symbol in self.data:
                del self.data[symbol]
                return True
            return False
