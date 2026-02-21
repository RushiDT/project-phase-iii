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
- **Server Side (Laptop/PC)**: Run `python start_system.py`
- **Edge Side (Raspberry Pi)**: Run `bash start_pi.sh`

---

## 🍓 Raspberry Pi 4 — Base Station Deployment

The Raspberry Pi 4 Model B serves as the dedicated **Base Station / Gateway** running the MQTT broker, data validation, and batch forwarding.

### Hardware Requirements
| Item | Requirement |
|------|-------------|
| Board | Raspberry Pi 4 Model B (2GB+ RAM) |
| Power | Official USB-C 5V/3A power supply |
| Storage | 16GB+ microSD card (Class 10) |
| Network | Ethernet recommended (WiFi works) |
| OS | Raspberry Pi OS (64-bit Lite recommended) |

### First-Time Setup

```bash
# 1. Clone the repo onto your Pi
git clone <your-repo-url> ~/iot-security
cd ~/iot-security

# 2. Run the one-command setup (installs everything)
bash gateway/setup_pi.sh

# 3. Edit your network configuration
nano gateway/.env
#    → Set SERVER_HOST to your laptop/server IP
#    → Set MQTT credentials

# 4. Start the base station
bash start_pi.sh
```

### What Gets Installed
- **Mosquitto MQTT broker** — runs locally on port 1883 with authentication
- **Python 3 venv** — isolated environment with gateway dependencies
- **systemd service** — auto-start on boot (`basestation.service`)

### Network Configuration

On your **laptop** (running `start_system.py`):
- Select "Remote Gateway" when prompted
- Enter the Pi's IP address (find it with `hostname -I` on the Pi)

On your **Pi** (`gateway/.env`):
- Set `SERVER_HOST` to your laptop's IP
- Set `MQTT_BROKER=localhost`

### Monitoring Endpoints
| Endpoint | Description |
|----------|-------------|
| `http://<pi-ip>:8090/status` | Gateway status, uptime, buffer size |
| `http://<pi-ip>:8090/pi/health` | CPU temp, RAM, disk, system health |

### Service Management
```bash
# Start/stop/restart
sudo systemctl start basestation
sudo systemctl stop basestation
sudo systemctl restart basestation

# View logs
sudo journalctl -u basestation -f

# Check Mosquitto
sudo systemctl status mosquitto
```

### Troubleshooting
| Issue | Solution |
|-------|----------|
| Mosquitto not starting | `sudo journalctl -u mosquitto` for errors |
| Server unreachable | Check `SERVER_HOST` in `.env`, verify laptop firewall |
| MQTT auth failed | Re-run `bash gateway/install_mosquitto.sh` |
| High CPU temp warnings | Ensure proper ventilation or add a heatsink |
| Gateway won't start | Check `bash gateway/setup_pi.sh` ran successfully |