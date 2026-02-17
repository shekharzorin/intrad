import os
import pandas as pd
from typing import List, Dict, Any, Optional
import threading

class SymbolSearchManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SymbolSearchManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.instruments: List[Dict[str, Any]] = []
        self._load_instruments()

    def _load_instruments(self):
        csv_files = {
            "NSE": "NSE.csv",
            "BSE": "BSE.csv",
            "MCX": "MCX.csv"
        }
        
        base_path = os.path.join(os.path.dirname(__file__), '..')
        
        for exch, filename in csv_files.items():
            path = os.path.join(base_path, filename)
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    # Standardize columns based on what we found earlier
                    # NSE: Exch, Exchange Segment, Symbol, Token, Instrument Name
                    # BSE: Exch, Exchange Segment, Symbol, Token
                    # MCX: Exch, Exchange Segment, Symbol, Token
                    
                    for _, row in df.iterrows():
                        self.instruments.append({
                            "symbol": str(row.get("Symbol", "")),
                            "exch": exch,
                            "segment": str(row.get("Exchange Segment", exch)),
                            "token": int(row.get("Token", 0)),
                            "name": str(row.get("Instrument Name", row.get("Symbol", ""))),
                            "type": str(row.get("Instrument Type", ""))
                        })
                except Exception as e:
                    print(f"[SEARCH-MGR] Error loading {filename}: {e}")
        
        print(f"[SEARCH-MGR] Loaded {len(self.instruments)} instruments.")

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not query:
            return []
        
        query = query.upper()
        results = []
        
        # Priority 1: Exact symbol match
        # Priority 2: Symbol starts with
        # Priority 3: Name contains
        
        for inst in self.instruments:
            symbol = inst["symbol"].upper()
            name = inst["name"].upper()
            
            if symbol == query:
                results.append((0, inst))
            elif symbol.startswith(query):
                results.append((1, inst))
            elif query in name:
                results.append((2, inst))
            
            if len(results) > 100: # optimization
                break

        # Sort by priority then alphabetical symbol
        results.sort(key=lambda x: (x[0], x[1]["symbol"]))
        
        return [r[1] for r in results[:limit]]

    def get_by_symbol(self, symbol: str, exch: Optional[str] = None) -> Optional[Dict[str, Any]]:
        for inst in self.instruments:
            if inst["symbol"].upper() == symbol.upper():
                if exch and inst["exch"].upper() != exch.upper():
                    continue
                return inst
        return None
