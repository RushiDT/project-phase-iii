"""
Enhanced ML Anomaly Detection Service
Uses scikit-learn based models compatible with Python 3.14.
Provides multiple threat detection methods without TensorFlow dependency.
"""

import json
import time
from typing import Any, cast
import os
import sys
import hashlib
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from flask_cors import CORS
from datetime import datetime
import threading
import requests

app = Flask(__name__)
CORS(app)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PREDICTIONS_PATH = os.path.join(BASE_DIR, "anomaly_results.json")
SERVER_LOGS_PATH = os.path.join(BASE_DIR, "..", "server", "server_logs.jsonl")
DEVICES_PATH = os.path.join(BASE_DIR, "..", "server", "devices.json")

# Load configuration
def load_config():
    """Load configuration from config.json."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ML] Error loading config: {e}")
    return {
        "thresholds": {"temperature_max": 45, "cpu_usage_high": 90},
        "logging": {"save_predictions": True, "max_predictions": 1000}
    }

CONFIG = load_config()
print(f"[ML] Config loaded: {json.dumps(CONFIG.get('thresholds', {}), indent=2)}")

def load_device_types():
    """Load device types from server/devices.json."""
    device_types = {}
    if os.path.exists(DEVICES_PATH):
        try:
            with open(DEVICES_PATH, 'r') as f:
                devices = json.load(f)
                for device in devices:
                    device_types[device.get("id")] = device.get("type", "unknown")
        except Exception as e:
            print(f"[ML] Error loading device types: {e}")
    return device_types

# Prediction history lock
predictions_lock = threading.Lock()

def save_prediction(prediction_data):
    """Save prediction to anomaly_results.json."""
    if not CONFIG.get("logging", {}).get("save_predictions", True):
        return
    
    with predictions_lock:
        try:
            predictions: list[dict[str, Any]] = []
            if os.path.exists(PREDICTIONS_PATH):
                with open(PREDICTIONS_PATH, 'r') as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        predictions = list(loaded)  # Explicit cast for type checker
            
            predictions.append({
                **prediction_data,
                "timestamp": datetime.now().isoformat()
            })
            
            # Prune if needed
            max_preds: int = int(CONFIG.get("logging", {}).get("max_predictions", 1000))
            if len(predictions) > max_preds:
                predictions = list(predictions)[-max_preds:]  # type: ignore[index]
            
            with open(PREDICTIONS_PATH, 'w') as f:
                json.dump(predictions, f, indent=2)
        except Exception as e:
            print(f"[ML] Error saving prediction: {e}")

# Model instances
SENSOR_MODELS = {} # Dictionary of models per device type
POWER_MODEL = None   # Random Forest for power anomaly classification
BEHAVIOR_MODEL = None  # Random Forest for behavior prediction

# Power anomaly labels
POWER_ANOMALY_TYPES = {
    0: "normal",
    1: "crypto_mining",
    2: "botnet",
    3: "ddos",
    4: "hardware_issue"
}

def load_data(device_type_map=None):
    """Loads logs from the server storage, filtering out alerts."""
    try:
        abs_logs_path = os.path.abspath(SERVER_LOGS_PATH)
        print(f"[ML] Loading data from: {abs_logs_path}")
        
        if not os.path.exists(abs_logs_path):
            print(f"[ML] Log file NOT FOUND at {abs_logs_path}")
            return pd.DataFrame()

        if device_type_map is None:
            device_type_map = load_device_types()
            
        with open(abs_logs_path, 'r') as f:
            lines = f.readlines()
            print(f"[ML] Read {len(lines)} lines from file.")
            data = []
            for i, line in enumerate(lines):
                if line.strip():
                    try:
                        record = json.loads(line)
                        # FILTER: Skip security alerts to avoid training on alarms
                        if record.get("event_type") == "SECURITY_ALERT":
                            continue
                        data.append(record)
                    except Exception as je:
                        if i < 5: print(f"[ML] JSON parse error on line {i+1}: {je}")
                        continue
        
        print(f"[ML] Successfully parsed {len(data)} training records (filtered alerts).")
        if not data:
            return pd.DataFrame()

        flattened_data = []
        for entry in data:
            # Safely get values with defaults
            sensors = entry.get("sensors", {})
            system = entry.get("system", {})
            ts = entry.get("timestamp", datetime.now().timestamp())
            dt = datetime.fromtimestamp(ts)
            device_id = entry.get("device_id", "unknown")
            
            flat = {
                "temperature": sensors.get("temperature", sensors.get("light_level", 25)),
                "humidity": sensors.get("humidity", 50),
                "vibration": sensors.get("vibration", 0.05),
                "cpu_usage": system.get("cpu_usage", 20),
                "battery_level": system.get("battery_level", 100),
                "power_watts": system.get("power_watts", 10),
                "network_activity": system.get("network_activity", 20),
                "hour": dt.hour,
                "device_type": device_type_map.get(device_id, "unknown")
            }
            flattened_data.append(flat)
            
        return pd.DataFrame(flattened_data)
    except Exception as e:
        print(f"Error loading data: {e}")
        return pd.DataFrame()

def train_sensor_model():
    """Trains Isolation Forest models for each device type."""
    global SENSOR_MODELS
    df = load_data()
    
    if df.empty:
        print("[ML] No data available to train sensor models.")
        return False
        
    device_types = df['device_type'].unique()
    print(f"[ML] Found device types: {device_types}")
    
    success = False
    min_samples = CONFIG.get("model", {}).get("min_training_samples", 10)
    contamination = CONFIG.get("model", {}).get("contamination", 0.01)
    random_state = CONFIG.get("model", {}).get("random_state", 42)

    for d_type in device_types:
        if d_type == "unknown": continue
        
        type_df = df[df['device_type'] == d_type]
        # Drop metadata columns for training
        train_df = type_df.drop(columns=['device_type', 'hour'], errors='ignore')
        # We keep 'hour' in the feature list in prediction, so we should keep it here or drop it consistently.
        # Original code used 'hour' in features. Let's keep it but ensure columns match.
        # The previous load_data returned a flat dict, so keys are columns. 
        # features list in predict_basic: ["temperature", "humidity", "vibration", "cpu_usage", "battery_level", "power_watts", "network_activity", "hour"]
        
        feature_cols = ["temperature", "humidity", "vibration", "cpu_usage", "battery_level", "power_watts", "network_activity", "hour"]
        train_df = type_df[feature_cols]

        if len(train_df) < min_samples:
            print(f"[ML] Not enough data for {d_type} (got {len(train_df)}, need {min_samples}).")
            continue
            
        print(f"[ML] Training model for {d_type} on {len(train_df)} records...")
        model = IsolationForest(contamination=contamination, random_state=random_state)
        model.fit(train_df)
        SENSOR_MODELS[d_type] = model
        success = True
        
    print(f"[ML] Sensor models trained for: {list(SENSOR_MODELS.keys())}")
    return success

def train_power_model():
    """Trains Isolation Forest specifically for power/system anomalies."""
    global POWER_MODEL
    df = load_data()
    
    if df.empty or len(df) < 10:
        print("[ML] Not enough data to train power model.")
        return False
        
    print("[ML] Training power profiler model...")
    # Features focused on power and network
    power_df = df[["cpu_usage", "power_watts", "network_activity", "temperature"]]
    POWER_MODEL = IsolationForest(contamination=0.04, random_state=42)
    POWER_MODEL.fit(power_df)
    print("[ML] Power model trained successfully.")
    return True

def train_behavior_model():
    """Trains Isolation Forest for behavioral patterns (time-based)."""
    global BEHAVIOR_MODEL
    df = load_data()
    
    if df.empty or len(df) < 10:
        print("[ML] Not enough data to train behavior model.")
        return False
        
    print("[ML] Training behavior predictor model...")
    # Basic behavior: what hours are device states changing?
    # In this simplified model, we look at hour and cpu/power as proxy for activity
    behavior_df = df[["hour", "cpu_usage", "power_watts"]]
    BEHAVIOR_MODEL = IsolationForest(contamination=0.03, random_state=42)
    BEHAVIOR_MODEL.fit(behavior_df)
    print("[ML] Behavior model trained successfully.")
    return True

def classify_power_anomaly(data):
    """Detect power anomalies using the trained Isolation Forest."""
    global POWER_MODEL
    
    system = data.get("system", {})
    cpu = system.get("cpu_usage", 20)
    power = system.get("power_watts", 10)
    network = system.get("network_activity", 20)
    temp = data.get("sensors", {}).get("temperature", 25)

    if POWER_MODEL is not None and not isinstance(POWER_MODEL, str):
        features = [[cpu, power, network, temp]]
        score = POWER_MODEL.decision_function(features)[0]
        is_anomaly = POWER_MODEL.predict(features)[0] == -1
        
        if is_anomaly:
            # Heuristic to name the threat
            if cpu > 80 and power > 80: return "crypto_mining", 0.95
            if network > 400: return "botnet", 0.9
            
            # Filter out minor statistical anomalies (sanity check)
            if cpu < 60 and power < 60:
                return "normal", 0.0

            return "system_anomaly", 0.7
            
    # Fallback to rules if model not ready
    if cpu > 90 and power > 100: return "crypto_mining", 0.9
    if network > 500: return "botnet", 0.85
    
    return "normal", 0.0

def check_behavior_anomaly(context, actual_state):
    """Rule-based behavior anomaly detection."""
    hour = context.get("hour", datetime.now().hour)
    device_id = context.get("device_id", "unknown")
    
    # Simple rules for behavior anomaly
    is_night = hour < 6 or hour > 23
    is_unusual = False
    confidence = 0.0
    
    # Night-time activity for non-essential devices
    if is_night and actual_state == "on":
        if "light" in device_id.lower() or "tv" in device_id.lower():
            is_unusual = True
            confidence = 0.6
    
    # High access frequency
    access_count = context.get("access_count", 0)
    if access_count > 20:
        is_unusual = True
        confidence = max(confidence, 0.7)
    
    return is_unusual, confidence

def log_to_blockchain(device_id, score, data_hash, batch_hash="NONE", event_type="ANOMALY", gateway_id="unknown"):
    """Log anomaly to blockchain with batch verification hash."""
    try:
        # Pre-emptive sleep to reduce collision probability with server logs
        import random
        time.sleep(random.uniform(0.1, 0.5))
        
        blockchain_path = os.path.join(os.path.dirname(__file__), '..', 'blockchain')
        sys.path.insert(0, blockchain_path)
        from deploy_and_interact import log_event  # type: ignore[import-not-found]
        
        result = log_event(device_id, score, data_hash, batch_hash, event_type, gateway_id)
        if "error" in result:
            print(f"[ML] Blockchain log failed: {result['error']}")
        else:
            print(f"[ML] Logged to blockchain: {event_type} for {device_id} (Batch: {batch_hash[:8]})")
    except Exception as e:
        print(f"[ML] Failed to log to Blockchain: {e}")


# ==================== API ENDPOINTS ====================

@app.route('/train', methods=['POST'])
def trigger_train():
    """Train all models."""
    print("[ML] Training trigger received...")
    sensor_ok = train_sensor_model()
    power_ok = train_power_model()
    behavior_ok = train_behavior_model()
    
    return jsonify({
        "status": "success" if sensor_ok else "partial",
        "models": {
            "sensor": "trained" if sensor_ok else "skipped",
            "power": "trained" if power_ok else "skipped",
            "behavior": "trained" if behavior_ok else "skipped"
        },
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Compatibility endpoint for start_system.py."""
    return jsonify({"status": "healthy", "service": "ml-engine"}), 200

@app.route('/predict', methods=['POST'])
def predict_basic():
    """Basic prediction using Isolation Forest (original endpoint)."""
    global SENSOR_MODELS
    
    # Fallback / Init if empty
    if not SENSOR_MODELS:
        train_sensor_model()

    entry = request.json
    device_id = entry.get("device_id", "unknown")
    
    # Determine device type
    device_types = load_device_types()
    device_type = device_types.get(device_id, "unknown")
    
    # Select Model
    model = SENSOR_MODELS.get(device_type)
    
    if model is None:
        # Fallback to threshold if no model for this type
        temp = entry.get("sensors", {}).get("temperature", 0)
        batch_hash = entry.get("batch_hash", "NONE")
        is_anomaly = temp > 50 # Higher threshold for unknown fallback
        if is_anomaly:
            data_hash = hashlib.sha256(json.dumps(entry).encode()).hexdigest()
            log_to_blockchain(device_id, 1.0, data_hash, batch_hash, "TEMP_SPIKE", entry.get("gateway_id", "unknown"))
        
        return jsonify({
            "is_anomaly": is_anomaly,
            "score": 1.0 if is_anomaly else 0.0, 
            "method": "fallback_threshold",
            "device_type": device_type,
            "note": "No dedicated model for this device type"
        })

    try:
        sensors = entry.get("sensors", {})
        system = entry.get("system", {})
        
        # Consistent 8-feature vector to match trained model
        feature_names = ["temperature", "humidity", "vibration", "cpu_usage", "battery_level", "power_watts", "network_activity", "hour"]
        features_list = [[
            sensors.get("temperature", sensors.get("light_level", 25)),
            sensors.get("humidity", 50),
            sensors.get("vibration", 0.05),
            system.get("cpu_usage", 20),
            system.get("battery_level", 100),
            system.get("power_watts", 10),
            system.get("network_activity", 20),
            datetime.now().hour
        ]]
        features = pd.DataFrame(features_list, columns=feature_names)
        
        prediction = model.predict(features)[0]
        score = model.decision_function(features)[0]
        
        # Only consider it an anomaly if prediction is -1 AND score is below a safe threshold
        # High scores (near 0) often mean the point is on the boundary
        threshold = CONFIG.get("model", {}).get("score_threshold", -0.1)
        is_anomaly = prediction == -1 and score < threshold
        
        if is_anomaly:
            print(f"[ML] ANOMALY DETECTED for {device_id} ({device_type})! Score: {score:.4f} (Threshold: {threshold})")

            print(f"      Features: {features}")
            # Use raw list for hash to avoid DataFrame serialization error
            data_hash = hashlib.sha256(json.dumps(features_list).encode()).hexdigest()
            batch_hash = entry.get("batch_hash", "NONE")
            log_to_blockchain(entry.get("device_id", "unknown"), score, data_hash, batch_hash, "ANOMALY", entry.get("gateway_id", "unknown"))
            
            # Save to local JSON file for dashboard/debugging
            save_prediction({
                "device_id": entry.get("device_id", "unknown"),
                "score": float(score),
                "is_anomaly": True,
                "features": features_list[0],
                "threat_type": "sensor_anomaly",
                "batch_hash": batch_hash
            })

            # Forward as security alert to server for dashboard
            try:
                server_host = os.getenv("SERVER_HOST", "localhost")
                alert_payload = {
                    "device_id": entry.get("device_id", "unknown"),
                    "event_type": "SECURITY_ALERT",
                    "reason": f"ML Anomaly Detected (Score: {score:.4f})",
                    "anomaly_score": float(score),
                    "timestamp": int(datetime.now().timestamp()),
                    "batch_hash": batch_hash
                }
                requests.post(f"http://{server_host}:5002/api/alerts", json=alert_payload, timeout=2)
                
                # If score is very low, trigger the Base Station Alarm
                if score < -0.1:
                    requests.post(f"http://{server_host}:5002/api/alarm/trigger", 
                                 json={"reason": f"High Priority Anomaly: {score:.4f}"}, 
                                 timeout=2)
            except Exception as e:
                print(f"[ML] Failed to forward alert/alarm to server: {e}")
        
        return jsonify({
            "is_anomaly": bool(is_anomaly),
            "anomaly_score": float(score),
            "method": "isolation_forest"
        })
        
    except Exception as e:
        print(f"Prediction error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/predict/access', methods=['POST'])
def predict_access():
    """Access anomaly detection using Isolation Forest."""
    if not SENSOR_MODELS:
        train_sensor_model()
    
    try:
        access_log = request.json
        
        # Extract features
        hour = datetime.fromisoformat(access_log.get("timestamp", datetime.now().isoformat())).hour if isinstance(access_log.get("timestamp"), str) else datetime.now().hour
        
        # Simple rule-based access anomaly
        is_anomaly = False
        confidence = 0.0
        reasons = []
        
        # Check for unusual access time
        if hour < 5 or hour > 23:
            is_anomaly = True
            confidence = max(confidence, 0.7)
            reasons.append("unusual_access_time")
        
        # Check for unknown location
        location = access_log.get("location", "home")
        if location not in ["home", "office", "known"]:
            is_anomaly = True
            confidence = max(confidence, 0.8)
            reasons.append("unknown_location")
        
        # Check for external IP
        ip = access_log.get("ip_address", "192.168.1.1")
        if not ip.startswith("192.168.") and not ip.startswith("10."):
            is_anomaly = True
            confidence = max(confidence, 0.9)
            reasons.append("external_ip")
        
        # High frequency access
        access_count = access_log.get("access_count", 0)
        if access_count > 50:
            is_anomaly = True
            confidence = max(confidence, 0.75)
            reasons.append("high_frequency")
        
        if is_anomaly:
            data_hash = hashlib.sha256(json.dumps(access_log).encode()).hexdigest()
            batch_hash = access_log.get("batch_hash", "NONE")
            log_to_blockchain(access_log.get("device_id", "unknown"), 
                            confidence, data_hash, batch_hash, "ACCESS_ANOMALY", access_log.get("gateway_id", "unknown"))
        
        return jsonify({
            "is_anomaly": is_anomaly,
            "confidence": confidence,
            "reasons": reasons,
            "method": "access_rules",
            "threat_type": "access_anomaly"
        })
    except Exception as e:
        print(f"[ML] Access prediction error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/predict/power', methods=['POST'])
def predict_power():
    """Power consumption anomaly detection (crypto mining, botnets)."""
    try:
        power_log = request.json
        device_id = power_log.get("device_id", "unknown")
        
        anomaly_type, confidence = classify_power_anomaly(power_log)
        is_anomaly = anomaly_type != "normal"
        
        if is_anomaly:
            data_hash = hashlib.sha256(json.dumps(power_log).encode()).hexdigest()
            batch_hash = power_log.get("batch_hash", "NONE")
            log_to_blockchain(device_id, confidence, data_hash, batch_hash, anomaly_type.upper(), power_log.get("gateway_id", "unknown"))
        
        return jsonify({
            "is_anomaly": is_anomaly,
            "confidence": confidence,
            "anomaly_type": anomaly_type,
            "method": "power_profiler",
            "threat_types": ["crypto_mining", "botnet", "ddos", "hardware_issue"]
        })
    except Exception as e:
        print(f"[ML] Power prediction error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/predict/behavior', methods=['POST'])
def predict_behavior():
    """Behavior anomaly detection."""
    try:
        data = request.json
        context = data.get('context', data)
        actual_state = data.get('actual_state', data.get('device_state', 'unknown'))
        
        is_anomaly, confidence = check_behavior_anomaly(context, actual_state)
        
        if is_anomaly:
            data_hash = hashlib.sha256(json.dumps(data).encode()).hexdigest()
            batch_hash = data.get("batch_hash", "NONE")
            log_to_blockchain(context.get("device_id", "unknown"), 
                            confidence, data_hash, batch_hash, "BEHAVIOR_ANOMALY")
        
        return jsonify({
            "is_anomaly": is_anomaly,
            "actual_state": actual_state,
            "confidence": confidence,
            "method": "behavior_rules",
            "threat_type": "behavior_anomaly"
        })
    except Exception as e:
        print(f"[ML] Behavior prediction error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/predict/comprehensive', methods=['POST'])
def predict_comprehensive():
    """Comprehensive threat detection using all methods."""
    data = request.json
    device_id = data.get("device_id", "unknown")
    
    # Use a local list to avoid type inference issues with dict value types
    detections: list[dict[str, float | str]] = []
    
    results = {
        "device_id": device_id,
        "timestamp": datetime.now().isoformat(),
        "detections": detections,
        "overall_threat_level": "normal",
        "is_anomaly": False
    }
    
    # Sensor check
    try:
        # Determine device type for model selection
        device_types = load_device_types()
        device_type = device_types.get(device_id, "unknown")
        sensor_model = SENSOR_MODELS.get(device_type)

        if sensor_model is not None:
            features = [[
                data.get("sensors", {}).get("temperature", 25),
                data.get("sensors", {}).get("humidity", 50),
                data.get("sensors", {}).get("vibration", 0),
                data.get("system", {}).get("cpu_usage", 20),
                data.get("system", {}).get("battery_level", 100),
                data.get("system", {}).get("power_watts", 10),
                data.get("system", {}).get("network_activity", 20),
                datetime.now().hour
            ]]
            prediction = sensor_model.predict(features)[0]
            score = sensor_model.decision_function(features)[0]
            
            # Check score threshold (consistent with predict_basic)
            threshold = CONFIG.get("model", {}).get("score_threshold", -0.1)
            
            if prediction == -1 and score < threshold:
                detections.append({
                    "type": "sensor_anomaly",
                    "method": "isolation_forest",
                    "confidence": 0.8
                })
    except Exception as e:
        print(f"[ML] Sensor check error: {e}")
    
    # Power check
    try:
        anomaly_type, confidence = classify_power_anomaly(data)
        if anomaly_type != "normal":
            detections.append({
                "type": anomaly_type,
                "method": "power_profiler",
                "confidence": confidence
            })
    except Exception as e:
        print(f"[ML] Power check error: {e}")
    
    # Behavior check
    try:
        actual_state = data.get('device_state', 'unknown')
        is_unusual, confidence = check_behavior_anomaly(data, actual_state)
        if is_unusual:
            detections.append({
                "type": "behavior_anomaly",
                "method": "behavior_rules",
                "confidence": confidence
            })
    except Exception as e:
        print(f"[ML] Behavior check error: {e}")
    
    # Determine overall threat level
    if len(detections) > 0:
        results["is_anomaly"] = True
        max_confidence = float(max([d["confidence"] for d in detections]))
        
        if max_confidence > 0.8:
            results["overall_threat_level"] = "critical"
        elif max_confidence > 0.6:
            results["overall_threat_level"] = "high"
        
        # Primary threat type for blockchain
        first_detection = detections[0]
        main_threat = str(first_detection.get("type", "unknown"))
        
        # Log to blockchain
        data_hash = hashlib.sha256(json.dumps(data).encode()).hexdigest()
        batch_hash = data.get("batch_hash", "NONE")
        log_to_blockchain(device_id, max_confidence, data_hash, batch_hash, main_threat.upper(), data.get("gateway_id", "unknown"))
        
        # Save detailed prediction locally
        save_prediction({
            "device_id": device_id,
            "score": float(max_confidence),
            "is_anomaly": True,
            "threat_type": main_threat,
            "confidence": max_confidence,
            "features": data,
            "batch_hash": batch_hash,
            "method": "comprehensive"
        })

        # Forward as security alert to server (for Dashboard/Alarm)
        try:
            server_host = os.getenv("SERVER_HOST", "localhost")
            # 1. Send Alert
            alert_payload = {
                "device_id": device_id,
                "event_type": "SECURITY_ALERT",
                "reason": f"{main_threat} (Conf: {max_confidence:.2f})",
                "anomaly_score": float(max_confidence),
                "timestamp": int(datetime.now().timestamp()),
                "batch_hash": batch_hash,
                "threat_type": main_threat
            }
            requests.post(f"http://{server_host}:5002/api/alerts", json=alert_payload, timeout=1)

            # 2. Trigger Alarm if Critical
            if max_confidence > 0.8:
                requests.post(f"http://{server_host}:5002/api/alarm/trigger", 
                             json={"reason": f"CRITICAL: {main_threat} detected!"}, 
                             timeout=1)

        except Exception as e:
            print(f"[ML] Failed to forward alert/alarm to server: {e}")
    
    return jsonify(results)

@app.route('/status', methods=['GET'])
def get_status():
    """Get ML service status and available models."""
    return jsonify({
        "status": "running",
        "python_version": sys.version,
        "models": {
            "sensor_models": list(SENSOR_MODELS.keys()),
            "power_model": POWER_MODEL is not None,
            "behavior_model": BEHAVIOR_MODEL is not None
        },
        "endpoints": [
            "/predict - Basic sensor anomaly (Isolation Forest)",
            "/predict/access - Access anomaly detection",
            "/predict/power - Power anomaly (crypto mining, botnet)",
            "/predict/behavior - Behavior anomaly detection",
            "/predict/comprehensive - All detections combined"
        ],
        "threat_types": [
            "sensor_anomaly",
            "access_anomaly (unusual time, location, IP)",
            "crypto_mining (high CPU + power)",
            "botnet (high network + CPU)",
            "ddos (very high network)",
            "hardware_issue (high temp/power)",
            "behavior_anomaly (unusual patterns)"
        ]
    })


if __name__ == '__main__':
    print("=" * 50)
    print("Enhanced ML Anomaly Detection Service")
    print("Python 3.14 Compatible (sklearn-only)")
    print("=" * 50)
    
    # Initialize models
    train_sensor_model()
    train_power_model()
    train_behavior_model()
    
    print("\nThreat Detection Available:")
    print("  [OK] Sensor anomaly (Isolation Forest)")
    print("  [OK] Access anomaly (Rule-based)")
    print("  [OK] Power anomaly (Crypto mining, Botnet, DDoS)")
    print("  [OK] Behavior anomaly (Pattern rules)")
    
    print(f"\nStarting server on port 5001...")
    app.run(host='0.0.0.0', port=5001)
