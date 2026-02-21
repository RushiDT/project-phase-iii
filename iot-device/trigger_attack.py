import paho.mqtt.client as mqtt
import json
import time

MQTT_BROKER = "192.168.1.161"
MQTT_PORT = 1883
MQTT_USER = "admin"
MQTT_PASSWORD = "password123"
# Use one of the registered device IDs
DEVICE_ID = "esp32_light_motion"
TOPIC = f"iot/devices/{DEVICE_ID}/control"

def trigger_attack():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        payload = {"command": "MODE_ATTACK"}
        print(f"[!] Sending command: {payload} to {TOPIC}")
        client.publish(TOPIC, json.dumps(payload))
        
        time.sleep(1)
        client.disconnect()
        print("[✓] Attack mode triggered. Monitor ML Engine for detections.")
    except Exception as e:
        print(f"[✗] Error: {e}")

if __name__ == "__main__":
    trigger_attack()
