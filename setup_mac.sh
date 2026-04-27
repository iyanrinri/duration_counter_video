#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================"
echo "🛠️  Duration Counter - macOS Setup"
echo "========================================"

# Check for python3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed. Please install Python 3 first."
    exit 1
fi

# Remove old venv if exists
if [ -d "venv" ]; then
    echo "♻️  Removing old virtual environment..."
    rm -rf venv
fi

# Create new venv
echo "🏗️  Creating new virtual environment..."
python3 -m venv venv

# Activate venv
echo "🔌 Activating venv..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📦 Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "⚠️  requirements.txt not found. Installing defaults..."
    pip install Flask psutil python-dotenv
fi

echo ""
echo "========================================"
echo "✅ Setup complete!"
echo "========================================"
echo ""
echo "🚀 To run the application:"
echo "   ./run_app_mac.sh"
echo ""
echo "🛰️  To run the background monitor:"
echo "   source venv/bin/activate && python3 monitor_drives.py"
echo ""
