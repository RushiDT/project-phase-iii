"""
Enhanced ML Anomaly Detection Service
Uses scikit-learn based models compatible with Python 3.14.
Provides multiple threat detection methods without TensorFlow dependency.
"""

import json
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

app = Flask(__name__)
CORS(app)

# Configuration
SERVER_LOGS_PATH = os.path.join("..", "server", "server_logs.json")

# Model instances
SENSOR_MODEL = None  # Isolation Forest for sensor anomalies
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

def load_data():
    """Loads logs from the server storage."""
    if not os.path.exists(SERVER_LOGS_PATH):
        return pd.DataFrame()
    
    try:
        with open(SERVER_LOGS_PATH, 'r') as f:
            data = json.load(f)
        
        if not data:
            return pd.DataFrame()

        flattened_data = []
        for entry in data:
            flat = {
                "temperature": entry["sensors"]["temperature"],
                "humidity": entry["sensors"]["humidity"],
                "vibration": entry["sensors"]["vibration"],
                "cpu_usage": entry["system"]["cpu_usage"],
                "battery_level": entry["system"]["battery_level"]
            }
            flattened_data.append(flat)
            
        return pd.DataFrame(flattened_data)
    except Exception as e:
        print(f"Error loading data: {e}")
        return pd.DataFrame()

def train_sensor_model():
    """Trains the Isolation Forest for sensor anomaly detection."""
    global SENSOR_MODEL
    df = load_data()
    
    if df.empty or len(df) < 10:
        print("[ML] Not enough data to train sensor model yet.")
        return False
        
    print(f"[ML] Training sensor model on {len(df)} records...")
    SENSOR_MODEL = IsolationForest(contamination=0.05, random_state=42)
    SENSOR_MODEL.fit(df)
    print("[ML] Sensor model trained successfully.")
    return True

def train_power_model():
    """Initialize power anomaly classifier with predefined rules."""
    global POWER_MODEL
    # Since we don't have labeled power data, use rule-based detection
    print("[ML] Power model initialized (rule-based detection)")
    POWER_MODEL = "rule_based"
    return True

def train_behavior_model():
    """Initialize behavior prediction model."""
    global BEHAVIOR_MODEL
    # Since we don't have labeled behavior data, use rule-based detection
    print("[ML] Behavior model initialized (rule-based detection)")
    BEHAVIOR_MODEL = "rule_based"
    return True

def classify_power_anomaly(data):
    """Rule-based power anomaly classification."""
    cpu_usage = data.get("cpu_usage", data.get("system", {}).get("cpu_usage", 0))
    power_watts = data.get("power_watts", 0)
    network_activity = data.get("network_activity", 0)
    temperature = data.get("temperature", data.get("sensors", {}).get("temperature", 25))
    
    # Detection rules
    if cpu_usage > 90 and power_watts > 100:
        return "crypto_mining", 0.9
    elif network_activity > 150 and cpu_usage > 70:
        return "botnet", 0.85
    elif network_activity > 200:
        return "ddos", 0.8
    elif temperature > 60:
        return "hardware_issue", 0.75
    elif power_watts > 80 and cpu_usage < 20:
        return "hardware_issue", 0.6
    else:
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

def log_to_blockchain(device_id, score, data_hash, batch_hash="NONE", event_type="ANOMALY"):
    """Log anomaly to blockchain with batch verification hash."""
    try:
        blockchain_path = os.path.join(os.path.dirname(__file__), '..', 'blockchain')
        sys.path.insert(0, blockchain_path)
        from deploy_and_interact import log_anomaly
        log_anomaly(device_id, score, data_hash, batch_hash, event_type)
        print(f"[ML] Logged to blockchain: {event_type} for {device_id} (Batch: {batch_hash[:8]})")
    except Exception as e:
        print(f"[ML] Failed to log to Blockchain: {e}")


# ==================== API ENDPOINTS ====================

@app.route('/train', methods=['POST'])
def trigger_train():
    """Train all models."""
    sensor_ok = train_sensor_model()
    train_power_model()
    train_behavior_model()
    
    if sensor_ok:
        return jsonify({"status": "trained", "models": ["sensor", "power", "behavior"]}), 200
    else:
        return jsonify({"status": "partial", "reason": "Not enough sensor data"}), 200

@app.route('/predict', methods=['POST'])
def predict_basic():
    """Basic prediction using Isolation Forest (original endpoint)."""
    global SENSOR_MODEL
    
    if SENSOR_MODEL is None:
        if not train_sensor_model():
            data = request.json
            temp = data.get("sensors", {}).get("temperature", 0)
            batch_hash = data.get("batch_hash", "NONE")
            is_anomaly = temp > 45
            if is_anomaly:
                data_hash = hashlib.sha256(json.dumps(data).encode()).hexdigest()
                log_to_blockchain(data.get("device_id", "unknown"), -1.0, data_hash, batch_hash, "TEMP_SPIKE")
            
            return jsonify({
                "is_anomaly": is_anomaly,
                "score": -1.0 if is_anomaly else 1.0, 
                "method": "fallback_threshold"
            })

    try:
        entry = request.json
        features = [[
            entry["sensors"]["temperature"],
            entry["sensors"]["humidity"],
            entry["sensors"]["vibration"],
            entry["system"]["cpu_usage"],
            entry["system"]["battery_level"]
        ]]
        
        prediction = SENSOR_MODEL.predict(features)[0]
        score = SENSOR_MODEL.decision_function(features)[0]
        is_anomaly = prediction == -1
        
        if is_anomaly:
            print(f"[ML] ANOMALY DETECTED! Score: {score:.4f}")
            data_hash = hashlib.sha256(json.dumps(features).encode()).hexdigest()
            batch_hash = entry.get("batch_hash", "NONE")
            log_to_blockchain(entry.get("device_id", "unknown"), score, data_hash, batch_hash)
        
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
    if SENSOR_MODEL is None:
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
                            confidence, data_hash, batch_hash, "ACCESS_ANOMALY")
        
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
            log_to_blockchain(device_id, confidence, data_hash, batch_hash, anomaly_type.upper())
        
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
    
    results = {
        "device_id": device_id,
        "timestamp": datetime.now().isoformat(),
        "detections": [],
        "overall_threat_level": "normal",
        "is_anomaly": False
    }
    
    # Sensor check
    try:
        if SENSOR_MODEL is not None:
            features = [[
                data.get("sensors", {}).get("temperature", 25),
                data.get("sensors", {}).get("humidity", 50),
                data.get("sensors", {}).get("vibration", 0),
                data.get("system", {}).get("cpu_usage", 20),
                data.get("system", {}).get("battery_level", 100)
            ]]
            prediction = SENSOR_MODEL.predict(features)[0]
            if prediction == -1:
                results["detections"].append({
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
            results["detections"].append({
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
            results["detections"].append({
                "type": "behavior_anomaly",
                "method": "behavior_rules",
                "confidence": confidence
            })
    except Exception as e:
        print(f"[ML] Behavior check error: {e}")
    
    # Determine overall threat level
    if len(results["detections"]) > 0:
        results["is_anomaly"] = True
        max_confidence = max([d["confidence"] for d in results["detections"]])
        
        if max_confidence > 0.8:
            results["overall_threat_level"] = "critical"
        elif max_confidence > 0.6:
            results["overall_threat_level"] = "high"
        elif max_confidence > 0.4:
            results["overall_threat_level"] = "medium"
        else:
            results["overall_threat_level"] = "low"
        
        # Log to blockchain
        data_hash = hashlib.sha256(json.dumps(data).encode()).hexdigest()
        batch_hash = data.get("batch_hash", "NONE")
        threat_type = results["detections"][0]["type"].upper()
        log_to_blockchain(device_id, max_confidence, data_hash, batch_hash, threat_type)
    
    return jsonify(results)

@app.route('/status', methods=['GET'])
def get_status():
    """Get ML service status and available models."""
    return jsonify({
        "status": "running",
        "python_version": sys.version,
        "models": {
            "sensor_model": SENSOR_MODEL is not None,
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
    print("  ✓ Sensor anomaly (Isolation Forest)")
    print("  ✓ Access anomaly (Rule-based)")
    print("  ✓ Power anomaly (Crypto mining, Botnet, DDoS)")
    print("  ✓ Behavior anomaly (Pattern rules)")
    
    print(f"\nStarting server on port 5001...")
    app.run(host='0.0.0.0', port=5001)
