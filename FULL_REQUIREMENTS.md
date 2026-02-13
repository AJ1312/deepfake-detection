# 📋 FULL SYSTEM REQUIREMENTS — Everything You Need

> **One-stop reference** for ALL APIs, keys, services, packages, and setup steps
> needed to run the complete Deepfake Detection + Blockchain system.

---

## 🔑 APIs & Keys — Where to Get Them

| # | Service | What It Does | Signup URL | Free Tier? |
|---|---------|-------------|------------|------------|
| 1 | **Google Gemini API** | Deepfake verification + fact-checking (model: `gemini-1.5-flash`) | https://aistudio.google.com/apikey | ✅ Yes — 60 req/min free |
| 2 | **Polygon Amoy RPC** | Blockchain testnet access | https://rpc-amoy.polygon.technology (public) | ✅ Free public endpoint |
| 3 | **Alchemy RPC** | Premium blockchain RPC (faster, more reliable) | https://www.alchemy.com/ | ✅ Free tier — 300M compute/month |
| 4 | **Infura RPC** | Alternative premium RPC | https://www.infura.io/ | ✅ Free tier — 100K req/day |
| 5 | **PolygonScan API** | Smart contract verification on-chain | https://polygonscan.com/register | ✅ Free — 5 calls/sec |
| 6 | **ip-api.com** | GeoIP location lookup (IP → country/lat/long) | http://ip-api.com — no signup needed | ✅ 100 req/min free |
| 7 | **Telegram Bot Token** | Alert notifications via Telegram | https://t.me/BotFather → `/newbot` | ✅ Free |
| 8 | **Discord Webhook** | Alert notifications via Discord | Discord Server → Settings → Integrations → Webhooks | ✅ Free |
| 9 | **SMTP Email** | Alert notifications via email | Gmail: https://myaccount.google.com/apppasswords | ✅ Free |
| 10 | **Polygon Faucet** | Free testnet MATIC tokens for gas fees | https://faucet.polygon.technology/ | ✅ Free |
| 11 | **MaxMind GeoLite2** | Offline GeoIP database (production upgrade) | https://dev.maxmind.com/geoip/geolite2-free-geolocation-data | ✅ Free with signup |
| 12 | **Kaggle** | Dataset download (training data) | https://www.kaggle.com/account/login | ✅ Free |

---

## 🌐 Environment Variables — Full List

### ⭐ CRITICAL (must have)

```env
# Blockchain
POLYGON_RPC_URL=https://rpc-amoy.polygon.technology/
WALLET_PRIVATE_KEY=your_64_char_hex_private_key

# Contract addresses (get after deploying contracts)
VIDEO_REGISTRY_ADDRESS=0x...deployed_address...
TRACKING_LEDGER_ADDRESS=0x...deployed_address...
ALERT_MANAGER_ADDRESS=0x...deployed_address...

# Google Gemini (needed for full detection pipeline)
GEMINI_API_KEY=your_gemini_api_key
```

### 📦 DATABASE (host laptop node)

```env
DB_HOST=localhost
DB_USER=deepfake
DB_PASSWORD=your_db_password
```

### 🔔 NOTIFICATIONS (all optional)

```env
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-1001234567890

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
ALERT_EMAIL_FROM=your_email@gmail.com
ALERT_EMAIL_TO=recipient@gmail.com
```

### 🛡️ OPTIONAL

```env
POLYGONSCAN_API_KEY=your_key           # For contract verification
ALCHEMY_API_KEY=your_key               # Premium RPC
REDIS_URL=redis://localhost:6379/1     # Redis connection
IP_HASH_SALT=random_string_here        # IP privacy salt
BLOCKCHAIN_NETWORK=amoy                # Network override
```

---

## 💻 System Dependencies — Install First

| Dependency | What For | macOS | Ubuntu/Debian |
|------------|----------|-------|---------------|
| **Python 3.10+** | Everything | `brew install python@3.12` | `sudo apt install python3 python3-pip python3-venv` |
| **Node.js 18+** | Smart contract compilation | `brew install node` | `curl -fsSL https://deb.nodesource.com/setup_18.x \| sudo -E bash - && sudo apt install nodejs` |
| **Redis** | Caching layer | `brew install redis && brew services start redis` | `sudo apt install redis-server && sudo systemctl start redis` |
| **PostgreSQL** | Host database | `brew install postgresql && brew services start postgresql` | `sudo apt install postgresql && sudo systemctl start postgresql` |
| **FFmpeg** | Video processing | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| **Git** | Version control | `brew install git` | `sudo apt install git` |

---

## 🐍 Python Packages

### Root (Core Detection System)
```
torch, torchvision, opencv-python, numpy, pillow, scipy, 
matplotlib, seaborn, scikit-learn, tqdm, google-generativeai, 
pyyaml, imagehash, pytest, requests, python-dotenv, kagglehub, 
flask, flask-cors, werkzeug
```

### Laptop Node (adds to above)
```
Flask-SocketIO, eventlet, gunicorn, web3, eth-account, eth-abi,
torchaudio, ffmpeg-python, zeroconf, psycopg2-binary, SQLAlchemy,
redis, APScheduler, celery, aiohttp, cryptography, PyJWT, psutil,
geoip2, click, rich
```

### Pi Node (lightweight — NO PyTorch)
```
flask, gunicorn, redis, pyyaml, web3, eth-account,
opencv-python-headless, numpy, scipy, Pillow, imagehash,
requests, psutil, apscheduler, python-json-logger
```

---

## 📦 NPM Packages (Smart Contracts)

```json
{
  "hardhat": "^2.19.0",
  "@nomicfoundation/hardhat-toolbox": "^4.0.0",
  "dotenv": "^16.3.1"
}
```
Solidity compiler: **0.8.20** (with optimizer, 200 runs + viaIR)

---

## ⛓️ Blockchain Requirements

| Requirement | How to Get | Cost |
|-------------|-----------|------|
| **Ethereum wallet** | `python shared/scripts/generate_wallet.py` or MetaMask | Free |
| **MATIC (Amoy testnet)** | https://faucet.polygon.technology/ | Free |
| **MATIC (Polygon mainnet)** | Buy on Coinbase, Binance, etc. | ~$0.001-0.01 per transaction |
| **Deploy 3 contracts** | `npm run deploy:amoy` in `shared/contracts/` | ~0.1 MATIC total |
| **Authorize nodes** | Call `authorizeNode()` on AccessControl contract | ~0.001 MATIC |

---

## 🗄️ Databases

| Database | Used By | Setup |
|----------|---------|-------|
| **PostgreSQL** | Laptop host node | `createdb deepfake_host` (user: `deepfake`) |
| **SQLite** | Everything else (auto-created) | No setup needed |
| **Redis** | Pi cache (port 6379/db 0), Laptop cache (port 6379/db 1) | `redis-server` |

---

## 🚀 QUICK START — Step by Step

### Step 1: System Dependencies
```bash
# macOS
brew install python@3.12 node redis postgresql ffmpeg
brew services start redis
brew services start postgresql

# Create database
createdb deepfake_host
```

### Step 2: Clone & Install Python
```bash
cd "Hackathon copy"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3: Install Smart Contract Tools
```bash
cd shared/contracts
npm install
```

### Step 4: Get API Keys
1. Go to https://aistudio.google.com/apikey → create Gemini key
2. Go to https://faucet.polygon.technology/ → get testnet MATIC
3. Go to https://polygonscan.com/register → get API key (optional)

### Step 5: Set Environment Variables
```bash
# In shared/contracts/
cp .env.example .env && nano .env

# In blockchain-laptop/
cp .env.example .env && nano .env

# In blockchain-pi/ (if using Pi)
cp .env.example .env && nano .env
```

### Step 6: Deploy Smart Contracts
```bash
cd shared/contracts

# Option A: Local test (no real blockchain)
npx hardhat node &
npm run deploy:local

# Option B: Polygon Amoy testnet (recommended)
npm run deploy:amoy
```
**Copy the 3 contract addresses into your `.env` files!**

### Step 7: Run the System

```bash
# Original web app (standalone)
python run_web.py

# --- OR ---

# Laptop Host
cd blockchain-laptop
python run_host.py --debug

# Laptop Client (on another machine)
cd blockchain-laptop
python run_client.py --host 192.168.1.5:5050

# --- OR ---

# Pi Node (on Raspberry Pi)
cd blockchain-pi
python run_pi.py --debug
```

---

## 📁 Where Each .env File Goes

```
Hackathon copy/
├── shared/contracts/.env          ← PRIVATE_KEY, RPC URLs, POLYGONSCAN
├── blockchain-laptop/.env         ← All blockchain + GEMINI + DB + notifications
├── blockchain-pi/.env             ← All blockchain + notifications (no Gemini)
```

---

## ⚠️ Important Notes

1. **Testnet First**: Always test on Amoy before mainnet. Faucet MATIC is free.
2. **Gemini Free Tier**: 60 requests/minute — enough for demos, not production.
3. **Redis Optional**: System falls back to in-memory cache if Redis is down.
4. **PostgreSQL Optional**: Host falls back to SQLite if PostgreSQL is unavailable.
5. **Private Key Security**: NEVER commit `.env` files to Git. They're in `.gitignore`.
6. **Pi Limitations**: No CNN/PyTorch on Pi — uses handcrafted features only.
7. **Same Network**: Host and client must be on the same WiFi/LAN for mDNS discovery.
