# 🍓 Blockchain Pi Node — Deepfake Detection

Lightweight deepfake detection node designed for **Raspberry Pi 4 (4GB/8GB)**.
Analyzes videos using handcrafted features (no heavy CNN), writes results to
the **Polygon blockchain**, and provides real-time tracking + alerts.

## Architecture

```
┌──────────────────────────────────────────────┐
│            Raspberry Pi 4 Node               │
├──────────────────────────────────────────────┤
│  Video Analyzer  (Optical Flow, FFT, Edge,   │
│                   Color Histogram, Noise)     │
│  ↓                                           │
│  Blockchain Uploader → Polygon (Web3.py)     │
│  ↓                                           │
│  Local Cache (Redis + in-memory fallback)    │
│  ↓                                           │
│  REST API (Flask, port 8080)                 │
│  ↓                                           │
│  Health Monitor (CPU, RAM, Temp)             │
└──────────────────────────────────────────────┘
```

## Features

- **Lightweight Detection**: 5 handcrafted feature extractors (no PyTorch required)
  - Optical flow analysis
  - Color histogram consistency
  - Edge detection patterns
  - Frequency domain (FFT) analysis
  - Noise pattern analysis
- **Blockchain Integration**: All results written to Polygon L2
- **Offline Resilience**: Queue results locally when blockchain is unreachable
- **IP Tracking**: SHA-256 hashed IP tracking + geo-resolution
- **Crypto Alerts**: Signed notifications on deepfake detection
- **Auto-Recovery**: systemd service with auto-restart
- **Low Resource**: Runs within 1GB RAM, 80% CPU cap

## Quick Start

### Prerequisites

- Raspberry Pi 4 (4GB or 8GB recommended)
- Raspberry Pi OS 64-bit
- Internet connection
- Polygon wallet with MATIC for gas fees

### 1. Deploy Smart Contracts

```bash
cd ../shared/contracts
npm install
cp .env.example .env
# Edit .env with your wallet private key and RPC URL
npm run deploy:amoy    # Testnet
# or
npm run deploy:polygon # Mainnet
```

### 2. Setup Pi Node

```bash
# SSH into your Pi
sudo bash scripts/setup_pi.sh
```

This will:
- Install all system dependencies (Python, Redis, OpenCV, FFmpeg)
- Create a dedicated `deepfake` service user
- Set up a Python virtual environment
- Install the systemd service
- Generate a wallet

### 3. Configure

```bash
# Edit the environment file
sudo nano /opt/deepfake-pi/.env

# Required settings:
POLYGON_RPC_URL=https://polygon-amoy.drpc.org
WALLET_PRIVATE_KEY=your_private_key
VIDEO_REGISTRY_ADDRESS=0x...
TRACKING_LEDGER_ADDRESS=0x...
ALERT_MANAGER_ADDRESS=0x...
```

### 4. Start

```bash
# Via systemd (production)
sudo systemctl start deepfake-pi
sudo systemctl status deepfake-pi

# Or manually (development)
cd /opt/deepfake-pi
source venv/bin/activate
python run_pi.py --debug
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/analyze` | Upload and analyze a video |
| GET | `/api/video/<hash>` | Look up a video by hash |
| GET | `/api/video/<hash>/spread` | Get spread events |
| GET | `/api/video/<hash>/alerts` | Get alerts |
| GET | `/api/stats` | Node statistics |
| GET | `/api/health` | Health check |
| GET | `/api/queue/stats` | TX queue status |
| POST | `/api/queue/sync` | Sync offline queue |

### Example: Analyze a Video

```bash
curl -X POST http://pi-node:8080/api/analyze \
  -F "video=@suspicious_video.mp4"
```

Response:
```json
{
  "video_hash": "a1b2c3...",
  "is_deepfake": true,
  "confidence": 0.87,
  "features": {
    "optical_flow": 82,
    "edge_consistency": 91,
    "frequency": 78,
    "color_histogram": 65,
    "noise_pattern": 88
  },
  "blockchain_tx": "queued",
  "processing_time": 4.2
}
```

## Configuration

All configuration is in `config/pi_config.yaml`. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `analysis.frames_to_sample` | 5 | Frames to analyze per video |
| `analysis.confidence_threshold` | 0.65 | Detection threshold |
| `analysis.max_video_size_mb` | 200 | Max upload size |
| `batching.batch_size` | 10 | TX batch size |
| `batching.flush_interval` | 60 | Seconds between flushes |
| `api.port` | 8080 | API port |

## Monitoring

The health endpoint reports:
- CPU usage and temperature
- Memory usage
- Disk space
- Network I/O
- Queue depth and offline items

```bash
curl http://pi-node:8080/api/health
```

## Wallet Management

```bash
# Generate a new wallet
python scripts/generate_wallet.py --name "my-pi-node"

# Show wallet address (without private key)
python scripts/generate_wallet.py --show
```

## Resource Limits

The systemd service enforces:
- **Memory**: 1GB max
- **CPU**: 80% max
- Automatic restart on failure (5-second delay)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| High temperature | Add heatsink/fan, reduce `frames_to_sample` |
| Offline queue growing | Check internet connection, verify RPC URL |
| Out of memory | Reduce `max_video_size_mb`, restart Redis |
| Redis unavailable | Node falls back to in-memory cache automatically |
| Blockchain errors | Check wallet has MATIC, verify contract addresses |

## Directory Structure

```
blockchain-pi/
├── run_pi.py              # Entry point
├── requirements-pi.txt    # Python dependencies
├── .env.example           # Environment template
├── config/
│   └── pi_config.yaml     # Full configuration
├── scripts/
│   ├── setup_pi.sh        # Automated setup
│   └── generate_wallet.py # Wallet management
└── src/
    ├── video_analyzer.py      # Lightweight detection
    ├── blockchain_uploader.py # Blockchain + offline queue
    ├── local_cache.py         # Redis cache
    ├── pi_node.py             # Main orchestrator
    ├── pi_api.py              # Flask REST API
    └── health_check.py        # System monitoring
```
