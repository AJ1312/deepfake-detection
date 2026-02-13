#!/usr/bin/env bash
# =============================================
# Laptop Node — Quick Setup Script
# =============================================
# Works on macOS and Linux
# Usage: bash scripts/setup.sh [host|client|both]

set -euo pipefail

MODE="${1:-both}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "  Deepfake Detection Laptop — Setup"
echo "  Mode: $MODE"
echo "============================================"

cd "$PROJECT_DIR"

# ---- Python venv ----
if [ ! -d "venv" ]; then
    echo "[1/5] Creating Python virtual environment..."
    python3 -m venv venv
else
    echo "[1/5] Virtual environment exists"
fi

source venv/bin/activate
echo "  Python: $(python3 --version)"

# ---- Install dependencies ----
echo "[2/5] Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements-laptop.txt -q

# ---- Install shared module ----
echo "[3/5] Setting up shared blockchain module..."
SHARED_DIR="$(dirname "$PROJECT_DIR")/shared"
if [ -d "$SHARED_DIR" ]; then
    echo "  Found shared/ at $SHARED_DIR"
    # Make it importable
    export PYTHONPATH="${SHARED_DIR}:${PYTHONPATH:-}"
fi

# ---- Create directories ----
echo "[4/5] Creating data directories..."
mkdir -p data/uploads logs

# ---- Environment file ----
if [ ! -f ".env" ]; then
    echo "[5/5] Creating .env from template..."
    cp .env.example .env
    echo "  ⚠️  Edit .env with your credentials before running!"
else
    echo "[5/5] .env already exists"
fi

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""

if [ "$MODE" = "host" ] || [ "$MODE" = "both" ]; then
    echo "  Start HOST:   python run_host.py"
    echo "                 python run_host.py --port 5050 --debug"
fi

if [ "$MODE" = "client" ] || [ "$MODE" = "both" ]; then
    echo "  Start CLIENT:  python run_client.py"
    echo "                 python run_client.py --host 192.168.1.5:5050"
fi

echo ""
echo "  Deploy contracts first: cd ../shared/contracts && npm run deploy:local"
echo ""
