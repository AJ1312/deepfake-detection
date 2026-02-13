# 💻 Blockchain Laptop Node — Deepfake Detection P2P System

Distributed deepfake detection system for **personal laptops** with a
**host + client** architecture. Host runs the full detection pipeline 
(CNN + Gemini), clients auto-discover and connect via mDNS. All results
are written to the **Polygon blockchain** with real-time WebSocket updates.

## Architecture

```
┌─────────────────────────────────────────────┐
│              HOST LAPTOP                     │
│  Full Pipeline (CNN + Gemini + Lip-Sync)    │
│  Polygon Blockchain Writer                   │
│  WebSocket Server (Flask-SocketIO)          │
│  mDNS Service Registration                  │
│  P2P Sync Manager                           │
│  Alert Listener                              │
│  Web Dashboard (port 5050)                  │
└──────────┬──────────────────────┬───────────┘
           │   mDNS Auto-Discovery  │
    ┌──────▼──────┐         ┌──────▼──────┐
    │  CLIENT #1  │         │  CLIENT #2  │
    │  Upload UI  │         │  Upload UI  │
    │  WebSocket  │         │  WebSocket  │
    │  port 5060  │         │  port 5060  │
    └─────────────┘         └─────────────┘
```

## Features

### Host
- **Full Detection Pipeline**: CNN (LipSyncAuthenticityNet) + Google Gemini verification
- **Blockchain Writes**: All results stored on Polygon L2 (~$0.001/tx)
- **WebSocket Broadcasting**: Real-time progress + results to all clients
- **mDNS Registration**: Clients auto-discover the host on the network
- **Result Caching**: PostgreSQL or SQLite for fast lookups
- **P2P Sync**: Bidirectional result sharing with peers
- **Alert System**: Blockchain event listener with multi-channel notifications

### Client
- **Auto-Discovery**: Finds host automatically via mDNS/Zeroconf
- **Video Upload**: Drag-and-drop upload UI
- **Real-Time Updates**: Live detection progress via WebSocket
- **Load Balancing**: Picks best host by latency (supports multiple hosts)
- **Local Cache**: Caches results for offline access
- **Network Map**: Visual topology of all connected nodes

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for smart contracts)
- Redis (optional, for caching)
- PostgreSQL (optional, for host database)

### 1. Deploy Smart Contracts

```bash
cd shared/contracts
npm install
cp .env.example .env
# Edit .env with your wallet and RPC
npx hardhat compile
npm run deploy:amoy       # Testnet
```

### 2. Setup

```bash
cd blockchain-laptop
bash scripts/setup.sh     # Creates venv, installs deps, creates .env
```

### 3. Configure

```bash
# Edit .env with your credentials
nano .env

# Required:
POLYGON_RPC_URL=https://polygon-amoy.drpc.org
WALLET_PRIVATE_KEY=your_key
VIDEO_REGISTRY_ADDRESS=0x...
TRACKING_LEDGER_ADDRESS=0x...
ALERT_MANAGER_ADDRESS=0x...
GEMINI_API_KEY=your_gemini_key    # Host only
```

### 4. Run Host

```bash
source venv/bin/activate
python run_host.py --port 5050
```

The host will:
1. Load the CNN model and Gemini verifier
2. Connect to Polygon blockchain
3. Register itself on the local network via mDNS
4. Start the WebSocket server
5. Open the dashboard at http://localhost:5050

### 5. Run Client (on another laptop)

```bash
source venv/bin/activate
python run_client.py
```

The client will:
1. Auto-discover the host via mDNS
2. Connect via WebSocket
3. Open the upload UI at http://localhost:5060

Or connect to a specific host:
```bash
python run_client.py --host 192.168.1.5:5050
```

## API Endpoints

### Host API (port 5050)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/analyze` | Upload and analyze video |
| GET | `/api/video/<hash>` | Look up detection result |
| GET | `/api/video/<hash>/spread` | Spread events |
| GET | `/api/video/<hash>/alerts` | Video alerts |
| GET | `/api/network/peers` | Connected peers |
| GET | `/api/network/status` | Network status |
| GET | `/api/stats` | Full node stats |
| GET | `/api/health` | Health check |
| POST | `/api/sync/hashes` | Sync hashes (P2P) |
| POST | `/api/sync/result` | Sync result (P2P) |
| POST | `/api/sync/fetch` | Fetch results (P2P) |
| GET | `/api/queue/stats` | TX queue stats |
| POST | `/api/queue/retry` | Retry failed TXs |

### Client API (port 5060)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/analyze` | Upload → routes to host |
| GET | `/api/video/<hash>` | Look up (cache → host) |
| GET | `/api/host` | Current host status |
| POST | `/api/host/connect` | Manual host connect |
| POST | `/api/hosts/discover` | Trigger discovery |
| GET | `/api/cache` | Cached results |
| POST | `/api/cache/clear` | Clear local cache |
| GET | `/api/stats` | Client stats |
| GET | `/api/health` | Health check |

## Web UI

### Host Dashboard (`http://host:5050`)
- Live detection feed with real-time WebSocket updates
- Video upload with drag-and-drop
- Connected peers table
- Alert feed
- Detection stats

### Client Upload (`http://client:5060`)
- Video upload with progress tracking
- Detection result display (verdict, confidence, scores)
- Host connection status
- Manual host connection

### Network Map (`http://client:5060/network`)
- Visual peer topology (SVG)
- Host discovery
- Latency information
- Connect buttons

## WebSocket Events

### Client Subscribes To:
| Room | Events |
|------|--------|
| `detection` | `detection_started`, `detection_progress`, `detection_complete` |
| `alerts` | `new_alert`, `alert_acknowledged` |
| `network` | `peer_joined`, `peer_left`, `network_status` |

### Event: `detection_progress`
```json
{
  "video_hash": "abc123...",
  "stage": "analyzing",
  "progress": 0.6,
  "details": {},
  "timestamp": 1700000000.0
}
```

### Event: `detection_complete`
```json
{
  "video_hash": "abc123...",
  "result": {
    "is_deepfake": true,
    "confidence": 0.92,
    "lipsync_score": 0.15,
    "fact_check_score": 0.85,
    "blockchain_tx": "queued"
  },
  "timestamp": 1700000000.0
}
```

## Configuration

### Host Config (`config/host_config.yaml`)

Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `detection.mode` | `full` | Pipeline mode (full = CNN + Gemini) |
| `detection.confidence_threshold` | 0.7 | Detection threshold |
| `networking.api_port` | 5050 | API & WebSocket port |
| `networking.max_clients` | 10 | Max simultaneous clients |
| `database.type` | `postgresql` | Database backend |
| `blockchain.tx_manager.batch_size` | 20 | TX batch size |

### Client Config (`config/client_config.yaml`)

| Setting | Default | Description |
|---------|---------|-------------|
| `discovery.method` | `mdns` | Host discovery method |
| `discovery.manual_host` | `` | Manual host address |
| `api.port` | 5060 | Client API port |
| `upload.max_video_size_mb` | 500 | Max upload size |

## P2P Networking

### mDNS Auto-Discovery
- Service type: `_deepfake-detect._tcp.local.`
- Host registers itself automatically on startup
- Clients browse for services and auto-connect
- Fall back to manual `--host` flag if mDNS is blocked

### Load Balancing
When multiple hosts are available, clients use the **lowest latency** strategy:
- Periodic health checks measure latency
- Jobs route to the fastest healthy host
- Automatic failover if a host goes down

### Result Sync
- Background thread periodically exchanges hash lists between peers
- New results are distributed across the network
- Ensures all nodes have consistent detection data

## Directory Structure

```
blockchain-laptop/
├── run_host.py            # Host entry point
├── run_client.py          # Client entry point
├── requirements-laptop.txt
├── .env.example
├── config/
│   ├── host_config.yaml   # Host configuration
│   └── client_config.yaml # Client configuration
├── scripts/
│   └── setup.sh           # Quick setup
├── services/
│   ├── host_node.py       # Host orchestrator
│   ├── host_api.py        # Host Flask API
│   ├── client_node.py     # Client orchestrator
│   └── client_api.py      # Client Flask API
├── network/
│   ├── peer_discovery.py  # mDNS/Zeroconf
│   ├── websocket_server.py # Flask-SocketIO
│   ├── sync_manager.py    # P2P result sync
│   └── load_balancer.py   # Host selection
├── monitoring/
│   └── network_monitor.py # Network health
└── web/
    ├── templates/
    │   ├── host_dashboard.html
    │   ├── client_upload.html
    │   └── network_map.html
    └── static/
        ├── css/dashboard.css
        └── js/dashboard.js
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Client can't find host | Check same network, try `--host IP:PORT` |
| mDNS not working | Install Bonjour (Windows) or avahi (Linux) |
| WebSocket disconnects | Check firewall, increase `heartbeat_interval` |
| Slow detection | Ensure GPU/MPS is available on host |
| DB connection error | Check PostgreSQL is running, or use SQLite fallback |
| Blockchain errors | Verify .env has correct contract addresses |
