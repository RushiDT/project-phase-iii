import requests
import json

try:
    print("Testing /api/devices endpoint...")
    response = requests.get("http://localhost:5002/api/devices")
    print(f"Status Code: {response.status_code}")
    print("Response Body:")
    try:
        data = response.json()
        print(json.dumps(data, indent=2))
        
        # Check for ESP32
        esp32 = [d for d in data if d.get('id') == 'esp32_sec_01']
        if esp32:
            print("\n[SUCCESS] Found esp32_sec_01 in response.")
        else:
            print("\n[FAIL] esp32_sec_01 NOT found in response.")
            
    except json.JSONDecodeError:
        print("Response is not valid JSON:", response.text)

except Exception as e:
    print(f"Request failed: {e}")
