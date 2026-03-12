#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  VR Classroom Control Panel"
echo "============================================"
echo

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found! Install Python 3.10+"
    exit 1
fi

# Create venv if needed
if [ ! -d "App/venv" ]; then
    echo "[SETUP] Creating virtual environment..."
    python3 -m venv App/venv
fi

echo "[SETUP] Activating virtual environment..."
source App/venv/bin/activate

echo "[SETUP] Installing/updating dependencies..."
pip install -q -r App/requirements.txt

# Build frontend if dist doesn't exist
if [ ! -d "App/frontend/dist" ]; then
    echo "[SETUP] Building frontend..."
    if command -v npm &>/dev/null; then
        cd App/frontend
        npm install
        npm run build
        cd ../..
    else
        echo "[WARNING] npm not found. Frontend must be built manually."
        echo "Install Node.js from https://nodejs.org"
    fi
fi

echo
echo "[START] Starting server..."
echo "[INFO]  Open http://localhost:8000 in your browser"
echo "[INFO]  Press Ctrl+C to stop"
echo

cd App
python3 run.py
