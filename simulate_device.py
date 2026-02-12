import paho.mqtt.client as mqtt
import json
import time
import os
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BROKER = os.getenv("MQTT_BROKER", "127.0.0.1")
PORT = 1883
DEVICE_ID = "esp32_sec_01"  # Matches the ID used in Dashboard
TOPIC_DATA = f"iot/devices/{DEVICE_ID}/data"
TOPIC_CONTROL = f"iot/devices/{DEVICE_ID}/control"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Connected to MQTT Broker at {BROKER}:{PORT}")
        client.subscribe(TOPIC_CONTROL)
        print(f"📡 Subscribed to Control Topic: {TOPIC_CONTROL}")
    else:
        print(f"❌ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        command = payload.get("command")
        print("\n" + "="*40)
        print(f"⚡ COMMAND RECEIVED: {command}")
        print(f"   Full Payload: {payload}")
        print("="*40 + "\n")
        
        # Simulate action
        if command == "LIGHT_ON":
            print("💡 Light turned ON")
        elif command == "LIGHT_OFF":
            print("🌑 Light turned OFF")
            
    except Exception as e:
        print(f"⚠ Error processing message: {e}")

def main():
    print(f"🚀 Starting Virtual Device: {DEVICE_ID}")
    
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        
        seq_num = 1
        while True:
            # Send telemetry every 5 seconds to keep dashboard alive
            telemetry = {
                "device_id": DEVICE_ID,
                "user_id": "user_456",
                "timestamp": int(time.time()),
                "sequence_number": seq_num,
                "sensors": {
                    "motion": random.choice([True, False]),
                    "light_state": random.choice([True, False]),
                    "vibration": round(random.uniform(0, 0.1), 2)
                },
                "system": {
                    "battery_level": 98,
                    "cpu_usage": random.randint(5, 15),
                    "wifi_signal": -50
                }
            }
            
            client.publish(TOPIC_DATA, json.dumps(telemetry))
            print(f"📤 Sent telemetry #{seq_num}", end="\r")
            seq_num += 1
            time.sleep(5)
            
    except ConnectionRefusedError:
        print(f"\n❌ CRITICAL: Could not connect to MQTT Broker at {BROKER}:{PORT}")
        print("   Make sure Mosquitto is installed and running!")
        print("   Windows: 'net start mosquitto' (if service) or run 'mosquitto -v'")
    except KeyboardInterrupt:
        print("\n🛑 Stopping simulator")
        client.disconnect()

if __name__ == "__main__":
    main()
