# 🔗 Shared Blockchain Infrastructure

Common blockchain components used by both the **Raspberry Pi** and **Laptop** implementations.

## Components

### Smart Contracts (`contracts/`)
Four Solidity contracts deployed on **Polygon (L2)**:

| Contract | Purpose |
|----------|---------|
| `AccessControl.sol` | Node authorization (wallet-based) |
| `VideoRegistry.sol` | Video detection results on-chain |
| `TrackingLedger.sol` | Spread events, lineage, geo tracking |
| `AlertManager.sol` | Threshold alerts with cooldowns |

### Python Blockchain Client (`blockchain/`)
| Module | Purpose |
|--------|---------|
| `web3_client.py` | High-level Python wrapper for all contracts |
| `transaction_manager.py` | Persistent queue with batch writes + retry |

### Alert System (`alerts/`)
| Module | Purpose |
|--------|---------|
| `alert_listener.py` | Polls blockchain events, routes to handlers |
| `notification_service.py` | Multi-channel delivery (Telegram, Discord, Email) |
| `crypto_authenticator.py` | Wallet-based identity + EIP-191 signing |

### Configuration (`config/`)
| File | Purpose |
|------|---------|
| `blockchain_config.yaml` | Network/contract/TX settings |
| `geo_rules.yaml` | IP privacy, spread detection rules |
| `alert_rules.yaml` | Thresholds, cooldowns, routing |

## Contract Deployment

```bash
cd contracts
npm install
cp .env.example .env
# Edit .env

# Compile
npx hardhat compile

# Test
npx hardhat test

# Deploy
npm run deploy:local     # Local Hardhat node
npm run deploy:amoy      # Polygon Amoy testnet
npm run deploy:polygon   # Polygon mainnet
```

## Usage from Python

```python
from blockchain.web3_client import create_client_from_env

client = create_client_from_env()

# Register a video
tx = client.register_video(
    content_hash="abc123...",
    perceptual_hash="def456...",
    is_deepfake=True,
    confidence=0.92,
    lipsync_score=0.15,
    fact_check_score=0.85,
)
print(f"TX: {tx}")
```
