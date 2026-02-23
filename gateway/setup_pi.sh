#!/bin/bash
# ============================================
# IoT Base Station – Raspberry Pi 4 Setup
# ============================================
# Run once on a fresh Pi:  bash setup_pi.sh
# Run from the project root (parent of gateway/)

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
GATEWAY_DIR="$PROJECT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   IoT Security Base Station – Pi 4 Setup        ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Detect Pi model
PI_MODEL="Unknown"
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(cat /proc/device-tree/model | tr -d '\0')
fi
echo "📟 Detected: $PI_MODEL"
echo ""

# ---- Step 1: System Update ----
echo "[1/7] 📦 Updating system packages..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq
echo "  ✓ System updated"

# ---- Step 2: Install System Dependencies ----
echo ""
echo "[2/7] 🔧 Installing system dependencies..."
sudo apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    libopenblas-dev \
    mosquitto \
    mosquitto-clients \
    git \
    curl
echo "  ✓ System dependencies installed"

# ---- Step 3: Install & Configure Mosquitto MQTT ----
echo ""
echo "[3/7] 📡 Configuring Mosquitto MQTT Broker..."
if [ -f "$GATEWAY_DIR/install_mosquitto.sh" ]; then
    bash "$GATEWAY_DIR/install_mosquitto.sh"
else
    echo "  ⚠ install_mosquitto.sh not found, configuring basic Mosquitto..."
    sudo systemctl enable mosquitto
    sudo systemctl start mosquitto
fi

# ---- Step 4: Create Python Virtual Environment ----
echo ""
echo "[4/7] 🐍 Setting up Python virtual environment..."
if [ ! -d "$GATEWAY_DIR/.venv" ]; then
    python3 -m venv "$GATEWAY_DIR/.venv"
    echo "  ✓ Virtual environment created"
else
    echo "  ✓ Virtual environment already exists"
fi

# ---- Step 5: Install Python Dependencies ----
echo ""
echo "[5/7] 📥 Installing Python requirements..."
source "$GATEWAY_DIR/.venv/bin/activate"
pip install --upgrade pip -q
if [ -f "$GATEWAY_DIR/requirements_pi.txt" ]; then
    pip install -r "$GATEWAY_DIR/requirements_pi.txt" -q
    echo "  ✓ Pi-specific requirements installed"
else
    pip install flask flask-cors paho-mqtt requests python-dotenv RPi.GPIO psutil -q
    echo "  ✓ Base requirements installed (no requirements_pi.txt found)"
fi
deactivate

# ---- Step 6: Setup Environment File ----
echo ""
echo "[6/7] 📄 Setting up environment configuration..."
if [ ! -f "$GATEWAY_DIR/.env" ]; then
    if [ -f "$GATEWAY_DIR/.env.example" ]; then
        cp "$GATEWAY_DIR/.env.example" "$GATEWAY_DIR/.env"
        echo "  ✓ Created .env from .env.example"
        echo "  ⚠ IMPORTANT: Edit $GATEWAY_DIR/.env with your network settings!"
    else
        echo "  ⚠ No .env.example found. Please create $GATEWAY_DIR/.env manually."
    fi
else
    echo "  ✓ .env file already exists"
fi

# ---- Step 7: Setup Systemd Service ----
echo ""
echo "[7/7] ⚙️  Configuring systemd service..."
SERVICE_FILE="$GATEWAY_DIR/basestation.service"
if [ -f "$SERVICE_FILE" ]; then
    sudo cp "$SERVICE_FILE" /etc/systemd/system/basestation.service
    sudo systemctl daemon-reload
    sudo systemctl enable basestation
    echo "  ✓ Service 'basestation' enabled (starts on boot)"
    echo "  💡 Start now with: sudo systemctl start basestation"
    echo "  💡 View logs with: sudo journalctl -u basestation -f"
else
    echo "  ⚠ Service file not found at $SERVICE_FILE"
fi

# ---- Final Summary ----
PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║           ✅  SETUP COMPLETE!                   ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "  📟 Device:     $PI_MODEL"
echo "  🌐 IP Address: $PI_IP"
echo "  📡 MQTT:       Port 1883"
echo "  🚪 Gateway:    Port 8090"
echo "║                                                  ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Next Steps:                                     ║"
echo "║                                                  ║"
echo "  1. Edit gateway/.env with your SERVER_HOST IP"
echo "  2. Run: bash start_pi.sh"
echo "  3. On your laptop, run start_system.py and"
echo "     select 'Remote Gateway' with this Pi's IP"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
