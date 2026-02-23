import logging
import json
import time
import threading
import requests
import hashlib
import os
import paho.mqtt.client as mqtt
from flask import Flask, request, jsonify
from datetime import datetime

# Optional: flask-cors (not needed on Pi — CORS is for browser requests only)
try:
    from flask_cors import CORS
    HAS_CORS = True
except ImportError:
    HAS_CORS = False

# Optional: python-dotenv (falls back to OS env vars / hardcoded defaults)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Thread references for health monitoring
gateway_threads = {}

# Flush buffer diagnostics
last_flush_error = None
flush_success_count = 0
flush_fail_count = 0

# Pi health monitoring (graceful fallback on non-Pi)
try:
    from pi_health_monitor import get_health_report
    HEALTH_MONITOR_AVAILABLE = True
except ImportError:
    HEALTH_MONITOR_AVAILABLE = False

# Configure log level from .env
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s - [GATEWAY] - %(message)s")

# Track startup time for uptime calculation
STARTUP_TIME = time.time()

# Optional Raspberry Pi GPIO support
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

app = Flask(__name__)
if HAS_CORS:
    CORS(app)

# =========================
# CONFIGURATION
# =========================
GATEWAY_ID = "gateway_001"

# Central server where gateway forwards verified logs (Laptop IP)
SERVER_HOST = os.getenv("SERVER_HOST", "192.168.1.121")
SERVER_URL = f"http://{SERVER_HOST}:5002/api/logs"
DEVICE_REGISTRY_URL = f"http://{SERVER_HOST}:5002/api/devices"
ALARM_STATUS_URL = f"http://{SERVER_HOST}:5002/api/alarm/status"

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# JWT Auth
GLOBAL_JWT_TOKEN = None

# GPIO Configuration
ALARM_GPIO = int(os.getenv("ALARM_GPIO", "17"))

if GPIO_AVAILABLE:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(ALARM_GPIO, GPIO.OUT)
    GPIO.output(ALARM_GPIO, GPIO.LOW)

# Batch sending rules (Optimized for low-latency sync)
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
BATCH_INTERVAL = int(os.getenv("BATCH_INTERVAL", "2"))

# MQTT Broker Config (local LAN IP for hardware accessibility)
MQTT_BROKER = os.getenv("MQTT_BROKER", "192.168.1.161")
MQTT_PORT = 1883
MQTT_TOPIC = "iot/devices/+/data"
MQTT_USER = "admin"  # Set to None if no auth
MQTT_PASSWORD = "password123"

# Flask HTTP Port
FLASK_PORT = 8090

# Access Control Registry (Device ID -> Authorized User IDs)
# Now dynamically loaded from server
ACCESS_REGISTRY = {}
QUARANTINE_REGISTRY = set()

def authenticate_gateway():
    """Authenticate with central server to get JWT token."""
    global GLOBAL_JWT_TOKEN
    login_url = f"http://{SERVER_HOST}:5002/api/login"
    try:
        logging.info(f"🔑 Authenticating Gateway via {login_url}...")
        resp = requests.post(login_url, json={"username":"gateway", "password":"gateway_secret"}, verify=False, timeout=5)
        if resp.status_code == 200:
            GLOBAL_JWT_TOKEN = resp.json().get('token')
            logging.info("✓ Gateway Authenticated Successfully. JWT Token Acquired.")
        else:
            logging.error(f"✗ Gateway Authentication Failed! Code HTTP {resp.status_code}")
    except Exception as e:
        logging.error(f"✗ Gateway Authentication Failed (Exception): {e}")

def get_auth_headers():
    if GLOBAL_JWT_TOKEN:
        return {"Authorization": f"Bearer {GLOBAL_JWT_TOKEN}"}
    return {}

def sync_device_registry():
    """Fetch authorized devices from the server."""
    global ACCESS_REGISTRY, QUARANTINE_REGISTRY
    try:
        response = requests.get(DEVICE_REGISTRY_URL, headers=get_auth_headers(), verify=False, timeout=5)
        if response.status_code == 200:
            devices = response.json()
            new_registry = {}
            new_quarantine = set()
            for dev in devices:
                if 'id' in dev and 'user_id' in dev:
                    new_registry[dev['id']] = [dev['user_id']]
                    if dev.get('quarantined'):
                        new_quarantine.add(dev['id'])
                        
            ACCESS_REGISTRY = new_registry
            QUARANTINE_REGISTRY = new_quarantine
            logging.info(f"✓ Synced registry: {len(ACCESS_REGISTRY)} devices ({len(QUARANTINE_REGISTRY)} quarantined)")
    except Exception as e:
        logging.warning(f"⚠ Registry sync failed: {e}")

# =========================
# SMART AUTOMATION RULES
# =========================
def process_smart_rules(payload):
    """Simple edge-intelligence rules."""
    # Note: LED automation removed per user request for strictly manual control.
    pass

# =========================
# STORAGE
# =========================
data_buffer = []
device_sequence_map = {}
buffer_lock = threading.Lock()

# Failed batch storage
FAILED_BATCHES_FILE = os.path.join(os.path.dirname(__file__), "failed_batches.json")
failed_batches_lock = threading.Lock()

# =========================
# LOGGING SETUP (configured above with LOG_LEVEL)
# =========================


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

    # Access Control - HYBRID: Check local cache first, then server
    base_id = "_".join(device_id.split("_")[:3])  # e.g. esp8266_env_01
    
    # 🚨 Phase 7: Quarantine Check
    if base_id in QUARANTINE_REGISTRY or device_id in QUARANTINE_REGISTRY:
        return False, f"Device {device_id} is QUARANTINED. Dropping payload."
    
    # Check local cache first (fast path)
    if base_id in ACCESS_REGISTRY or device_id in ACCESS_REGISTRY:
        allowed_users = ACCESS_REGISTRY.get(device_id) or ACCESS_REGISTRY.get(base_id)
        if user_id not in allowed_users:
            return False, f"Permission Denied: User {user_id} not authorized for {device_id}"
    else:
        # Unknown device - verify with server in real-time
        logging.info(f"🔍 Unknown device {device_id}, verifying with server...")
        try:
            verify_url = f"{DEVICE_REGISTRY_URL}/verify/{device_id}/{user_id}"
            response = requests.get(verify_url, headers=get_auth_headers(), verify=False, timeout=3)
            if response.status_code == 200:
                result = response.json()
                if result.get("authorized"):
                    # Add to local cache for future requests
                    ACCESS_REGISTRY[base_id] = [user_id]
                    logging.info(f"✓ Server verified {device_id}, added to local cache")
                else:
                    return False, f"Server rejected: {result.get('reason', 'Unknown')}"
            else:
                return False, f"Server verification failed: HTTP {response.status_code}"
        except Exception as e:
            # Fail-secure: reject unknown devices if server unreachable
            logging.warning(f"⚠ Server unreachable for verification: {e}")
            return False, f"Unauthorized Device: {device_id} (server unreachable)"

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

    if "vibration" in sensors:
        if not (0 <= sensors["vibration"] <= 10):
            return False, "Vibration exceeds safety limit"

    # Replay Protection
    if device_id in device_sequence_map:
        last_seq = device_sequence_map[device_id]
        if seq_num <= last_seq and seq_num != 1:
            return False, f"Replay detected: Seq {seq_num} <= {last_seq}"

    device_sequence_map[device_id] = seq_num
    return True, "Valid"


# =========================
# FAILED BATCH STORAGE
# =========================
def save_failed_batch(batch_payload):
    """Save failed batch to local file for later retry."""
    with failed_batches_lock:
        try:
            failed_batches = []
            if os.path.exists(FAILED_BATCHES_FILE):
                with open(FAILED_BATCHES_FILE, 'r') as f:
                    failed_batches = json.load(f)
            
            batch_payload['failed_at'] = int(time.time())
            failed_batches.append(batch_payload)
            
            with open(FAILED_BATCHES_FILE, 'w') as f:
                json.dump(failed_batches, f, indent=2)
            
            logging.info(f"💾 Saved failed batch ({batch_payload['batch_hash'][:8]}) to local storage.")
        except Exception as e:
            logging.error(f"Failed to save batch locally: {e}")


def retry_failed_batches():
    """Background thread to retry sending failed batches."""
    RETRY_INTERVAL = 30  # seconds
    
    while True:
        time.sleep(RETRY_INTERVAL)
        
        with failed_batches_lock:
            if not os.path.exists(FAILED_BATCHES_FILE):
                continue
            
            try:
                with open(FAILED_BATCHES_FILE, 'r') as f:
                    failed_batches = json.load(f)
                
                if not failed_batches:
                    continue
                
                logging.info(f"🔄 Retrying {len(failed_batches)} failed batches...")
                
                still_failed = []
                for batch in failed_batches:
                    if not isinstance(batch, dict):
                        continue
                    
                    # Remove the failed_at timestamp before sending
                    batch_to_send = {k: v for k, v in batch.items() if k != 'failed_at'}
                    try:
                        response = requests.post(SERVER_URL, json=batch_to_send, headers=get_auth_headers(), verify=False, timeout=5)
                        # Explicit type hint and 0:8 slice to satisfy linting
                        b_hash: str = str(batch.get('batch_hash', 'unknown'))
                        batch_hash_short = b_hash[0:8]
                        if response.status_code == 200:
                            logging.info(f"✓ Retry SUCCESS: batch {batch_hash_short}")
                        else:
                            logging.warning(f"⚠ Retry failed: {response.status_code}")
                            still_failed.append(batch)
                    except Exception as e:
                        logging.warning(f"⚠ Retry failed: {e}")
                        still_failed.append(batch)
                
                # Update file with remaining failed batches
                with open(FAILED_BATCHES_FILE, 'w') as f:
                    json.dump(still_failed, f, indent=2)
                
                if len(still_failed) < len(failed_batches):
                    logging.info(f"✓ Recovered {len(failed_batches) - len(still_failed)} batches.")
                    
            except Exception as e:
                logging.error(f"Error in retry thread: {e}")


# =========================
# BUFFER FLUSH FUNCTION
# =========================
def flush_buffer():
    """Batch and forward verified data to central server."""
    global data_buffer

    global flush_success_count, flush_fail_count, last_flush_error

    while True:
        time.sleep(BATCH_INTERVAL)

        try:
            with buffer_lock:
                if not data_buffer:
                    continue

                # Real-time priority: if buffer backlog is too large, 
                # skip old entries so dashboard stays near real-time
                MAX_BUFFER_BACKLOG = 100
                if len(data_buffer) > MAX_BUFFER_BACKLOG:
                    dropped = len(data_buffer) - BATCH_SIZE
                    data_buffer = data_buffer[-BATCH_SIZE:]
                    logging.info(f"⚡ Buffer trimmed: dropped {dropped} old entries to stay real-time")

                current_batch = data_buffer[:BATCH_SIZE]
                data_buffer = data_buffer[BATCH_SIZE:]

                batch_string = json.dumps(current_batch, sort_keys=True, default=str)
                batch_hash = hashlib.sha256(batch_string.encode()).hexdigest()

            batch_payload = {
                "gateway_id": GATEWAY_ID,
                "batch_id": f"{GATEWAY_ID}_{int(time.time())}_{batch_hash[:8]}",
                "timestamp": int(time.time()),
                "batch_size": len(current_batch),
                "batch_hash": batch_hash,
                "logs": current_batch
            }

            try:
                # Refresh token periodically if unauthorized error occurs
                response = requests.post(SERVER_URL, json=batch_payload, headers=get_auth_headers(), verify=False, timeout=5)
                if response.status_code == 401 or response.status_code == 403:
                     logging.warning(f"⚠ Token expired or invalid. Re-authenticating...")
                     authenticate_gateway()
                     response = requests.post(SERVER_URL, json=batch_payload, headers=get_auth_headers(), verify=False, timeout=5)
                     
                if response.status_code == 200:
                    flush_success_count += 1
                    logging.info(f"✓ Forwarded batch ({batch_hash[:8]}) to Server.")
                else:
                    flush_fail_count += 1
                    last_flush_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    logging.warning(f"⚠ Server returned {response.status_code}")
                    save_failed_batch(batch_payload)
            except Exception as e:
                flush_fail_count += 1
                last_flush_error = f"POST exception: {str(e)[:200]}"
                logging.warning(f"⚠ Server unavailable: {e}")
                save_failed_batch(batch_payload)

        except Exception as e:
            flush_fail_count += 1
            last_flush_error = f"outer exception: {str(e)[:200]}"
            logging.error(f"✗ flush_buffer error (batch dropped): {e}")


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

def on_disconnect(client, userdata, rc):
    if rc != 0:
        logging.warning(f"⚠ MQTT disconnected unexpectedly (rc={rc}). Paho will auto-reconnect.")
    else:
        logging.info("MQTT disconnected cleanly.")


# Replay Protection tracking
last_sequence_numbers = {}

def validate_sequence_number(device_id, seq_no):
    """
    Check if sequence number is valid.
    Allows resets if seq_no is small (device restarted).
    """
    last_seq = last_sequence_numbers.get(device_id, -1)
    
    # Normal case: increasing sequence
    if seq_no > last_seq:
        last_sequence_numbers[device_id] = seq_no
        return True
        
    # Reset case: Device restarted (seq_no is small, e.g. < 50)
    if seq_no < 50:
        logging.warning(f"⚠ Device {device_id} sequence reset (sent {seq_no}, last was {last_seq}). allowing.")
        last_sequence_numbers[device_id] = seq_no
        return True
        
    # Replay case: Old sequence number
    # FOR DEMO: Allow it but log warning
    logging.warning(f"⚠ REPLAY WARNING: Device {device_id} sent {seq_no} <= {last_seq}. ALLOWING for demo stability.")
    last_sequence_numbers[device_id] = seq_no
    return True

def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode()
        payload = json.loads(payload_str)
        
        device_id = payload.get("device_id", "unknown")
        seq_no = payload.get("sequence_number", payload.get("sequence_no", 0))

        # 1. Replay Attack Detection
        if not validate_sequence_number(device_id, seq_no):
            logging.warning(f"🚫 REPLAY ATTACK DETECTED: Device {device_id} sent old/repeated seq {seq_no}. Dropping.")
            # Optionally forward alert to server
            alert_payload = {
                "device_id": device_id,
                "event_type": "SECURITY_ALERT",
                "reason": "REPLAY_ATTACK_DETECTED",
                "seq_no": seq_no,
                "timestamp": int(time.time()),
                "gateway_id": GATEWAY_ID
            }
            try:
                requests.post(f"{SERVER_URL.replace('/logs', '/alerts')}", json=alert_payload, headers=get_auth_headers(), verify=False, timeout=2)
            except Exception as e:
                logging.error(f"Failed to send replay alert: {e}")
            return

        # 2. Schema Validation
        is_valid, reason = validate_payload(payload)

        if is_valid:
            # Process Smart Home Automation Rules
            process_smart_rules(payload)
            
            with buffer_lock:
                data_buffer.append(payload)
            logging.info(f"✓ MQTT Accepted from {payload['device_id']}")
        else:
            logging.warning(f"✗ MQTT Rejected: {reason}")
            # Send immediate alert to server for blockchain logging
            alert_payload = {
                "device_id": payload.get("device_id", "unauthenticated"),
                "event_type": "SECURITY_ALERT",
                "reason": reason,
                "timestamp": int(time.time()),
                "raw_payload": payload_str[:200]
            }
            try:
                requests.post(f"{SERVER_URL.replace('/logs', '/alerts')}", json=alert_payload, headers=get_auth_headers(), verify=False, timeout=2)
            except:
                pass

    except Exception as e:
        logging.error(f"Error processing MQTT message: {e}")


def start_mqtt_listener():
    """Subscribe to MQTT broker with automatic reconnection."""
    INITIAL_BACKOFF = 1   # seconds
    MAX_BACKOFF = 60      # cap at 60s
    backoff = INITIAL_BACKOFF

    while True:
        try:
            client = mqtt.Client()
            
            if MQTT_USER and MQTT_PASSWORD:
                client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

            # Let paho handle transient drops internally
            client.reconnect_delay_set(min_delay=1, max_delay=30)

            client.on_connect = on_connect
            client.on_disconnect = on_disconnect
            client.on_message = on_message

            logging.info(f"🔌 Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}...")
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            backoff = INITIAL_BACKOFF  # reset on successful connect
            client.loop_forever()      # blocks until fatal disconnect
        except Exception as e:
            logging.error(f"✗ MQTT Listener failed: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

def periodic_registry_sync():
    """Periodically sync registry from server (resilient)."""
    while True:
        try:
            sync_device_registry()
        except Exception as e:
            logging.warning(f"⚠ Registry sync thread error: {e}")
        time.sleep(60)  # Every minute

def alarm_monitor_thread():
    """Poll server for alarm status and provide local feedback (resilient)."""
    logging.info("📢 Base Station local alarm monitor started.")
    last_state = False
    
    while True:
        try:
            response = requests.get(ALARM_STATUS_URL, headers=get_auth_headers(), verify=False, timeout=3)
            if response.status_code == 200:
                status = response.json()
                active = status.get("active", False)
                reason = status.get("reason", "Unknown Anomaly")
                
                if active:
                    # Flash visible alarm in terminal
                    print("\n" + "!" * 60)
                    print(f"🚨 BASE STATION ALARM ACTIVE: {reason} 🚨")
                    print("!" * 60 + "\n")
                    if GPIO_AVAILABLE:
                        GPIO.output(ALARM_GPIO, GPIO.HIGH)
                elif last_state and not active:
                    logging.info("✅ Base Station alarm cleared local state.")
                    if GPIO_AVAILABLE:
                        GPIO.output(ALARM_GPIO, GPIO.LOW)
                
                last_state = active
        except Exception:
            pass  # Server offline — silently retry next cycle
        
        time.sleep(3)  # Check every 3 seconds
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
    uptime_sec = int(time.time() - STARTUP_TIME)
    hours, remainder = divmod(uptime_sec, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Thread health diagnostics
    thread_status = {}
    for name, t in gateway_threads.items():
        thread_status[name] = "alive" if t.is_alive() else "DEAD"

    status_data = {
        "status": "running",
        "gateway_id": GATEWAY_ID,
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "buffer_size": len(data_buffer),
        "registered_devices": len(ACCESS_REGISTRY),
        "server_host": SERVER_HOST,
        "mqtt_broker": MQTT_BROKER,
        "threads": thread_status,
        "flush_ok": flush_success_count,
        "flush_fail": flush_fail_count,
        "last_flush_error": last_flush_error,
    }

    # Add Pi-specific info if available
    if HEALTH_MONITOR_AVAILABLE:
        try:
            health = get_health_report()
            status_data["pi_model"] = health.get("pi_model", "Unknown")
            status_data["cpu_temperature_c"] = health.get("cpu_temperature_c")
        except Exception:
            pass

    return jsonify(status_data), 200


@app.route("/pi/health", methods=["GET"])
def pi_health():
    """Raspberry Pi hardware health endpoint."""
    if not HEALTH_MONITOR_AVAILABLE:
        return jsonify({
            "status": "unavailable",
            "reason": "Pi health monitor not available (non-Pi platform or psutil not installed)"
        }), 200

    try:
        report = get_health_report()
        report["gateway_uptime_s"] = int(time.time() - STARTUP_TIME)
        report["buffer_size"] = len(data_buffer)
        return jsonify(report), 200
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)}), 500

@app.route("/api/sync", methods=["POST"])
def trigger_sync():
    """Endpoint for central server to trigger an immediate registry sync."""
    logging.info("♻ Central Server requested registry sync...")
    sync_device_registry()
    return jsonify({"status": "sync_complete", "devices_count": len(ACCESS_REGISTRY)}), 200


# =========================
# DEVICE CONTROL ENDPOINT
# =========================
mqtt_publisher = None

def get_mqtt_publisher():
    """Get or create MQTT client for publishing control commands."""
    global mqtt_publisher
    if mqtt_publisher is None:
        mqtt_publisher = mqtt.Client()
        if MQTT_USER and MQTT_PASSWORD:
            mqtt_publisher.username_pw_set(MQTT_USER, MQTT_PASSWORD)
            
        mqtt_publisher.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_publisher.loop_start()
    return mqtt_publisher

@app.route("/control", methods=["POST"])
def control_device():
    """Receive control command and forward to device via MQTT."""
    try:
        payload = request.get_json()
        device_id = payload.get("device_id")
        command = payload.get("command")
        command_id = payload.get("command_id")  # From blockchain
        
        if not device_id or not command:
            return jsonify({"status": "error", "reason": "Missing device_id or command"}), 400
        
        logging.info(f"✓ Forwarding command '{command}' to {device_id}")
        
        # Publish to MQTT control topic
        control_topic = f"iot/devices/{device_id}/control"
        control_payload = json.dumps({
            "command": command,
            "command_id": command_id,
            "timestamp": int(time.time()),
            "gateway_id": GATEWAY_ID
        })
        
        publisher = get_mqtt_publisher()
        result = publisher.publish(control_topic, control_payload)
        
        if result.rc == 0:
            logging.info(f"✓ Published control command to {control_topic}")
            return jsonify({
                "status": "forwarded",
                "device_id": device_id,
                "command": command,
                "topic": control_topic
            }), 200
        else:
            logging.error(f"✗ MQTT publish failed with code {result.rc}")
            return jsonify({"status": "error", "reason": f"MQTT publish failed: {result.rc}"}), 500
            
    except Exception as e:
        logging.error(f"Control endpoint error: {e}")
        return jsonify({"status": "error", "reason": str(e)}), 500


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    # Initial Login & Sync
    authenticate_gateway()
    sync_device_registry()
    
    gateway_threads['flush_buffer'] = threading.Thread(target=flush_buffer, daemon=True)
    gateway_threads['retry_failed'] = threading.Thread(target=retry_failed_batches, daemon=True)
    gateway_threads['mqtt_listener'] = threading.Thread(target=start_mqtt_listener, daemon=True)
    gateway_threads['registry_sync'] = threading.Thread(target=periodic_registry_sync, daemon=True)
    gateway_threads['alarm_monitor'] = threading.Thread(target=alarm_monitor_thread, daemon=True)
    for t in gateway_threads.values():
        t.start()
    
    logging.info(f"✓ Starting IoT Gateway on port {FLASK_PORT}...")
    logging.info(f"✓ API Access secured via JWT")
    logging.info(f"✓ Failed batch retry enabled (every 30s)")
    print("\n" + "="*50)
    print(" >>> GATEWAY UPDATE: REPLAY PROTECTION DISABLED <<<")
    print("="*50 + "\n")
    
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)
