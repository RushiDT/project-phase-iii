import requests
import json
import time
import hashlib

# Configuration
# We send data to the Server, which forwards to ML Engine
SERVER_URL = "http://localhost:5002/api/logs"
DEVICE_ID = "esp32_sec_01"
GATEWAY_ID = "gateway_001"

def simulate_crypto_mining():
    print(f"\n[ATTACK] Simulating CRYPTO MINING attack on {DEVICE_ID}...")
    print("---------------------------------------------------------------")
    print(f"Target: {SERVER_URL}")
    print("Payload: CPU=98%, Power=120W (Crypto Mining Signature)")
    print("---------------------------------------------------------------")
    
    # 1. Create the malicious log entry
    log_entry = {
        "device_id": DEVICE_ID,
        "user_id": "user_456",
        "timestamp": int(time.time()),
        "sequence_number": 9999,
        "sensors": {
            "motion": True,
            "temperature": 75,
            "vibration": 0.05
        },
        "system": {
            # These values trigger the 'crypto_mining' rule
            "cpu_usage": 98,
            "power_watts": 120,
            "battery_level": 40,
            "network_activity": 50,
            "firmware_version": "v1.2.0"
        }
    }

    # 2. Wrap it in a Gateway Batch (Server expects this format)
    batch_logs = [log_entry]
    batch_string = json.dumps(batch_logs, sort_keys=True)
    batch_hash = hashlib.sha256(batch_string.encode()).hexdigest()

    batch_payload = {
        "gateway_id": GATEWAY_ID,
        "batch_id": f"attack_{int(time.time())}",
        "timestamp": int(time.time()),
        "batch_size": 1,
        "batch_hash": batch_hash,
        "logs": batch_logs
    }
    
    try:
        # Send to Server
        print("Sending batch to Server...")
        response = requests.post(SERVER_URL, json=batch_payload, timeout=5)
        
        if response.status_code == 200:
            print("[✅] Attack batch accepted by Server!")
            print(f"     Response: {response.json()}")
            print("\n[->] Server should now forward this to ML Engine...")
            print("[->] Check your Dashboard for a critical alert!")
            print("[->] Check 'ml-engine/anomaly_results.json' for the log.")
        else:
            print(f"[X] Attack failed: {response.text}")

    except Exception as e:
        print(f"[!] Error sending attack: {e}")

if __name__ == "__main__":
    simulate_crypto_mining()
