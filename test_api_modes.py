import requests
import json

BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_modes():
    print("--- STARTING BROWSER-EQUIVALENT API TEST ---")
    
    # 1. Initial State
    res = requests.get(f"{BASE_URL}/dashboard/metrics")
    mode = res.json().get('execution_mode')
    print(f"Initial Mode: {mode}")
    
    # 2. Switch to SIMULATION
    requests.post(f"{BASE_URL}/system/mode", json={"mode": "SIMULATION"})
    res = requests.get(f"{BASE_URL}/dashboard/metrics")
    mode = res.json().get('execution_mode')
    print(f"Mode after SIM switch: {mode}")
    
    # 3. Switch to PAPER
    requests.post(f"{BASE_URL}/system/mode", json={"mode": "PAPER"})
    res = requests.get(f"{BASE_URL}/dashboard/metrics")
    mode = res.json().get('execution_mode')
    print(f"Mode after PAPER switch: {mode}")
    
    # 4. Check Market Data
    res = requests.get(f"{BASE_URL}/market/ohlc/NIFTY")
    market = res.json()
    print(f"NIFTY Data Status: {market.get('status')} | Price: {market.get('ltp')}")
    
    # 5. Check Audit Logs
    res = requests.get(f"{BASE_URL}/alerts/logs")
    logs = res.json()
    print(f"Latest Log Entry: {logs[-1]['message'] if logs else 'No logs'}")
    
    # 6. Return to MOCK
    requests.post(f"{BASE_URL}/system/mode", json={"mode": "MOCK"})
    print("Returned to MOCK mode for safety.")

if __name__ == "__main__":
    test_modes()
