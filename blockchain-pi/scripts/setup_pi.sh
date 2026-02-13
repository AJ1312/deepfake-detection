#!/usr/bin/env bash
# ============================================================
# Raspberry Pi Deepfake Detection Node — Setup Script
# ============================================================
# Tested on: Raspberry Pi 4 (4GB/8GB) with Raspberry Pi OS (64-bit)
# Usage: sudo bash setup_pi.sh
# ============================================================

set -euo pipefail

INSTALL_DIR="/opt/deepfake-pi"
DATA_DIR="/var/lib/deepfake-pi"
LOG_DIR="/var/log/deepfake-pi"
SERVICE_USER="deepfake"

echo "============================================"
echo "  Deepfake Detection Pi Node — Setup"
echo "============================================"

# ---- Check root ----
if [[ $EUID -ne 0 ]]; then
   echo "ERROR: Run with sudo"
   exit 1
fi

# ---- Check architecture ----
ARCH=$(uname -m)
echo "[1/10] Architecture: $ARCH"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "armv7l" ]]; then
    echo "WARNING: Not running on ARM. Some optimisations may not apply."
fi

# ---- System updates ----
echo "[2/10] Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq

# ---- Install system dependencies ----
echo "[3/10] Installing system dependencies..."
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    redis-server \
    libopencv-dev \
    libatlas-base-dev \
    libhdf5-dev \
    libjasper-dev \
    libqtgui4 libqt4-test \
    ffmpeg \
    git curl jq \
    build-essential

# ---- Enable Redis ----
echo "[4/10] Configuring Redis..."
systemctl enable redis-server
systemctl start redis-server

# ---- Create service user ----
echo "[5/10] Creating service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --create-home --shell /bin/bash "$SERVICE_USER"
fi

# ---- Create directories ----
echo "[6/10] Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR/offline_queue"
mkdir -p "$DATA_DIR/keystore"
mkdir -p "$LOG_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" "$LOG_DIR"

# ---- Copy project files ----
echo "[7/10] Installing application..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
# Also copy shared modules
cp -r "$SCRIPT_DIR/../shared" "$INSTALL_DIR/shared" 2>/dev/null || true

# ---- Create virtual environment ----
echo "[8/10] Setting up Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
source "$INSTALL_DIR/venv/bin/activate"
pip install --upgrade pip setuptools wheel
pip install -r "$INSTALL_DIR/requirements-pi.txt"

# ---- Generate wallet (if not exists) ----
echo "[9/10] Checking wallet..."
if [ ! -f "$DATA_DIR/keystore/Pi-Node-001.json" ]; then
    echo "Generating new wallet..."
    python3 -c "
import sys; sys.path.insert(0, '$INSTALL_DIR')
from shared.alerts.crypto_authenticator import CryptoAuthenticator
auth = CryptoAuthenticator('$DATA_DIR/keystore')
identity = auth.generate_wallet('Pi-Node-001', 'pi')
print(f'Wallet address: {identity.address}')
print('IMPORTANT: Fund this wallet with MATIC for gas fees!')
print(f'Save this address and add it to your .env file.')
"
else
    echo "Wallet already exists."
fi

# ---- Install systemd service ----
echo "[10/10] Installing systemd service..."
cat > /etc/systemd/system/deepfake-pi.service <<EOF
[Unit]
Description=Deepfake Detection Pi Node
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=-$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python -m src.pi_node
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Resource limits for Pi
MemoryMax=1G
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable deepfake-pi.service

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Copy .env file:  cp $INSTALL_DIR/.env.example $INSTALL_DIR/.env"
echo "  2. Edit .env:       nano $INSTALL_DIR/.env"
echo "  3. Add RPC URL and contract addresses"
echo "  4. Fund the wallet with MATIC"
echo "  5. Start service:   sudo systemctl start deepfake-pi"
echo "  6. View logs:       sudo journalctl -u deepfake-pi -f"
echo ""
