import time
import json
import random
import uuid
import sys
import paho.mqtt.client as mqtt

# Configuration
DEVICES = [
    {"id": "esp32_sim_01", "user_id": "user_789", "type": "environmental"},
    {"id": "esp32_sim_02", "user_456": "user_456", "type": "security"}
]
LOCATION = "warehouse_zone_A"
INTERVAL = 3  # Seconds between readings
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

# Device state
is_running = True

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("[MQTT] Connected to broker")
        for dev in DEVICES:
            topic = f"iot/devices/{dev['id']}/control"
            client.subscribe(topic)
            print(f"[MQTT] Subscribed to {topic}")
    else:
        print(f"[MQTT] Connection failed with code {rc}")

def on_message(client, userdata, msg):
    global is_running
    try:
        payload = json.loads(msg.payload.decode())
        command = payload.get("command")
        print(f"[MQTT] Received command for {msg.topic}: {command}")
        if command == "STOP":
            is_running = False
        elif command == "START":
            is_running = True
    except Exception as e:
        print(f"[MQTT] Error processing message: {e}")

def generate_telemetry(device, sequence_number):
    """Generates a JSON object mimicking the ESP32 payload based on device type."""
    sensors = {"vibration": round(random.uniform(0.0, 2.0), 3)}
    
    if device["type"] == "environmental":
        temp = round(random.uniform(20.0, 30.0), 2)
        humidity = round(random.uniform(40.0, 60.0), 2)
        if random.random() < 0.05: # Anomaly
            temp += 20
        sensors["temperature"] = temp
        sensors["humidity"] = humidity
    elif device["type"] == "security":
        sensors["motion"] = random.random() < 0.1 # 10% chance of motion
        sensors["light_level"] = random.randint(200, 800)
    
    battery = round(max(0, 100 - (sequence_number * 0.01)), 2)
    
    payload = {
        "device_id": device["id"],
        "user_id": device.get("user_id", "user_789"),
        "timestamp": int(time.time()),
        "sequence_number": sequence_number,
        "sensors": sensors,
        "system": {
            "battery_level": battery,
            "cpu_usage": round(random.uniform(10, 40), 1),
            "wifi_signal": random.randint(-70, -50)
        }
    }
    return payload

def main():
    global is_running
    print(f"Starting MQTT IoT Simulator for {len(DEVICES)} Devices...")
    print(f"Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print("Press Ctrl+C to stop.\n")
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"could not connect to MQTT broker: {e}")
        sys.exit(1)
        
    client.loop_start()
    
    seq = 1
    try:
        while True:
            if is_running:
                for dev in DEVICES:
                    data = generate_telemetry(dev, seq)
                    topic = f"iot/devices/{dev['id']}/data"
                    result = client.publish(topic, json.dumps(data))
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        print(f"[{seq}] Published {dev['id']}: Success")
                    else:
                        print(f"[{seq}] Published {dev['id']}: Failed ({result.rc})")
                
                seq += 1
            else:
                print("[SIMULATOR] Simulation is STOPPED.")
            
            time.sleep(INTERVAL)
            
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()

