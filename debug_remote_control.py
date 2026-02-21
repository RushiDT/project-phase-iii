import requests
import json
import time

GATEWAY_IP = "192.168.1.161"
GATEWAY_PORT = 8090
DEVICE_ID = "esp32_sec_01"

print(f"Testing connection to Remote Gateway at {GATEWAY_IP}:{GATEWAY_PORT}...")

# 1. Test Status Endpoint
try:
    url = f"http://{GATEWAY_IP}:{GATEWAY_PORT}/status"
    print(f"[TEST 1] GET {url}")
    resp = requests.get(url, timeout=5)
    print(f"  Result: {resp.status_code}")
    print(f"  Body: {resp.text}")
except Exception as e:
    print(f"  FAILED: {e}")

# 2. Test Control Endpoint (Light ON)
try:
    url = f"http://{GATEWAY_IP}:{GATEWAY_PORT}/control"
    payload = {
        "device_id": DEVICE_ID,
        "command": "LIGHT_ON",
        "command_id": "debug_test_01"
    }
    print(f"\n[TEST 2] POST {url}")
    print(f"  Payload: {json.dumps(payload)}")
    resp = requests.post(url, json=payload, timeout=5)
    print(f"  Result: {resp.status_code}")
    print(f"  Body: {resp.text}")
except Exception as e:
    print(f"  FAILED: {e}")
