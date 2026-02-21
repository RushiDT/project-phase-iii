#!/bin/bash
# ============================================
# IoT Base Station – Raspberry Pi Launcher
# ============================================
# Usage: bash start_pi.sh
# Run from the project root directory

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
GATEWAY_DIR="$PROJECT_DIR/gateway"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     🚀 IoT Base Station – Starting Up...        ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ---- Detect Pi ----
PI_MODEL="Unknown"
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(cat /proc/device-tree/model | tr -d '\0')
fi
PI_IP=$(hostname -I | awk '{print $1}')
echo "📟 $PI_MODEL"
echo "🌐 IP: $PI_IP"

# ---- Load .env ----
if [ -f "$GATEWAY_DIR/.env" ]; then
    echo "📄 Loading config from gateway/.env"
    set -a
    source "$GATEWAY_DIR/.env"
    set +a
else
    echo "⚠  No .env found! Using defaults."
    echo "   Run 'cp gateway/.env.example gateway/.env' and edit it."
    export SERVER_HOST="192.168.1.121"
    export MQTT_BROKER="localhost"
fi

# ---- Step 1: Check Mosquitto MQTT Broker ----
echo ""
echo "[1/4] 📡 Checking MQTT Broker..."
if systemctl is-active --quiet mosquitto 2>/dev/null; then
    echo "  ✓ Mosquitto is running"
else
    echo "  ⚠ Mosquitto is not running. Attempting to start..."
    sudo systemctl start mosquitto 2>/dev/null || true
    sleep 2
    if systemctl is-active --quiet mosquitto 2>/dev/null; then
        echo "  ✓ Mosquitto started successfully"
    else
        echo "  ❌ Mosquitto failed to start!"
        echo "     Run 'bash gateway/install_mosquitto.sh' to install it."
    fi
fi

# ---- Step 2: Activate Virtual Environment ----
echo ""
echo "[2/4] 🐍 Activating Python environment..."
if [ -d "$GATEWAY_DIR/.venv" ]; then
    source "$GATEWAY_DIR/.venv/bin/activate"
    echo "  ✓ Virtual environment activated"
else
    echo "  ❌ No .venv found! Run 'bash gateway/setup_pi.sh' first."
    exit 1
fi

# ---- Step 3: Connectivity Check ----
echo ""
echo "[3/4] 🔍 Checking connectivity..."

# Check server
SERVER_URL="http://${SERVER_HOST}:5002/api/logs"
if curl -s --connect-timeout 3 "$SERVER_URL" > /dev/null 2>&1; then
    echo "  ✓ Central Server at ${SERVER_HOST}:5002 is reachable"
else
    echo "  ⚠ Central Server at ${SERVER_HOST}:5002 is NOT reachable"
    echo "    Gateway will queue batches locally until server comes online."
fi

# Check MQTT
MQTT_HOST="${MQTT_BROKER:-localhost}"
if mosquitto_sub -h "$MQTT_HOST" -u "${MQTT_USER:-admin}" -P "${MQTT_PASSWORD:-password123}" -t 'test' -C 1 -W 2 > /dev/null 2>&1; then
    echo "  ✓ MQTT broker at $MQTT_HOST:1883 is accepting connections"
else
    # Try without auth (some setups)
    if mosquitto_sub -h "$MQTT_HOST" -t 'test' -C 1 -W 2 > /dev/null 2>&1; then
        echo "  ✓ MQTT broker at $MQTT_HOST:1883 is running (no auth)"
    else
        echo "  ⚠ MQTT broker at $MQTT_HOST:1883 may not be ready"
    fi
fi

# ---- Step 4: Launch Gateway ----
echo ""
echo "[4/4] 🚀 Starting Gateway Service..."
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║         BASE STATION STATUS                     ║"
echo "╠══════════════════════════════════════════════════╣"
echo "  📟 Device:     $PI_MODEL"
echo "  🌐 IP:         $PI_IP"
echo "  📡 MQTT:       ${MQTT_HOST}:1883"
echo "  🖥️  Server:     http://${SERVER_HOST}:5002"
echo "  🚪 Gateway:    http://${PI_IP}:8090"
echo "  🏥 Health:     http://${PI_IP}:8090/pi/health"
echo "╠══════════════════════════════════════════════════╣"
echo "  Press Ctrl+C to stop the base station."
echo "╚══════════════════════════════════════════════════╝"
echo ""

cd "$GATEWAY_DIR"
python3 gateway_service.py
