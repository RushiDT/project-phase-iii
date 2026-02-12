# PRD: End-to-End IoT Data Flow & Architecture

## Introduction

This PRD defines the complete data flow for the IoT Device Security System. The system monitors IoT devices (ESP32/ESP8266), transmits sensor data via a Gateway to a Central Server, analyzes it for security threats using an ML Engine, logs critical events to a Blockchain, and visualizes the system state on a Dashboard.

**Note:** This PRD documents the intended architecture to guide refactoring and debugging efforts.

## Goals

- **Reliable Data Ingestion:** Ensure sensor data from ESP devices reaches the server without loss.
- **Real-time Anomaly Detection:** Process incoming data through the ML Engine to detect potential security threats (e.g., physical tampering, network attacks).
- **Immutable Logging:** Securely log high-severity anomalies to the blockchain for audit trails.
- **Actionable Visualization:** Display real-time device status and alerts on the dashboard.
- **Device Control:** Enable remote control (e.g., locking/unlocking) from the dashboard back to the device.

## User Stories

### US-001: Device Data Transmission
**Description:** As a system administrator, I want IoT devices to send sensor data (temperature, motion, proximity) at regular intervals so that I have visibility into their physical state.
**Acceptance Criteria:**
- [ ] ESP32/ESP8266 connects to Gateway Wi-Fi.
- [ ] Devices publish JSON payload to MQTT topic `iot/sensors`.
- [ ] Gateway forwards MQTT messages to Central Server API.
- [ ] Payload includes: `device_id`, `timestamp`, `sensor_values`.

### US-002: Central Server Processing & ML Analysis
**Description:** As a security analyst, I want the server to process incoming data and detect anomalies immediately.
**Acceptance Criteria:**
- [ ] Server receives data from Gateway.
- [ ] Server forwards data point to ML Engine (`ml-engine/`).
- [ ] ML Engine returns `anomaly_score` and `status` ("Normal" or "Anomaly").
- [ ] Server stores raw data and result in local JSON logs (per device).

### US-003: Blockchain Evidence Logging
**Description:** As an auditor, I want critical security alerts to be logged to the blockchain so that they cannot be tampered with.
**Acceptance Criteria:**
- [ ] If `status` is "Anomaly", Server triggers Blockchain Writer.
- [ ] Data hash and metadata written to Smart Contract.
- [ ] Transaction ID stored in local logs for reference.

### US-004: Real-time Dashboard Updates
**Description:** As a user, I want to see the live status of my devices on a dashboard.
**Acceptance Criteria:**
- [ ] Dashboard polls Server or receives Push notifications (WebSocket) for updates.
- [ ] UI displays current sensor values and "Safe/Danger" status.
- [ ] Alerts are visually distinct (Red/Blinking).
- [ ] Verify in browser using dev-browser skill.

### US-005: Remote Device Control
**Description:** As a user, I want to remotely trigger actions on the device (e.g., "Activate Defense") from the dashboard.
**Acceptance Criteria:**
- [ ] User clicks "Activate" on Dashboard.
- [ ] Dashboard sends command to Server.
- [ ] Server publishes command to MQTT topic `iot/control/{device_id}`.
- [ ] Device receives message and executes physical action (e.g., LED on, Servo move).

## Functional Requirements

### Data Model
- **Sensor Data:**
  ```json
  {
    "device_id": "esp32_01",
    "timestamp": "2023-10-27T10:00:00Z",
    "sensors": {
      "temp": 25.5,
      "motion": true
    }
  }
  ```
- **Anomaly Result:**
  ```json
  {
    "is_anomaly": true,
    "confidence": 0.95,
    "type": "Physical Tampering"
  }
  ```

### Components
1. **IoT Device:** ESP32/ESP8266 Clean C++ Implementation.
2. **Gateway:** Python script or lightweight broker acting as a bridge.
3. **Server:** Python (Flask/FastAPI) handling API and orchestration.
4. **ML Engine:** Python (Scikit-learn/TensorFlow) model for inference.
5. **Blockchain:** Solidity Smart Contract + Web3.py interface.
6. **Dashboard:** React Frontend.

## Non-Goals
- Video streaming or heavy media processing.
- Multi-tenant cloud architecture (Local/Edge focused).
- Battery optimization (assumes powered devices for now).

## Technical Considerations
- **Latency:** Critical for "Remote Control" (US-005). MQTT QoS 0 or 1 preferred.
- **Failover:** If Blockchain is unreachable, queue logs locally and retry.
- **Security:** Basic auth for API endpoints.

## Success Metrics
- **End-to-End Latency:** < 2 seconds from Device Sensor -> Dashboard Update.
- **Detection Rate:** > 90% accuracy for simulated physical attacks.
- **System Uptime:** 99% availability during testing.

## Open Questions
- What is the exact schema for the Smart Contract?
- How do we handle device disconnected states on the dashboard?
