
import json
import os
import pandas as pd
from datetime import datetime

# Mimic paths from anomaly_detector.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_LOGS_PATH = os.path.join(BASE_DIR, "..", "server", "server_logs.jsonl")

def test_load():
    print(f"Checking: {os.path.abspath(SERVER_LOGS_PATH)}")
    if not os.path.exists(SERVER_LOGS_PATH):
        print("File NOT FOUND")
        return
        
    with open(SERVER_LOGS_PATH, 'r') as f:
        data = []
        for line in f:
            if line.strip():
                try:
                    data.append(json.loads(line))
                except Exception as e:
                    print(f"Error parsing line: {e}")
                    
    print(f"Parsed {len(data)} records")
    if not data: return
    
    flattened_data = []
    for entry in data:
        sensors = entry.get("sensors", {})
        system = entry.get("system", {})
        ts = entry.get("timestamp", datetime.now().timestamp())
        dt = datetime.fromtimestamp(ts)
        
        flat = {
            "temperature": sensors.get("temperature", sensors.get("light_level", 25)),
            "humidity": sensors.get("humidity", 50),
            "cpu_usage": system.get("cpu_usage", 20),
            "power_watts": system.get("power_watts", 10),
            "network_activity": system.get("network_activity", 20),
            "hour": dt.hour
        }
        flattened_data.append(flat)
        
    df = pd.DataFrame(flattened_data)
    print(f"DataFrame shape: {df.shape}")
    print(df.head())

if __name__ == "__main__":
    test_load()
