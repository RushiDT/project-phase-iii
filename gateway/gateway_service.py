import logging
import json
import time
import threading
import requests
import hashlib
import paho.mqtt.client as mqtt
from flask import Flask, request, jsonify
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# =========================
# CONFIGURATION
# =========================
GATEWAY_ID = "gateway_001"

# Central server where gateway forwards verified logs (Laptop IP)
SERVER_URL = "http://192.168.1.121:5002/api/logs"

# Batch sending rules
BATCH_SIZE = 5
BATCH_INTERVAL = 10

# MQTT Broker Config (Mosquitto on PC)
MQTT_BROKER = "192.168.1.133"
MQTT_PORT = 1883
MQTT_TOPIC = "iot/devices/+/data"

# Flask HTTP Port
FLASK_PORT = 8090

# Access Control Registry (Device ID -> Authorized User IDs)
ACCESS_REGISTRY = {
    "esp32_sim_01": ["user_789"],
    "esp32_sim_02": ["user_456"],
    "esp32_env_01": ["user_789"],
    "esp8266_env_01": ["user_789"],
    "esp32_sec_01": ["user_456"]
}

# =========================
# STORAGE
# =========================
data_buffer = []
device_sequence_map = {}
buffer_lock = threading.Lock()

# =========================
# LOGGING SETUP
# =========================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [GATEWAY] - %(message)s")


# =========================
# VALIDATION FUNCTION
# =========================
def validate_payload(payload):
    """Multi-level validation: Fields, Identity, Values, Replay."""
    required_keys = ["device_id", "user_id", "timestamp", "sequence_number", "sensors", "system"]

    if not all(key in payload for key in required_keys):
        return False, "Missing required top-level keys"

    device_id = payload["device_id"]
    user_id = payload["user_id"]
    timestamp = payload["timestamp"]
    seq_num = payload["sequence_number"]
    sensors = payload["sensors"]
    system = payload["system"]

    # Access Control - Dynamic check to allow variants like esp8266_env_01_xxxx
    base_id = "_".join(device_id.split("_")[:3]) # e.g. esp8266_env_01
    
    if base_id not in ACCESS_REGISTRY and device_id not in ACCESS_REGISTRY:
        return False, f"Unauthorized Device: {device_id}"

    allowed_users = ACCESS_REGISTRY.get(device_id) or ACCESS_REGISTRY.get(base_id)
    if user_id not in allowed_users:
        return False, f"Permission Denied: User {user_id} not authorized for {device_id}"

    # Timestamp Handling
    if timestamp == 0:
        payload["timestamp"] = int(time.time())
    else:
        current_time = int(time.time())
        if abs(current_time - timestamp) > 300: # Increased threshold for multi-PC latency
            return False, f"Timestamp mismatch: skew {abs(current_time - timestamp)}s"

    # Sensor sanity checks
    if "temperature" in sensors:
        if not (0 <= sensors["temperature"] <= 100):
            return False, "Temperature out of range"

    if "humidity" in sensors:
        if not (0 <= sensors["humidity"] <= 100):
            return False, "Humidity out of range"

    # Replay Protection
    if device_id in device_sequence_map:
        last_seq = device_sequence_map[device_id]
        if seq_num <= last_seq and seq_num != 1:
            return False, f"Replay detected: Seq {seq_num} <= {last_seq}"

    device_sequence_map[device_id] = seq_num
    return True, "Valid"


# =========================
# BUFFER FLUSH FUNCTION
# =========================
def flush_buffer():
    """Batch and forward verified data to central server."""
    global data_buffer

    while True:
        time.sleep(BATCH_INTERVAL)

        with buffer_lock:
            if not data_buffer:
                continue

            current_batch = data_buffer[:BATCH_SIZE]
            data_buffer = data_buffer[BATCH_SIZE:]

            batch_string = json.dumps(current_batch, sort_keys=True)
            batch_hash = hashlib.sha256(batch_string.encode()).hexdigest()

        batch_payload = {
            "gateway_id": GATEWAY_ID,
            "timestamp": int(time.time()),
            "batch_size": len(current_batch),
            "batch_hash": batch_hash,
            "logs": current_batch
        }

        try:
            response = requests.post(SERVER_URL, json=batch_payload, timeout=5)
            if response.status_code == 200:
                logging.info(f"✓ Forwarded batch ({batch_hash[:8]}) to Laptop Server.")
            else:
                logging.warning(f"⚠ Server returned {response.status_code}")
                with buffer_lock:
                    data_buffer = current_batch + data_buffer
        except Exception as e:
            logging.warning(f"⚠ Laptop Server unavailable: {e}")
            with buffer_lock:
                data_buffer = current_batch + data_buffer


# =========================
# MQTT CALLBACKS
# =========================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("✓ Connected to MQTT Broker")
        client.subscribe(MQTT_TOPIC)
        logging.info(f"✓ Subscribed to: {MQTT_TOPIC}")
    else:
        logging.error(f"✗ MQTT connection failed with code {rc}")


def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode()
        payload = json.loads(payload_str)

        is_valid, reason = validate_payload(payload)

        if is_valid:
            with buffer_lock:
                data_buffer.append(payload)
            logging.info(f"✓ MQTT Accepted from {payload['device_id']}")
        else:
            logging.warning(f"✗ MQTT Rejected: {reason}")

    except Exception as e:
        logging.error(f"MQTT message processing error: {e}")


def start_mqtt_listener():
    """Start MQTT Client in background thread."""
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()


# =========================
# FLASK ROUTES
# =========================
@app.route("/api/submit", methods=["POST"])
def submit_device_data():
    try:
        payload = request.get_json()
        is_valid, reason = validate_payload(payload)
        if is_valid:
            with buffer_lock:
                data_buffer.append(payload)
            return jsonify({"status": "accepted"}), 200
        else:
            return jsonify({"status": "rejected", "reason": reason}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/status", methods=["GET"])
def gateway_status():
    return jsonify({"status": "running", "gateway_id": GATEWAY_ID}), 200


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    threading.Thread(target=flush_buffer, daemon=True).start()
    threading.Thread(target=start_mqtt_listener, daemon=True).start()
    logging.info(f"✓ Starting IoT Gateway on port {FLASK_PORT}...")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)
