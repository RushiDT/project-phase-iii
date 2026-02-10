# IoT Anomaly Detection & Security System

This project implements a multi-layered security framework for IoT devices, using Edge Computing, Machine Learning, and Blockchain technology.

## 🏗️ System Architecture (8-Point Specification)

### 1. IoT Devices (ESP32 / ESP8266)
- **Function**: Collect sensor data (temperature, humidity, motion, light, etc.) and generate operational logs periodically.
- **Metadata**: Each packet includes `device_id`, `sequence_no`, `cpu_usage`, `battery_level`, and `timestamp`.
- **Output**: signed Raw JSON logs.

### 2. Communication Layer (MQTT)
- **Protocol**: Messages are published to an MQTT broker (topic: `iot/logs`).
- **Format**: Lightweight JSON packets for low-latency transmission.

### 3. Base Station / Gateway (Raspberry Pi / PC)
- **Edge Logic**: Responsible for MQTT subscription, schema validation, sanity checks, and **replay protection** via sequence numbers.
- **Efficiency**: Buffers and batches logs before forwarding to the server via HTTPS/REST.

### 4. Central Server API (Node.js / Express)
- **Orchestration**: Receives batches, forwards to storage, and triggers the ML engine for real-time detection.
- **Security**: Generates **SHA-256 hashes** of validated batches before committing to the blockchain.

### 5. Server Storage (JSONL / Database)
- **Persistence**: Stores `server_logs.jsonl` (raw logs) and batch history in a dedicated off-chain layer.
- **Scalability**: Keeps high-volume raw data off-chain for performance.

### 6. ML Engine (Python Anomaly Detection)
- **Analysis**: Performs feature extraction and runs pretrained models (Isolation Forest/Random Forest).
- **Outcomes**: Produces anomaly labels (normal/anomalous) and confidence scores.

### 7. Blockchain Network (Ethereum / Ganache)
- **Immutable Audit Ledger**: Acts as a permanent "Cyber Incident Record System". Stores critical verified metadata: `device_id`, `gateway_id`, `timestamp`, `anomaly_score`, and `batch_hash`.
- **Device Trust Management**: Maintains on-chain reputation for every device. Trust scores are dynamically adjusted based on security events (e.g., -20 for security alerts, +1 for successful heartbeats).
- **Consensus-Backed Control**: Device control commands are vetted against these on-chain trust scores, preventing compromised devices from being manipulated.

### 8. Monitoring Dashboard (React UI)
- **Visualization**: Shows real-time logs, anomaly alerts, confidence scores, and device trust levels.
- **Verification**: Links dashboard alerts directly to Blockchain transaction hashes for auditability.

---

## 🚀 Quick Start
- **Server Side**: Run `python start_system.py`
- **Edge Side**: Run `./start_pi.sh` (on Raspberry Pi)