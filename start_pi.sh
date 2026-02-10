#!/bin/bash
# Raspberry Pi / Base Station Launcher
# ------------------------------------

# 1. Load configuration from .env if it exists
if [ -f "gateway/.env" ]; then
    echo "📄 Loading configuration from gateway/.env"
    export $(grep -v '^#' gateway/.env | xargs)
else
    # Fallback/Default values (Update these to match your network!)
    export SERVER_HOST="192.168.1.121"  # Laptop IP
    export MQTT_BROKER="localhost"      # Pi usually runs its own broker
fi

echo "🚀 Starting IoT Base Station (Gateway)..."
echo "   Pointing to Server at: $SERVER_HOST"

# 2. Start Gateway
cd gateway
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

python3 gateway_service.py
# If you want to run it in background, use:
# python3 gateway_service.py &
# GATEWAY_PID=$!
# echo "   [✓] Gateway started (PID: $GATEWAY_PID)"
