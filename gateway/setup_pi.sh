#!/bin/bash

# IoT Base Station Setup Script for Raspberry Pi
# ----------------------------------------------

echo "🚀 Starting Base Station Setup..."

# 1. Update system
echo "📦 Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Python and dependencies
echo "🐍 Installing Python dependencies..."
sudo apt-get install -y python3-pip python3-venv libatlas-base-dev

# 3. Create virtual environment
if [ ! -d ".venv" ]; then
    echo "🏗️ Creating virtual environment..."
    python3 -m venv .venv
fi

# 4. Install project requirements
echo "📥 Installing Python requirements..."
source .venv/bin/activate
pip install --upgrade pip
pip install -r ../requirements.txt
pip install RPi.GPIO  # Specific to Pi

# 5. Setup environment file
if [ ! -f ".env" ]; then
    echo "📄 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️ Please edit .env with your specific configuration."
fi

# 6. Setup systemd service
echo "🔧 Configuring systemd service..."
SERVICE_FILE="basestation.service"
if [ -f "$SERVICE_FILE" ]; then
    sudo cp $SERVICE_FILE /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable basestation
    echo "✅ Service 'basestation' enabled. Use 'sudo systemctl start basestation' to run."
fi

echo "✨ Setup complete! Base Station is ready."
echo "💡 To run manually: source .venv/bin/activate && python gateway_service.py"
