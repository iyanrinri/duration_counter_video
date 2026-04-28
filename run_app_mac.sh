#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================"
echo "🚀 Duration Counter - macOS Launcher"
echo "========================================"

if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment not found. Running setup..."
    bash setup_mac.sh
fi

echo "📦 Activating environment..."
source venv/bin/activate

echo "🔍 Checking remote status..."
# Optional: could do a quick curl check here too if desired

echo "🌐 Starting Web Application..."
echo "📍 Access at: http://127.0.0.1:5000"
echo "----------------------------------------"
python3 app.py
