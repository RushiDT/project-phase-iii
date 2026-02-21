#!/bin/bash
# ============================================
# Mosquitto MQTT Broker Installer for Pi
# ============================================
# Usage: sudo bash install_mosquitto.sh
# Run from the gateway/ directory

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF_SRC="$SCRIPT_DIR/mosquitto_pi.conf"

echo "🔧 Installing Mosquitto MQTT Broker..."
echo "======================================="

# 1. Install Mosquitto
echo ""
echo "[1/5] Installing mosquitto packages..."
sudo apt-get update -qq
sudo apt-get install -y mosquitto mosquitto-clients

# 2. Load credentials from .env
MQTT_USER="admin"
MQTT_PASSWORD="password123"

if [ -f "$SCRIPT_DIR/.env" ]; then
    source_user=$(grep -oP '^MQTT_USER=\K.*' "$SCRIPT_DIR/.env" 2>/dev/null || true)
    source_pass=$(grep -oP '^MQTT_PASSWORD=\K.*' "$SCRIPT_DIR/.env" 2>/dev/null || true)
    [ -n "$source_user" ] && MQTT_USER="$source_user"
    [ -n "$source_pass" ] && MQTT_PASSWORD="$source_pass"
elif [ -f "$SCRIPT_DIR/.env.example" ]; then
    source_user=$(grep -oP '^MQTT_USER=\K.*' "$SCRIPT_DIR/.env.example" 2>/dev/null || true)
    source_pass=$(grep -oP '^MQTT_PASSWORD=\K.*' "$SCRIPT_DIR/.env.example" 2>/dev/null || true)
    [ -n "$source_user" ] && MQTT_USER="$source_user"
    [ -n "$source_pass" ] && MQTT_PASSWORD="$source_pass"
fi

# 3. Create password file
echo ""
echo "[2/5] Creating MQTT credentials (user: $MQTT_USER)..."
sudo mosquitto_passwd -c -b /etc/mosquitto/passwd "$MQTT_USER" "$MQTT_PASSWORD"

# 4. Deploy config
echo ""
echo "[3/5] Deploying Mosquitto configuration..."
if [ -f "$CONF_SRC" ]; then
    sudo cp "$CONF_SRC" /etc/mosquitto/conf.d/iot_basestation.conf
    echo "  ✓ Config deployed to /etc/mosquitto/conf.d/iot_basestation.conf"
else
    echo "  ⚠ Config file not found at $CONF_SRC, using defaults."
fi

# 5. Create log directory
echo ""
echo "[4/5] Setting up log directory..."
sudo mkdir -p /var/log/mosquitto
sudo chown mosquitto:mosquitto /var/log/mosquitto

# 6. Enable and restart
echo ""
echo "[5/5] Enabling and starting Mosquitto service..."
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
sleep 2

# Verify
if systemctl is-active --quiet mosquitto; then
    echo ""
    echo "============================================"
    echo "  ✅ Mosquitto MQTT Broker is RUNNING"
    echo "============================================"
    echo "  Port:     1883"
    echo "  User:     $MQTT_USER"
    echo "  Config:   /etc/mosquitto/conf.d/iot_basestation.conf"
    echo "  Logs:     /var/log/mosquitto/mosquitto.log"
    echo ""
    echo "  Test with:"
    echo "    mosquitto_sub -h localhost -t 'test/#' -u $MQTT_USER -P $MQTT_PASSWORD"
    echo "    mosquitto_pub -h localhost -t 'test/hello' -m 'Hello Pi!' -u $MQTT_USER -P $MQTT_PASSWORD"
    echo ""
else
    echo ""
    echo "  ❌ Mosquitto failed to start. Check: sudo journalctl -u mosquitto"
fi
