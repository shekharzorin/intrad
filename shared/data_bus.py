class DataBus:
    """
    Shared data bus for live market data across agents.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DataBus, cls).__new__(cls)
            cls._instance.data = {}
        return cls._instance

    def __setitem__(self, key, value):
        """
        Allow dictionary-style assignment: data_bus[symbol] = data
        """
        self.data[key] = value

    def __getitem__(self, key):
        """
        Allow dictionary-style access: data_bus[symbol]
        """
        return self.data.get(key, None)

    def update_data(self, symbol, data):
        """
        Update live data for a symbol.
        """
        self.data[symbol] = data

    def get_data(self, symbol):
        """
        Get live data for a symbol.
        """
        return self.data.get(symbol, None)

    def get_all_data(self):
        """
        Get all live data.
        """
        return self.data

    def delete_data(self, symbol):
        """
        Delete live data for a symbol.
        """
        if symbol in self.data:
            del self.data[symbol]
            return True
        return False
