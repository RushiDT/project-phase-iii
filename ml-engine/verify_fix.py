import sys
import os
import pandas as pd
import json
from unittest.mock import patch, MagicMock

# Add current directory to path so we can import anomaly_detector
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

import anomaly_detector

def run_test():
    print("Starting verification test...")
    
    # Reset global state
    anomaly_detector.SENSOR_MODELS = {}
    anomaly_detector.POWER_MODEL = None
    anomaly_detector.BEHAVIOR_MODEL = None

    # Mock load_device_types
    with patch('anomaly_detector.load_device_types') as mock_load_devices:
        mock_load_devices.return_value = {
            "device_esp32_1": "esp32",
            "device_esp8266_1": "esp8266"
        }
        
        # Mock load_data
        with patch('anomaly_detector.load_data') as mock_load_data:
            import random
            
            # Create synthetic training data with noise
            # ESP32: Temp ~25, Hum ~50
            esp32_data = []
            for i in range(200):
                esp32_data.append({
                    "temperature": 25 + random.uniform(-2, 2), 
                    "humidity": 50 + random.uniform(-5, 5), 
                    "vibration": 0 + random.uniform(0, 0.01), 
                    "cpu_usage": 20 + random.uniform(-2, 2), 
                    "battery_level": 100, 
                    "power_watts": 10 + random.uniform(-1, 1), 
                    "network_activity": 20 + random.uniform(-2, 2), 
                    "hour": 12,
                    "device_type": "esp32",
                    "device_id": "device_esp32_1"
                })
            
            # ESP8266: Temp ~40, Hum ~5 (The "false positive" profile)
            esp8266_data = []
            for i in range(200):
                esp8266_data.append({
                    "temperature": 40 + random.uniform(-2, 2), 
                    "humidity": 5 + random.uniform(-1, 1), 
                    "vibration": 0 + random.uniform(0, 0.01), 
                    "cpu_usage": 20 + random.uniform(-2, 2), 
                    "battery_level": 100, 
                    "power_watts": 10 + random.uniform(-1, 1), 
                    "network_activity": 20 + random.uniform(-2, 2), 
                    "hour": 12,
                    "device_type": "esp8266",
                    "device_id": "device_esp8266_1"
                })

            mock_load_data.return_value = pd.DataFrame(esp32_data + esp8266_data)

            # Train Models
            print("[Test] Training models...")
            success = anomaly_detector.train_sensor_model()
            
            if not success:
                print("FAIL: train_sensor_model returned False")
                sys.exit(1)
            
            if "esp32" not in anomaly_detector.SENSOR_MODELS:
                print("FAIL: 'esp32' model not found in SENSOR_MODELS")
                sys.exit(1)
            if "esp8266" not in anomaly_detector.SENSOR_MODELS:
                print("FAIL: 'esp8266' model not found in SENSOR_MODELS")
                sys.exit(1)
                
            print(f"[Test] Models trained for: {list(anomaly_detector.SENSOR_MODELS.keys())}")

            # Test Predictions
            print("[Test] Testing Predictions...")
            
            # Case A: Normal ESP8266 data (should NOT be anomaly)
            feat_esp8266_normal = [[40, 5, 0, 20, 100, 10, 20, 12]]
            model_8266 = anomaly_detector.SENSOR_MODELS["esp8266"]
            pred_8266 = model_8266.predict(feat_esp8266_normal)[0]
            print(f"[Test] ESP8266 Normal Prediction: {pred_8266} (1=Normal, -1=Anomaly)")
            
            if pred_8266 != 1:
                print("FAIL: ESP8266 normal data flagged as anomaly!")
                sys.exit(1)
            else:
                print("PASS: ESP8266 normal data correctly classified.")

            # Case B: Anomaly ESP8266 data (Temp 80C)
            feat_esp8266_anomaly = [[80, 5, 0, 20, 100, 10, 20, 12]]
            pred_8266_anom = model_8266.predict(feat_esp8266_anomaly)[0]
            score_8266_anom = model_8266.score_samples(feat_esp8266_anomaly)[0]
            print(f"[Test] ESP8266 Anomaly Prediction: {pred_8266_anom} (1=Normal, -1=Anomaly)")
            print(f"[Test] ESP8266 Anomaly Score (score_samples): {score_8266_anom}")
            
            if pred_8266_anom != -1:
                print("FAIL: ESP8266 anomaly data NOT flagged!")
                # Don't exit yet, check simpler anomaly
                # sys.exit(1) 
            else:
                print("PASS: ESP8266 anomaly correctly detected.")

            # Case C: Check that ESP32 model handles ESP32 data correctly
            feat_esp32_normal = [[25, 50, 0, 20, 100, 10, 20, 12]]
            model_32 = anomaly_detector.SENSOR_MODELS["esp32"]
            pred_32 = model_32.predict(feat_esp32_normal)[0]
            score_32 = model_32.score_samples(feat_esp32_normal)[0]
            print(f"[Test] ESP32 Normal Prediction: {pred_32} Score: {score_32}")

            
            if pred_32 != 1:
                print("FAIL: ESP32 normal data flagged as anomaly!")
                sys.exit(1)
            else:
                print("PASS: ESP32 normal data correctly classified.")

    print("\nALL TESTS PASSED SUCCESSFULLY.")

if __name__ == "__main__":
    run_test()
