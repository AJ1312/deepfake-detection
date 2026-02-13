# Web3 Blockchain-Based Deepfake Detection System - Implementation Action Plan

**Version:** 1.0  
**Date:** February 13, 2026  
**Status:** Ready for Implementation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Technology Stack](#technology-stack)
4. [Shared Infrastructure (Phase 1-2)](#shared-infrastructure)
5. [Implementation A: Raspberry Pi Edge Node](#implementation-a-raspberry-pi-edge-node)
6. [Implementation B: Distributed Laptop System](#implementation-b-distributed-laptop-system)
7. [Testing & Deployment](#testing--deployment)
8. [Cost Analysis](#cost-analysis)
9. [Timeline](#timeline)

---

## Executive Summary

### Current System → Blockchain Migration

**From:** SQLite-based hash cache and lineage tracking with centralized storage  
**To:** Polygon blockchain-based immutable ledger with distributed verification nodes

### Key Objectives

1. **Immutable Audit Trail**: Replace SQLite with Polygon smart contracts for tamper-proof video detection records
2. **Distributed Verification**: Enable multiple nodes (Pi/laptops) to independently verify and record deepfakes
3. **Enhanced IP Tracking**: Secure, privacy-preserving location tracking with on-chain alerts
4. **Crypto-Based Alerting**: Automated notifications when flagged videos reappear, triggered by smart contract events
5. **Dual Deployment Models**: 
   - **Edge Computing**: Raspberry Pi as standalone verification node
   - **Distributed Network**: Multiple laptops sharing analysis load with P2P coordination

### What Changes

| Component | Current System | New Blockchain System |
|-----------|---------------|----------------------|
| **Storage** | SQLite databases | Polygon smart contracts + local cache |
| **Video Hashes** | SHA-256 in `lipsync_cache.db` | On-chain in `VideoRegistry.sol` |
| **Tracking** | `deepfake_lineage.db` | On-chain in `TrackingLedger.sol` |
| **IP Storage** | Hashed IPs in SQLite | On-chain with enhanced privacy |
| **Alerts** | No automated alerts | Smart contract events → Multi-channel notifications |
| **Access Control** | Open API | Wallet-based authentication |
| **Data Integrity** | Mutable database | Immutable blockchain records |
| **Deployment** | Single server | Distributed Pi/laptop nodes |

### What Stays the Same

✅ Core detection pipeline (CNN + Gemini)  
✅ Perceptual hashing algorithm (DCT-based pHash)  
✅ Web interface design  
✅ Video upload flow  
✅ LSH similarity search (moves to off-chain indexing)  

---

## Architecture Overview

### System Architecture Comparison

#### Current Architecture
```
┌─────────────────────┐
│   Flask Web App     │
│   (web/app.py)      │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐
│  Detection Pipeline │
│  (CNN + Gemini)     │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────┐     ┌──────────────────┐
│ SQLite Hash Cache   │ ←→  │  SQLite Lineage  │
│ lipsync_cache.db    │     │  lineage.db      │
└─────────────────────┘     └──────────────────┘
```

#### New Blockchain Architecture
```
┌──────────────────────────────────────────────────────┐
│              Polygon Blockchain (L2)                  │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │ VideoRegistry  │  │ TrackingLedger│  │AlertMgr  │ │
│  │  .sol          │  │  .sol         │  │ .sol     │ │
│  └────────────────┘  └──────────────┘  └──────────┘ │
└───────────────────────────┬──────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ↓                   ↓                   ↓
┌───────────────┐   ┌───────────────┐   ┌──────────────┐
│  Pi Node      │   │ Laptop Host   │   │Laptop Client │
│  (Edge)       │   │ (Coordinator) │   │ (Uploader)   │
├───────────────┤   ├───────────────┤   ├──────────────┤
│ Light Analysis│   │ Full Pipeline │   │ Upload Only  │
│ Local Cache   │   │ Local Cache   │   │ Auto-discover│
│ Batch Writes  │   │ Alert Listener│   │ Connect Host │
└───────────────┘   └───────────────┘   └──────────────┘
```

### Data Flow: Video Upload → Blockchain Record

```
1. User uploads video
   ↓
2. Extract frames & compute hashes (SHA-256, pHash, LSH)
   ↓
3. Check local cache (Redis/SQLite) for quick lookup
   ↓ [cache miss]
4. Query blockchain for perceptual hash matches
   ↓ [not found]
5. Run detection pipeline (CNN + Gemini)
   ↓
6. Create blockchain transaction with result
   ↓
7. Submit to Polygon network (transaction fee ~$0.001)
   ↓
8. Transaction confirmed (~2-5 seconds)
   ↓
9. Smart contract emits event
   ↓
10. Alert Listener catches event & checks rules
    ↓ [if flagged video detected]
11. Send notification (Telegram/Email/Discord)
    ↓
12. Update local cache with blockchain data
    ↓
13. Return result to user
```

---

## Technology Stack

### Blockchain Layer
- **Blockchain**: Polygon (Ethereum L2) - Low fees (~$0.001-0.01/tx)
- **Smart Contracts**: Solidity 0.8.20+
- **Development Framework**: Hardhat or Foundry
- **Node Provider**: Alchemy or Infura (Polygon endpoint)
- **Wallet Management**: Web3.py + eth-keyfile encryption

### Backend Layer (Unchanged Core)
- **Language**: Python 3.10+
- **Web Framework**: Flask 3.0+
- **Detection**: PyTorch 2.0+ (CNN), Google Gemini API
- **Video Processing**: OpenCV 4.8+, Pillow
- **Hashing**: SHA-256, DCT-based pHash, LSH

### New Components
- **Web3 Integration**: Web3.py 6.0+
- **Local Cache**: Redis 7.0+ (Pi/laptop nodes)
- **P2P Discovery**: Zeroconf (mDNS/Bonjour)
- **Real-time Comms**: Flask-SocketIO
- **Task Queue**: Celery + RabbitMQ (optional for heavy load)
- **Monitoring**: Prometheus + Grafana

### Hardware Requirements

**Raspberry Pi Implementation:**
- Raspberry Pi 4 Model B (4GB or 8GB RAM)
- 32GB+ microSD card (Class 10/UHS-I)
- Power supply (5V 3A USB-C)
- Ethernet connection (recommended) or WiFi
- Optional: Heatsink + fan for sustained load

**Laptop Implementation (Host):**
- 8GB+ RAM
- 20GB+ free disk space
- Dual-core+ CPU (quad-core recommended)
- GPU with CUDA support (optional, speeds up CNN)
- Stable internet connection

**Laptop Implementation (Client):**
- 4GB+ RAM
- 5GB+ free disk space
- Any modern dual-core CPU
- Network access to host laptop

---

## Shared Infrastructure

These components are used by both Pi and laptop implementations. Complete this phase first before proceeding to implementation-specific sections.

---

### Phase 1: Smart Contract Development (3-4 days)

#### Step 1.1: Create Project Structure

Create the shared contracts and blockchain infrastructure folders:

```bash
# Create directory structure
mkdir -p shared/contracts/{contracts,scripts,test}
mkdir -p shared/blockchain
mkdir -p shared/alerts
mkdir -p shared/tracking
mkdir -p shared/config
mkdir -p shared/docs

# Navigate to contracts directory
cd shared/contracts
```

**Folder Structure:**
```
shared/
├── contracts/                    # Smart contract project
│   ├── contracts/               # Solidity source files
│   │   ├── VideoRegistry.sol
│   │   ├── TrackingLedger.sol
│   │   ├── AlertManager.sol
│   │   └── AccessControl.sol
│   ├── scripts/
│   │   ├── deploy.js            # Deployment script
│   │   └── verify.js            # Contract verification
│   ├── test/
│   │   ├── VideoRegistry.test.js
│   │   ├── TrackingLedger.test.js
│   │   └── AlertManager.test.js
│   ├── hardhat.config.js        # Hardhat configuration
│   ├── package.json
│   └── deployed-addresses.json  # Deployed contract addresses
├── blockchain/                   # Python Web3 integration
│   ├── __init__.py
│   ├── web3_client.py           # Web3.py wrapper
│   ├── transaction_manager.py   # Transaction handling
│   ├── gas_optimizer.py         # Gas price management
│   └── ipfs_storage.py          # IPFS integration (optional)
├── alerts/                       # Alert system
│   ├── __init__.py
│   ├── alert_listener.py        # Event listener
│   ├── notification_service.py  # Multi-channel notifications
│   └── crypto_authenticator.py  # Signature verification
├── tracking/                     # Enhanced tracking
│   ├── __init__.py
│   ├── geo_verifier.py          # Advanced geo-verification
│   └── pattern_detector.py      # Suspicious pattern detection
├── config/                       # Shared configuration
│   ├── blockchain_config.yaml   # Blockchain settings
│   ├── geo_rules.yaml           # Geo-fencing rules
│   └── alert_rules.yaml         # Alert trigger rules
└── docs/
    ├── CONTRACT_API.md          # Smart contract reference
    ├── SECURITY.md              # Security best practices
    └── DEPLOYMENT.md            # Deployment guide
```

#### Step 1.2: Initialize Hardhat Project

```bash
cd shared/contracts

# Initialize Node.js project
npm init -y

# Install Hardhat and dependencies
npm install --save-dev hardhat @nomicfoundation/hardhat-toolbox

# Initialize Hardhat
npx hardhat

# Select: Create a JavaScript project
# Install dependencies when prompted
```

#### Step 1.3: Configure Hardhat for Polygon

Create `shared/contracts/hardhat.config.js`:

```javascript
require("@nomicfoundation/hardhat-toolbox");
require('dotenv').config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      }
    }
  },
  networks: {
    // Local development
    hardhat: {
      chainId: 31337
    },
    
    // Polygon Mumbai Testnet
    mumbai: {
      url: process.env.POLYGON_MUMBAI_RPC || "https://rpc-mumbai.maticvigil.com",
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
      chainId: 80001,
      gasPrice: 20000000000, // 20 gwei
    },
    
    // Polygon Mainnet
    polygon: {
      url: process.env.POLYGON_MAINNET_RPC || "https://polygon-rpc.com",
      accounts: process.env.PRIVATE_KEY ? [process.env.PRIVATE_KEY] : [],
      chainId: 137,
      gasPrice: "auto"
    }
  },
  etherscan: {
    apiKey: {
      polygon: process.env.POLYGONSCAN_API_KEY || "",
      polygonMumbai: process.env.POLYGONSCAN_API_KEY || ""
    }
  }
};
```

Create `.env` file (add to `.gitignore`):
```bash
PRIVATE_KEY=your_wallet_private_key_here
POLYGON_MUMBAI_RPC=https://polygon-mumbai.g.alchemy.com/v2/YOUR_API_KEY
POLYGON_MAINNET_RPC=https://polygon-mainnet.g.alchemy.com/v2/YOUR_API_KEY
POLYGONSCAN_API_KEY=your_polygonscan_api_key
```

#### Step 1.4: Write Smart Contracts

**Contract 1: VideoRegistry.sol**

Create `shared/contracts/contracts/VideoRegistry.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AccessControl.sol";

/**
 * @title VideoRegistry
 * @dev Stores video detection results on-chain with perceptual hashing
 */
contract VideoRegistry is AccessControl {
    
    struct VideoRecord {
        bytes32 contentHash;        // SHA-256 of video content
        string perceptualHash;      // DCT-based perceptual hash (5 frames)
        bool isDeepfake;           // Detection result
        uint256 confidence;        // Confidence score (0-10000, basis points)
        uint256 lipsyncScore;      // Lip-sync analysis score
        uint256 factCheckScore;    // Fact-check score
        uint256 firstSeen;         // First detection timestamp
        uint256 lastSeen;          // Most recent detection timestamp
        uint256 detectionCount;    // Number of times detected
        bytes32 ipHash;            // Privacy-preserving IP hash
        string country;            // Origin country
        string city;               // Origin city
        int256 latitude;           // Latitude * 1000000 (6 decimal places)
        int256 longitude;          // Longitude * 1000000
        address uploaderNode;      // Node that first uploaded
        string metadata;           // JSON metadata string
    }
    
    // Mapping: contentHash => VideoRecord
    mapping(bytes32 => VideoRecord) public videos;
    
    // Mapping: perceptualHash => contentHash[] (for similarity search)
    mapping(bytes32 => bytes32[]) public perceptualHashIndex;
    
    // Array of all video hashes for enumeration
    bytes32[] public allVideoHashes;
    
    // Events
    event VideoRegistered(
        bytes32 indexed contentHash,
        bool isDeepfake,
        uint256 confidence,
        address indexed uploaderNode,
        uint256 timestamp
    );
    
    event DeepfakeDetected(
        bytes32 indexed contentHash,
        uint256 confidence,
        string country,
        string city,
        bytes32 ipHash
    );
    
    event VideoRedetected(
        bytes32 indexed contentHash,
        uint256 detectionCount,
        bytes32 ipHash,
        uint256 timestamp
    );
    
    /**
     * @dev Register a new video or update existing record
     */
    function registerVideo(
        bytes32 _contentHash,
        string memory _perceptualHash,
        bool _isDeepfake,
        uint256 _confidence,
        uint256 _lipsyncScore,
        uint256 _factCheckScore,
        bytes32 _ipHash,
        string memory _country,
        string memory _city,
        int256 _latitude,
        int256 _longitude,
        string memory _metadata
    ) external onlyAuthorizedNode {
        require(_contentHash != bytes32(0), "Invalid content hash");
        require(_confidence <= 10000, "Confidence must be <= 10000");
        
        VideoRecord storage record = videos[_contentHash];
        
        if (record.firstSeen == 0) {
            // New video
            record.contentHash = _contentHash;
            record.perceptualHash = _perceptualHash;
            record.isDeepfake = _isDeepfake;
            record.confidence = _confidence;
            record.lipsyncScore = _lipsyncScore;
            record.factCheckScore = _factCheckScore;
            record.firstSeen = block.timestamp;
            record.lastSeen = block.timestamp;
            record.detectionCount = 1;
            record.ipHash = _ipHash;
            record.country = _country;
            record.city = _city;
            record.latitude = _latitude;
            record.longitude = _longitude;
            record.uploaderNode = msg.sender;
            record.metadata = _metadata;
            
            allVideoHashes.push(_contentHash);
            
            // Index perceptual hash
            bytes32 pHashKey = keccak256(abi.encodePacked(_perceptualHash));
            perceptualHashIndex[pHashKey].push(_contentHash);
            
            emit VideoRegistered(_contentHash, _isDeepfake, _confidence, msg.sender, block.timestamp);
            
            if (_isDeepfake) {
                emit DeepfakeDetected(_contentHash, _confidence, _country, _city, _ipHash);
            }
        } else {
            // Re-detection
            record.lastSeen = block.timestamp;
            record.detectionCount++;
            
            emit VideoRedetected(_contentHash, record.detectionCount, _ipHash, block.timestamp);
        }
    }
    
    /**
     * @dev Get video record by content hash
     */
    function getVideo(bytes32 _contentHash) external view returns (VideoRecord memory) {
        require(videos[_contentHash].firstSeen != 0, "Video not found");
        return videos[_contentHash];
    }
    
    /**
     * @dev Find videos with similar perceptual hash
     */
    function findSimilarVideos(string memory _perceptualHash) external view returns (bytes32[] memory) {
        bytes32 pHashKey = keccak256(abi.encodePacked(_perceptualHash));
        return perceptualHashIndex[pHashKey];
    }
    
    /**
     * @dev Get total number of registered videos
     */
    function getTotalVideos() external view returns (uint256) {
        return allVideoHashes.length;
    }
    
    /**
     * @dev Check if video exists
     */
    function videoExists(bytes32 _contentHash) external view returns (bool) {
        return videos[_contentHash].firstSeen != 0;
    }
}
```

**Contract 2: TrackingLedger.sol**

Create `shared/contracts/contracts/TrackingLedger.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AccessControl.sol";

/**
 * @title TrackingLedger
 * @dev Records spread events and lineage tracking for videos
 */
contract TrackingLedger is AccessControl {
    
    struct SpreadEvent {
        bytes32 videoHash;
        uint256 timestamp;
        bytes32 ipHash;
        string country;
        string city;
        int256 latitude;
        int256 longitude;
        string platform;        // e.g., "Direct Upload", "YouTube", etc.
        string sourceUrl;
        address reporterNode;
    }
    
    struct LineageRecord {
        bytes32 videoHash;
        bytes32 parentHash;     // Parent video hash (0 if original)
        uint256 generation;     // Distance from original (0 = original)
        string[] mutations;     // Detected mutations (compression, crop, etc.)
        bytes32[] childHashes;  // Child variants
    }
    
    // Mapping: videoHash => SpreadEvent[]
    mapping(bytes32 => SpreadEvent[]) public spreadEvents;
    
    // Mapping: videoHash => LineageRecord
    mapping(bytes32 => LineageRecord) public lineage;
    
    // Tracking for same-IP re-uploads
    mapping(bytes32 => mapping(bytes32 => uint256)) public ipUploadCount; // videoHash => ipHash => count
    
    // Events
    event SpreadEventRecorded(
        bytes32 indexed videoHash,
        string country,
        string city,
        bytes32 ipHash,
        uint256 timestamp
    );
    
    event SameIPReupload(
        bytes32 indexed videoHash,
        bytes32 ipHash,
        uint256 uploadCount
    );
    
    event NewLocationSpread(
        bytes32 indexed videoHash,
        string previousCountry,
        string newCountry,
        uint256 timestamp
    );
    
    event LineageEstablished(
        bytes32 indexed childHash,
        bytes32 indexed parentHash,
        uint256 generation
    );
    
    /**
     * @dev Record a spread event for a video
     */
    function recordSpreadEvent(
        bytes32 _videoHash,
        bytes32 _ipHash,
        string memory _country,
        string memory _city,
        int256 _latitude,
        int256 _longitude,
        string memory _platform,
        string memory _sourceUrl
    ) external onlyAuthorizedNode {
        require(_videoHash != bytes32(0), "Invalid video hash");
        
        SpreadEvent memory newEvent = SpreadEvent({
            videoHash: _videoHash,
            timestamp: block.timestamp,
            ipHash: _ipHash,
            country: _country,
            city: _city,
            latitude: _latitude,
            longitude: _longitude,
            platform: _platform,
            sourceUrl: _sourceUrl,
            reporterNode: msg.sender
        });
        
        spreadEvents[_videoHash].push(newEvent);
        
        emit SpreadEventRecorded(_videoHash, _country, _city, _ipHash, block.timestamp);
        
        // Check for same-IP re-upload
        ipUploadCount[_videoHash][_ipHash]++;
        if (ipUploadCount[_videoHash][_ipHash] > 1) {
            emit SameIPReupload(_videoHash, _ipHash, ipUploadCount[_videoHash][_ipHash]);
        }
        
        // Check for new location spread
        if (spreadEvents[_videoHash].length > 1) {
            SpreadEvent memory prevEvent = spreadEvents[_videoHash][spreadEvents[_videoHash].length - 2];
            if (keccak256(abi.encodePacked(prevEvent.country)) != keccak256(abi.encodePacked(_country))) {
                emit NewLocationSpread(_videoHash, prevEvent.country, _country, block.timestamp);
            }
        }
    }
    
    /**
     * @dev Register lineage relationship between videos
     */
    function registerLineage(
        bytes32 _childHash,
        bytes32 _parentHash,
        uint256 _generation,
        string[] memory _mutations
    ) external onlyAuthorizedNode {
        require(_childHash != bytes32(0), "Invalid child hash");
        require(lineage[_childHash].videoHash == bytes32(0), "Lineage already set");
        
        lineage[_childHash] = LineageRecord({
            videoHash: _childHash,
            parentHash: _parentHash,
            generation: _generation,
            mutations: _mutations,
            childHashes: new bytes32[](0)
        });
        
        // Update parent's children array if parent exists
        if (_parentHash != bytes32(0) && lineage[_parentHash].videoHash != bytes32(0)) {
            lineage[_parentHash].childHashes.push(_childHash);
        }
        
        emit LineageEstablished(_childHash, _parentHash, _generation);
    }
    
    /**
     * @dev Get all spread events for a video
     */
    function getSpreadEvents(bytes32 _videoHash) external view returns (SpreadEvent[] memory) {
        return spreadEvents[_videoHash];
    }
    
    /**
     * @dev Get lineage information for a video
     */
    function getLineage(bytes32 _videoHash) external view returns (LineageRecord memory) {
        return lineage[_videoHash];
    }
    
    /**
     * @dev Get number of spread events for a video
     */
    function getSpreadCount(bytes32 _videoHash) external view returns (uint256) {
        return spreadEvents[_videoHash].length;
    }
}
```

**Contract 3: AlertManager.sol**

Create `shared/contracts/contracts/AlertManager.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AccessControl.sol";

/**
 * @title AlertManager
 * @dev Manages threshold-based alerts and notification rules
 */
contract AlertManager is AccessControl {
    
    struct AlertRule {
        uint256 detectionThreshold;    // Trigger after N detections
        uint256 spreadThreshold;        // Trigger after N spread events
        bool enabled;
    }
    
    struct Alert {
        bytes32 videoHash;
        string alertType;              // "THRESHOLD", "VIRAL_SPREAD", "GEO_FENCE"
        string message;
        uint256 timestamp;
        bool acknowledged;
    }
    
    // Global alert rules
    AlertRule public globalRules;
    
    // Mapping: videoHash => Alert[]
    mapping(bytes32 => Alert[]) public alerts;
    
    // Array of all alerts for enumeration
    Alert[] public allAlerts;
    
    // Events
    event ThresholdCrossed(
        bytes32 indexed videoHash,
        uint256 detectionCount,
        uint256 threshold,
        uint256 timestamp
    );
    
    event ViralSpreadDetected(
        bytes32 indexed videoHash,
        uint256 spreadCount,
        uint256 threshold
    );
    
    event AlertCreated(
        bytes32 indexed videoHash,
        string alertType,
        string message,
        uint256 timestamp
    );
    
    event AlertAcknowledged(
        uint256 indexed alertId,
        address acknowledgedBy
    );
    
    constructor() {
        // Default thresholds
        globalRules = AlertRule({
            detectionThreshold: 100,
            spreadThreshold: 50,
            enabled: true
        });
    }
    
    /**
     * @dev Set global alert rules (admin only)
     */
    function setGlobalRules(
        uint256 _detectionThreshold,
        uint256 _spreadThreshold,
        bool _enabled
    ) external onlyOwner {
        globalRules = AlertRule({
            detectionThreshold: _detectionThreshold,
            spreadThreshold: _spreadThreshold,
            enabled: _enabled
        });
    }
    
    /**
     * @dev Check and trigger threshold alerts
     */
    function checkThresholds(
        bytes32 _videoHash,
        uint256 _detectionCount,
        uint256 _spreadCount
    ) external onlyAuthorizedNode {
        if (!globalRules.enabled) return;
        
        // Check detection threshold
        if (_detectionCount >= globalRules.detectionThreshold) {
            emit ThresholdCrossed(_videoHash, _detectionCount, globalRules.detectionThreshold, block.timestamp);
            
            _createAlert(
                _videoHash,
                "THRESHOLD",
                string(abi.encodePacked("Video detected ", _uint2str(_detectionCount), " times"))
            );
        }
        
        // Check spread threshold
        if (_spreadCount >= globalRules.spreadThreshold) {
            emit ViralSpreadDetected(_videoHash, _spreadCount, globalRules.spreadThreshold);
            
            _createAlert(
                _videoHash,
                "VIRAL_SPREAD",
                string(abi.encodePacked("Video spread to ", _uint2str(_spreadCount), " locations"))
            );
        }
    }
    
    /**
     * @dev Create a custom alert
     */
    function createAlert(
        bytes32 _videoHash,
        string memory _alertType,
        string memory _message
    ) external onlyAuthorizedNode {
        _createAlert(_videoHash, _alertType, _message);
    }
    
    /**
     * @dev Internal function to create alert
     */
    function _createAlert(
        bytes32 _videoHash,
        string memory _alertType,
        string memory _message
    ) internal {
        Alert memory newAlert = Alert({
            videoHash: _videoHash,
            alertType: _alertType,
            message: _message,
            timestamp: block.timestamp,
            acknowledged: false
        });
        
        alerts[_videoHash].push(newAlert);
        allAlerts.push(newAlert);
        
        emit AlertCreated(_videoHash, _alertType, _message, block.timestamp);
    }
    
    /**
     * @dev Acknowledge an alert
     */
    function acknowledgeAlert(uint256 _alertId) external onlyAuthorizedNode {
        require(_alertId < allAlerts.length, "Invalid alert ID");
        require(!allAlerts[_alertId].acknowledged, "Already acknowledged");
        
        allAlerts[_alertId].acknowledged = true;
        
        emit AlertAcknowledged(_alertId, msg.sender);
    }
    
    /**
     * @dev Get all alerts for a video
     */
    function getAlerts(bytes32 _videoHash) external view returns (Alert[] memory) {
        return alerts[_videoHash];
    }
    
    /**
     * @dev Get total number of alerts
     */
    function getTotalAlerts() external view returns (uint256) {
        return allAlerts.length;
    }
    
    /**
     * @dev Convert uint to string (helper function)
     */
    function _uint2str(uint256 _i) internal pure returns (string memory) {
        if (_i == 0) return "0";
        uint256 j = _i;
        uint256 len;
        while (j != 0) {
            len++;
            j /= 10;
        }
        bytes memory bstr = new bytes(len);
        uint256 k = len;
        while (_i != 0) {
            k = k-1;
            uint8 temp = (48 + uint8(_i - _i / 10 * 10));
            bytes1 b1 = bytes1(temp);
            bstr[k] = b1;
            _i /= 10;
        }
        return string(bstr);
    }
}
```

**Contract 4: AccessControl.sol**

Create `shared/contracts/contracts/AccessControl.sol`:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AccessControl
 * @dev Manages authorized nodes (Pi/laptop wallets) for write access
 */
contract AccessControl {
    
    address public owner;
    
    // Mapping: address => authorized
    mapping(address => bool) public authorizedNodes;
    
    // Array of authorized addresses
    address[] public authorizedNodeList;
    
    event NodeAuthorized(address indexed node, address authorizedBy);
    event NodeDeauthorized(address indexed node, address deauthorizedBy);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner can call this");
        _;
    }
    
    modifier onlyAuthorizedNode() {
        require(authorizedNodes[msg.sender] || msg.sender == owner, "Not authorized");
        _;
    }
    
    constructor() {
        owner = msg.sender;
        authorizedNodes[msg.sender] = true;
        authorizedNodeList.push(msg.sender);
    }
    
    /**
     * @dev Authorize a new node (Pi or laptop wallet)
     */
    function authorizeNode(address _node) external onlyOwner {
        require(!authorizedNodes[_node], "Already authorized");
        authorizedNodes[_node] = true;
        authorizedNodeList.push(_node);
        emit NodeAuthorized(_node, msg.sender);
    }
    
    /**
     * @dev Deauthorize a node
     */
    function deauthorizeNode(address _node) external onlyOwner {
        require(authorizedNodes[_node], "Not authorized");
        require(_node != owner, "Cannot deauthorize owner");
        authorizedNodes[_node] = false;
        emit NodeDeauthorized(_node, msg.sender);
    }
    
    /**
     * @dev Transfer ownership
     */
    function transferOwnership(address _newOwner) external onlyOwner {
        require(_newOwner != address(0), "Invalid address");
        address previousOwner = owner;
        owner = _newOwner;
        
        if (!authorizedNodes[_newOwner]) {
            authorizedNodes[_newOwner] = true;
            authorizedNodeList.push(_newOwner);
        }
        
        emit OwnershipTransferred(previousOwner, _newOwner);
    }
    
    /**
     * @dev Get all authorized nodes
     */
    function getAuthorizedNodes() external view returns (address[] memory) {
        return authorizedNodeList;
    }
    
    /**
     * @dev Check if address is authorized
     */
    function isAuthorized(address _node) external view returns (bool) {
        return authorizedNodes[_node];
    }
}
```

#### Step 1.5: Create Deployment Scripts

Create `shared/contracts/scripts/deploy.js`:

```javascript
const hre = require("hardhat");
const fs = require("fs");

async function main() {
  console.log("Deploying contracts to", hre.network.name);
  
  // Get deployer account
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying with account:", deployer.address);
  
  // Check balance
  const balance = await deployer.provider.getBalance(deployer.address);
  console.log("Account balance:", hre.ethers.formatEther(balance), "MATIC");
  
  // Deploy AccessControl first (inherited by other contracts)
  console.log("\n1. Deploying VideoRegistry...");
  const VideoRegistry = await hre.ethers.getContractFactory("VideoRegistry");
  const videoRegistry = await VideoRegistry.deploy();
  await videoRegistry.waitForDeployment();
  const videoRegistryAddress = await videoRegistry.getAddress();
  console.log("VideoRegistry deployed to:", videoRegistryAddress);
  
  console.log("\n2. Deploying TrackingLedger...");
  const TrackingLedger = await hre.ethers.getContractFactory("TrackingLedger");
  const trackingLedger = await TrackingLedger.deploy();
  await trackingLedger.waitForDeployment();
  const trackingLedgerAddress = await trackingLedger.getAddress();
  console.log("TrackingLedger deployed to:", trackingLedgerAddress);
  
  console.log("\n3. Deploying AlertManager...");
  const AlertManager = await hre.ethers.getContractFactory("AlertManager");
  const alertManager = await AlertManager.deploy();
  await alertManager.waitForDeployment();
  const alertManagerAddress = await alertManager.getAddress();
  console.log("AlertManager deployed to:", alertManagerAddress);
  
  // Save deployed addresses
  const deployedAddresses = {
    network: hre.network.name,
    chainId: hre.network.config.chainId,
    deployer: deployer.address,
    timestamp: new Date().toISOString(),
    contracts: {
      VideoRegistry: videoRegistryAddress,
      TrackingLedger: trackingLedgerAddress,
      AlertManager: alertManagerAddress
    }
  };
  
  const outputPath = "./deployed-addresses.json";
  fs.writeFileSync(outputPath, JSON.stringify(deployedAddresses, null, 2));
  console.log("\n✅ Deployment complete! Addresses saved to", outputPath);
  
  // Wait for block confirmations before verification
  if (hre.network.name !== "hardhat" && hre.network.name !== "localhost") {
    console.log("\n⏳ Waiting for block confirmations...");
    await videoRegistry.deploymentTransaction().wait(6);
    
    console.log("\n📝 Verifying contracts on PolygonScan...");
    try {
      await hre.run("verify:verify", {
        address: videoRegistryAddress,
        constructorArguments: []
      });
      await hre.run("verify:verify", {
        address: trackingLedgerAddress,
        constructorArguments: []
      });
      await hre.run("verify:verify", {
        address: alertManagerAddress,
        constructorArguments: []
      });
      console.log("✅ Verification complete!");
    } catch (error) {
      console.log("⚠️ Verification failed:", error.message);
    }
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
```

#### Step 1.6: Write Tests

Create `shared/contracts/test/VideoRegistry.test.js`:

```javascript
const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("VideoRegistry", function () {
  let videoRegistry;
  let owner, node1, node2;
  
  const sampleHash = ethers.id("sample_video_content");
  const perceptualHash = "FA3B7D2E1C9A8F6B-D2C1E4F3A5B8C7D9-E1F2A3B4C5D6E7F8-A4B5C6D7E8F9A1B2-B1C2D3E4F5A6B7C8";
  
  beforeEach(async function () {
    [owner, node1, node2] = await ethers.getSigners();
    
    const VideoRegistry = await ethers.getContractFactory("VideoRegistry");
    videoRegistry = await VideoRegistry.deploy();
    await videoRegistry.waitForDeployment();
    
    // Authorize node1
    await videoRegistry.authorizeNode(node1.address);
  });
  
  it("Should register a new video", async function () {
    await videoRegistry.connect(node1).registerVideo(
      sampleHash,
      perceptualHash,
      true, // isDeepfake
      8500, // confidence (85%)
      2341, // lipsyncScore
      7650, // factCheckScore
      ethers.id("192.168.1.1"), // ipHash
      "United States",
      "New York",
      40774900, // latitude * 1000000
      -73968500, // longitude * 1000000
      "{\"model\":\"CNN\"}"
    );
    
    const video = await videoRegistry.getVideo(sampleHash);
    expect(video.isDeepfake).to.equal(true);
    expect(video.confidence).to.equal(8500);
    expect(video.detectionCount).to.equal(1);
  });
  
  it("Should increment detection count on re-detection", async function () {
    // First detection
    await videoRegistry.connect(node1).registerVideo(
      sampleHash, perceptualHash, true, 8500, 2341, 7650,
      ethers.id("192.168.1.1"), "US", "NY", 0, 0, "{}"
    );
    
    // Second detection
    await videoRegistry.connect(node1).registerVideo(
      sampleHash, perceptualHash, true, 8500, 2341, 7650,
      ethers.id("192.168.1.2"), "US", "LA", 0, 0, "{}"
    );
    
    const video = await videoRegistry.getVideo(sampleHash);
    expect(video.detectionCount).to.equal(2);
  });
  
  it("Should emit DeepfakeDetected event", async function () {
    await expect(
      videoRegistry.connect(node1).registerVideo(
        sampleHash, perceptualHash, true, 8500, 2341, 7650,
        ethers.id("192.168.1.1"), "US", "NY", 0, 0, "{}"
      )
    ).to.emit(videoRegistry, "DeepfakeDetected")
     .withArgs(sampleHash, 8500, "US", "NY", ethers.id("192.168.1.1"));
  });
  
  it("Should reject unauthorized nodes", async function () {
    await expect(
      videoRegistry.connect(node2).registerVideo(
        sampleHash, perceptualHash, true, 8500, 2341, 7650,
        ethers.id("192.168.1.1"), "US", "NY", 0, 0, "{}"
      )
    ).to.be.revertedWith("Not authorized");
  });
  
  it("Should find similar videos by perceptual hash", async function () {
    await videoRegistry.connect(node1).registerVideo(
      sampleHash, perceptualHash, true, 8500, 2341, 7650,
      ethers.id("192.168.1.1"), "US", "NY", 0, 0, "{}"
    );
    
    const similar = await videoRegistry.findSimilarVideos(perceptualHash);
    expect(similar.length).to.equal(1);
    expect(similar[0]).to.equal(sampleHash);
  });
});
```

#### Step 1.7: Deploy to Polygon Mumbai Testnet

```bash
cd shared/contracts

# Compile contracts
npx hardhat compile

# Run tests
npx hardhat test

# Deploy to Mumbai testnet
npx hardhat run scripts/deploy.js --network mumbai

# Output will show:
# VideoRegistry deployed to: 0x...
# TrackingLedger deployed to: 0x...
# AlertManager deployed to: 0x...
```

**Get testnet MATIC**: Visit [Mumbai Faucet](https://faucet.polygon.technology/) to get free testnet MATIC for deployment.

---

### Phase 2: Web3 Integration Layer (3-4 days)

#### Step 2.1: Install Python Dependencies

Create `shared/requirements-blockchain.txt`:

```
web3==6.15.0
eth-account==0.10.0
eth-keyfile==0.7.0
python-dotenv==1.0.0
redis==5.0.1
celery==5.3.4
pyyaml==6.0.1
requests==2.31.0
python-telegram-bot==20.7
discord.py==2.3.2
```

Install dependencies:

```bash
cd /Users/ajiteshsharma/Downloads/Hackathon\ copy
pip install -r shared/requirements-blockchain.txt
```

#### Step 2.2: Create Web3 Client Module

Create `shared/blockchain/web3_client.py`:

```python
"""
Web3 Client for interacting with Polygon smart contracts
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Web3Client:
    """Web3.py wrapper for smart contract interactions"""
    
    def __init__(self, config_path: str = "shared/contracts/deployed-addresses.json"):
        """
        Initialize Web3 client
        
        Args:
            config_path: Path to deployed contract addresses JSON
        """
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Connect to Polygon RPC
        rpc_url = os.getenv('POLYGON_RPC_URL', 'https://polygon-rpc.com')
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        # Inject PoA middleware for Polygon
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Verify connection
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to Polygon RPC: {rpc_url}")
        
        logger.info(f"Connected to Polygon (Chain ID: {self.w3.eth.chain_id})")
        
        # Load account from private key
        private_key = os.getenv('PRIVATE_KEY')
        if not private_key:
            raise ValueError("PRIVATE_KEY not found in environment")
        
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        
        logger.info(f"Using account: {self.address}")
        
        # Load contract ABIs and addresses
        self.contracts = self._load_contracts()
    
    def _load_contracts(self) -> Dict:
        """Load contract instances from deployed addresses"""
        contracts = {}
        
        # Load ABIs from compiled artifacts
        artifact_dir = Path("shared/contracts/artifacts/contracts")
        
        for contract_name in ['VideoRegistry', 'TrackingLedger', 'AlertManager']:
            # Load ABI
            abi_path = artifact_dir / f"{contract_name}.sol" / f"{contract_name}.json"
            with open(abi_path, 'r') as f:
                artifact = json.load(f)
                abi = artifact['abi']
            
            # Get deployed address
            address = self.config['contracts'][contract_name]
            
            # Create contract instance
            contracts[contract_name] = self.w3.eth.contract(
                address=Web3.to_checksum_address(address),
                abi=abi
            )
            
            logger.info(f"Loaded {contract_name} at {address}")
        
        return contracts
    
    def register_video_on_chain(
        self,
        content_hash: str,
        perceptual_hash: str,
        is_deepfake: bool,
        confidence: float,
        lipsync_score: float,
        fact_check_score: float,
        ip_hash: str,
        country: str,
        city: str,
        latitude: float,
        longitude: float,
        metadata: Dict
    ) -> str:
        """
        Register video detection result on blockchain
        
        Args:
            content_hash: SHA-256 hash (hex string)
            perceptual_hash: Perceptual hash string
            is_deepfake: Detection result
            confidence: Confidence score (0.0-1.0)
            lipsync_score: Lip-sync analysis score (0.0-1.0)
            fact_check_score: Fact-check score (0.0-1.0)
            ip_hash: Privacy-preserving IP hash
            country: Origin country
            city: Origin city
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            metadata: Additional metadata dictionary
            
        Returns:
            Transaction hash
        """
        try:
            contract = self.contracts['VideoRegistry']
            
            # Convert hash to bytes32
            content_hash_bytes = bytes.fromhex(content_hash.replace('0x', ''))
            ip_hash_bytes = bytes.fromhex(ip_hash.replace('0x', ''))
            
            # Convert scores to basis points (0-10000)
            confidence_bp = int(confidence * 10000)
            lipsync_bp = int(lipsync_score * 10000)
            fact_check_bp = int(fact_check_score * 10000)
            
            # Convert coordinates to integers (scale by 1000000)
            lat_int = int(latitude * 1000000)
            lon_int = int(longitude * 1000000)
            
            # Serialize metadata
            metadata_json = json.dumps(metadata)
            
            # Build transaction
            txn = contract.functions.registerVideo(
                content_hash_bytes,
                perceptual_hash,
                is_deepfake,
                confidence_bp,
                lipsync_bp,
                fact_check_bp,
                ip_hash_bytes,
                country,
                city,
                lat_int,
                lon_int,
                metadata_json
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': 500000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            # Sign and send transaction
            signed_txn = self.account.sign_transaction(txn)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                logger.info(f"Video registered on-chain: {tx_hash.hex()}")
                return tx_hash.hex()
            else:
                raise Exception(f"Transaction failed: {tx_hash.hex()}")
                
        except Exception as e:
            logger.error(f"Failed to register video on chain: {e}")
            raise
    
    def get_video_from_chain(self, content_hash: str) -> Optional[Dict]:
        """
        Retrieve video record from blockchain
        
        Args:
            content_hash: SHA-256 hash (hex string)
            
        Returns:
            Video record dictionary or None if not found
        """
        try:
            contract = self.contracts['VideoRegistry']
            content_hash_bytes = bytes.fromhex(content_hash.replace('0x', ''))
            
            record = contract.functions.getVideo(content_hash_bytes).call()
            
            # Parse record tuple into dictionary
            return {
                'contentHash': record[0].hex(),
                'perceptualHash': record[1],
                'isDeepfake': record[2],
                'confidence': record[3] / 10000.0,
                'lipsyncScore': record[4] / 10000.0,
                'factCheckScore': record[5] / 10000.0,
                'firstSeen': record[6],
                'lastSeen': record[7],
                'detectionCount': record[8],
                'ipHash': record[9].hex(),
                'country': record[10],
                'city': record[11],
                'latitude': record[12] / 1000000.0,
                'longitude': record[13] / 1000000.0,
                'uploaderNode': record[14],
                'metadata': json.loads(record[15]) if record[15] else {}
            }
            
        except Exception as e:
            logger.warning(f"Video not found on chain: {content_hash}")
            return None
    
    def record_spread_event(
        self,
        video_hash: str,
        ip_hash: str,
        country: str,
        city: str,
        latitude: float,
        longitude: float,
        platform: str = "Direct Upload",
        source_url: str = ""
    ) -> str:
        """
        Record video spread event on blockchain
        
        Returns:
            Transaction hash
        """
        try:
            contract = self.contracts['TrackingLedger']
            
            video_hash_bytes = bytes.fromhex(video_hash.replace('0x', ''))
            ip_hash_bytes = bytes.fromhex(ip_hash.replace('0x', ''))
            
            lat_int = int(latitude * 1000000)
            lon_int = int(longitude * 1000000)
            
            txn = contract.functions.recordSpreadEvent(
                video_hash_bytes,
                ip_hash_bytes,
                country,
                city,
                lat_int,
                lon_int,
                platform,
                source_url
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': 300000,
                'gasPrice': self.w3.eth.gas_price
            })
            
            signed_txn = self.account.sign_transaction(txn)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                logger.info(f"Spread event recorded: {tx_hash.hex()}")
                return tx_hash.hex()
            else:
                raise Exception(f"Transaction failed: {tx_hash.hex()}")
                
        except Exception as e:
            logger.error(f"Failed to record spread event: {e}")
            raise
    
    def get_account_balance(self) -> float:
        """Get account MATIC balance"""
        balance_wei = self.w3.eth.get_balance(self.address)
        return self.w3.from_wei(balance_wei, 'ether')
    
    def estimate_gas_cost(self, operation: str = "register_video") -> float:
        """
        Estimate gas cost in MATIC for common operations
        
        Args:
            operation: "register_video" or "record_spread"
            
        Returns:
            Estimated cost in MATIC
        """
        gas_price = self.w3.eth.gas_price
        
        gas_estimates = {
            'register_video': 500000,
            'record_spread': 300000
        }
        
        gas_limit = gas_estimates.get(operation, 500000)
        cost_wei = gas_price * gas_limit
        return self.w3.from_wei(cost_wei, 'ether')
```

#### Step 2.3: Update Video Hash Cache to Use Blockchain

Modify `src/core/video_hash_cache.py` to integrate blockchain while keeping local cache for performance:

```python
# Add at the top of the file after imports
try:
    from shared.blockchain.web3_client import Web3Client
    BLOCKCHAIN_ENABLED = True
except ImportError:
    BLOCKCHAIN_ENABLED = False
    logger.warning("Blockchain module not available, using SQLite only")

# In VideoHashCache.__init__, add:
self.use_blockchain = use_blockchain and BLOCKCHAIN_ENABLED
if self.use_blockchain:
    try:
        self.web3_client = Web3Client()
        logger.info("Blockchain integration enabled")
    except Exception as e:
        logger.error(f"Failed to initialize blockchain client: {e}")
        self.use_blockchain = False

# Modify store_result method:
def store_result(self, video_path: str, result, cache_only: bool = False):
    """Store detection result in cache and optionally on blockchain"""
    # ... existing hash computation ...
    
    # Store in local SQLite first (fast cache)
    # ... existing SQLite code ...
    
    # Store on blockchain if enabled
    if self.use_blockchain and not cache_only:
        try:
            # Extract geo info (implement helper)
            geo_info = self._get_geo_info()
            
            tx_hash = self.web3_client.register_video_on_chain(
                content_hash=video_hash,
                perceptual_hash=perceptual_hash,
                is_deepfake=result.is_deepfake,
                confidence=result.confidence,
                lipsync_score=result.lipsync_score,
                fact_check_score=result.fact_check_score,
                ip_hash=self._hash_ip(geo_info['ip']),
                country=geo_info['country'],
                city=geo_info['city'],
                latitude=geo_info['latitude'],
                longitude=geo_info['longitude'],
                metadata={
                    'detection_method': result.detection_method,
                    'processing_time': result.processing_time,
                    'celebrity': result.celebrity_name if result.celebrity_detected else None
                }
            )
            logger.info(f"Stored on blockchain: {tx_hash}")
        except Exception as e:
            logger.error(f"Blockchain storage failed: {e}")
```

*(Continue with transaction manager, alert listener, and other Phase 2 components...)*

---

### Timeline Summary (Phase 1-2)

| Phase | Duration | Deliverables |
|-------|----------|-------------|
| **Phase 1: Smart Contracts** | 3-4 days | 4 Solidity contracts, deployment scripts, tests |
| **Phase 2: Web3 Integration** | 3-4 days | Python Web3 client, blockchain-enabled cache, alert system |

**Total Shared Infrastructure:** 6-8 days

---

## Implementation A: Raspberry Pi Edge Node

This implementation turns a Raspberry Pi 4 into a standalone deepfake detection node that operates at the edge (e.g., in a school, library, or community center). The Pi performs lightweight video analysis and writes results to the blockchain.

### Requirements

**Hardware:**
- Raspberry Pi 4 Model B (4GB or 8GB RAM)
- 32GB+ microSD card (Class 10 or UHS-I)
- 5V 3A USB-C power supply
- Ethernet cable (recommended) or WiFi
- Optional: Heatsink + fan

**Software:**
- Raspberry Pi OS Lite (64-bit) - Debian 12 (Bookworm)
- Python 3.10+
- Redis for local caching
- Systemd for service management

### Architecture

```
┌─────────────────────────────────────────┐
│      Raspberry Pi 4 (Edge Node)          │
├─────────────────────────────────────────┤
│                                          │
│  ┌────────────────────────────────────┐ │
│  │   Flask Web API (Port 8080)        │ │
│  │   - Video Upload Endpoint          │ │
│  │   - Health Check                   │ │
│  └──────────────┬─────────────────────┘ │
│                 │                        │
│  ┌──────────────▼─────────────────────┐ │
│  │   Lightweight Detection Engine     │ │
│  │   - Handcrafted Features Only      │ │
│  │   - No PyTorch CNN (resource limit)│ │
│  │   - Fast Pattern Detection         │ │
│  └──────────────┬─────────────────────┘ │
│                 │                        │
│  ┌──────────────▼─────────────────────┐ │
│  │   Redis Local Cache                │ │
│  │   - Quick Duplicate Checks         │ │
│  │   - TTL: 24 hours                  │ │
│  └──────────────┬─────────────────────┘ │
│                 │                        │
│  ┌──────────────▼─────────────────────┐ │
│  │   Blockchain Uploader              │ │
│  │   - Batch Transactions (10-50)     │ │
│  │   - Queue Offline, Sync Online     │ │
│  └──────────────┬─────────────────────┘ │
│                 │                        │
│  ┌──────────────▼─────────────────────┐ │
│  │   Alert Listener                   │ │
│  │   - Listen to Smart Contract Events│ │
│  │   - Send Telegram/Email Alerts     │ │
│  └────────────────────────────────────┘ │
│                                          │
└────────────┬─────────────────────────────┘
             │
             ▼
    ┌────────────────────┐
    │  Polygon Blockchain │
    │  (via Infura/Alchemy)│
    └────────────────────┘
```

### Deployment Steps

---

#### Step A.1: Setup Folder Structure

Create the Pi-specific implementation folder:

```bash
cd /Users/ajiteshsharma/Downloads/Hackathon\ copy
mkdir -p blockchain-pi/{config,services,monitoring,scripts,web}
```

**Folder Structure:**
```
blockchain-pi/
├── requirements-pi.txt          # Lightweight Python dependencies
├── setup_pi.sh                  # Automated setup script
├── pi_node.py                   # Main Pi service daemon
├── README.md                    # Pi setup documentation
├── .env.example                 # Environment template
├── config/
│   ├── pi_config.yaml           # Pi-specific settings
│   ├── redis.conf               # Redis configuration
│   └── nginx.conf               # Nginx reverse proxy config
├── services/
│   ├── __init__.py
│   ├── video_analyzer.py        # Lightweight detection (no CNN)
│   ├── blockchain_uploader.py   # Batch transaction manager
│   ├── local_cache.py           # Redis cache wrapper
│   └── offline_queue.py         # Offline transaction queue
├── monitoring/
│   ├── __init__.py
│   ├── health_check.py          # System health monitor
│   ├── metrics.py               # Prometheus metrics exporter
│   └── dashboard.html           # Simple status dashboard
├── scripts/
│   ├── install_dependencies.sh
│   ├── generate_wallet.py       # Create encrypted wallet
│   ├── deploy_systemd.sh        # Install systemd service
│   └── test_connectivity.py     # Test blockchain connection
└── web/
    ├── pi_api.py                # Flask API for Pi
    └── templates/
        └── upload.html          # Simple upload interface
```

#### Step A.2: Create Requirements File

Create `blockchain-pi/requirements-pi.txt`:

```
# Core dependencies (lightweight for Pi)
flask==3.0.0
flask-cors==4.0.0
web3==6.15.0
eth-account==0.10.0
eth-keyfile==0.7.0
redis==5.0.1
python-dotenv==1.0.0
pyyaml==6.0.1
requests==2.31.0

# Video processing (without PyTorch)
opencv-python-headless==4.8.1.78  # Headless version for Pi
pillow==10.1.0
numpy==1.24.3

# Monitoring
prometheus-client==0.19.0

# Alerts
python-telegram-bot==20.7
```

#### Step A.3: Create Setup Script

Create `blockchain-pi/setup_pi.sh`:

```bash
#!/bin/bash
# Automated Raspberry Pi Setup Script for DeepFake Detection Node

set -e

echo "========================================="
echo "Raspberry Pi DeepFake Detection Node Setup"
echo "========================================="

# Check if running on Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo; then
    echo "⚠️  Warning: This script is optimized for Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "📦 Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install system dependencies
echo "📦 Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    redis-server \
    nginx \
    git \
    libopencv-dev \
    libatlas-base-dev \
    libjpeg-dev \
    libpng-dev \
    libavformat-dev \
    libavcodec-dev \
    libswscale-dev

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements-pi.txt

# Configure Redis
echo "🔧 Configuring Redis..."
sudo cp config/redis.conf /etc/redis/redis.conf
sudo systemctl enable redis-server
sudo systemctl restart redis-server

# Configure Nginx (optional reverse proxy)
echo "🔧 Configuring Nginx..."
sudo cp config/nginx.conf /etc/nginx/sites-available/deepfake-pi
sudo ln -sf /etc/nginx/sites-available/deepfake-pi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Generate wallet if not exists
if [ ! -f ".env" ]; then
    echo "🔐 Generating new wallet..."
    source venv/bin/activate
    python3 scripts/generate_wallet.py
    echo "✅ Wallet created! Save your private key securely."
else
    echo "✅ Existing .env file found, skipping wallet generation"
fi

# Load environment
source .env

# Deploy systemd service
echo "⚙️  Deploying systemd service..."
bash scripts/deploy_systemd.sh

# Test connectivity
echo "🌐 Testing blockchain connectivity..."
python3 scripts/test_connectivity.py

echo ""
echo "========================================="
echo "✅ Setup Complete!"
echo "========================================="
echo ""
echo "Raspberry Pi node address: $NODE_ADDRESS"
echo "Service status: sudo systemctl status deepfake-pi-node"
echo "View logs: sudo journalctl -u deepfake-pi-node -f"
echo "Web interface: http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "⚠️  Important: Fund your wallet with MATIC for transactions"
echo "   Address: $NODE_ADDRESS"
echo "   Get testnet MATIC: https://faucet.polygon.technology/"
echo ""
```

#### Step A.4: Create Pi Configuration

Create `blockchain-pi/config/pi_config.yaml`:

```yaml
# Raspberry Pi Node Configuration

node:
  name: "Pi-DeepFake-Node-001"
  location: "Edge Deployment"
  
  # API settings
  api:
    host: "0.0.0.0"
    port: 8080
    debug: false
    max_content_length: 104857600  # 100MB max upload
  
  # Detection settings
  detection:
    use_cnn: false  # CNN disabled on Pi (resource constraint)
    use_handcrafted_features: true
    confidence_threshold: 0.7
    defer_to_cloud: true  # Defer complex analysis to cloud API
    cloud_api_url: "https://your-cloud-api.com/analyze"  # Optional

# Blockchain settings
blockchain:
  network: "polygon"  # or "mumbai" for testnet
  rpc_url: "${POLYGON_RPC_URL}"
  contract_addresses_file: "../shared/contracts/deployed-addresses.json"
  
  # Transaction batching (save gas costs)
  batch_enabled: true
  batch_size: 20  # Send 20 transactions at once
  batch_interval: 300  # Every 5 minutes
  
  # Offline mode
  offline_queue_enabled: true
  max_queue_size: 1000
  sync_interval: 600  # Sync every 10 minutes when online

# Cache settings
cache:
  backend: "redis"
  redis:
    host: "localhost"
    port: 6379
    db: 0
    ttl: 86400  # 24 hours
  
  # Local SQLite fallback if Redis fails
  sqlite_fallback: true
  sqlite_path: "cache.db"

# Geographic tracking
geo:
  provider: "ipapi"  # Free tier: 45 req/min
  cache_duration: 3600  # 1 hour
  fallback_location:
    country: "Unknown"
    city: "Unknown"
    latitude: 0.0
    longitude: 0.0

# Monitoring
monitoring:
  prometheus_enabled: true
  prometheus_port: 9090
  health_check_interval: 60  # seconds
  
  # Resource limits (Pi-specific)
  max_cpu_percent: 80
  max_memory_percent: 75
  max_temperature_celsius: 75  # Thermal throttling threshold

# Alerts
alerts:
  telegram:
    enabled: false  # Set to true and add bot token
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
  
  email:
    enabled: false
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    from_address: "${EMAIL_FROM}"
    to_address: "${EMAIL_TO}"
    password: "${EMAIL_PASSWORD}"

# Logging
logging:
  level: "INFO"
  file: "logs/pi_node.log"
  max_size_mb: 50
  backup_count: 3
```

#### Step A.5: Create Lightweight Video Analyzer

Create `blockchain-pi/services/video_analyzer.py`:

```python
"""
Lightweight video analysis for Raspberry Pi
Uses handcrafted features only (no CNN)
"""
import cv2
import numpy as np
from typing import Dict, Tuple
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LightweightVideoAnalyzer:
    """
    Fast video analysis using handcrafted features
    Optimized for Raspberry Pi (no PyTorch required)
    """
    
    def __init__(self):
        self.confidence_threshold = 0.7
    
    def analyze_video(self, video_path: str) -> Dict:
        """
        Analyze video using lightweight methods
        
        Returns:
            {
                'is_deepfake': bool,
                'confidence': float,
                'lipsync_score': float,
                'method': 'handcrafted_features',
                'processing_time': float
            }
        """
        import time
        start_time = time.time()
        
        try:
            # Extract frames
            frames = self._extract_frames(video_path, max_frames=10)
            
            if len(frames) < 5:
                logger.warning("Insufficient frames for analysis")
                return self._create_uncertain_result(time.time() - start_time)
            
            # Analyze features
            freq_score = self._analyze_frequency_artifacts(frames)
            edge_score = self._analyze_edge_consistency(frames)
            temporal_score = self._analyze_temporal_consistency(frames)
            
            # Combine scores (weighted average)
            lipsync_score = (
                0.4 * freq_score +
                0.3 * edge_score +
                0.3 * temporal_score
            )
            
            # Determine verdict
            is_deepfake = lipsync_score < 0.5  # Low score = likely fake
            confidence = abs(lipsync_score - 0.5) * 2  # Distance from threshold
            
            processing_time = time.time() - start_time
            
            return {
                'is_deepfake': is_deepfake,
                'confidence': confidence,
                'lipsync_score': lipsync_score,
                'fact_check_score': 0.5,  # Not available on Pi
                'method': 'handcrafted_features',
                'processing_time': processing_time,
                'features': {
                    'frequency_artifacts': freq_score,
                    'edge_consistency': edge_score,
                    'temporal_consistency': temporal_score
                }
            }
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return self._create_uncertain_result(time.time() - start_time)
    
    def _extract_frames(self, video_path: str, max_frames: int = 10) -> list:
        """Extract evenly distributed frames from video"""
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames == 0:
            return []
        
        frame_indices = np.linspace(0, total_frames - 1, max_frames, dtype=int)
        frames = []
        
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                # Resize to reduce memory usage
                frame = cv2.resize(frame, (256, 256))
                frames.append(frame)
        
        cap.release()
        return frames
    
    def _analyze_frequency_artifacts(self, frames: list) -> float:
        """
        Detect high-frequency artifacts typical of deepfakes
        Returns score 0-1 (higher = more natural)
        """
        scores = []
        
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # DCT analysis
            dct = cv2.dct(np.float32(gray))
            
            # High frequency energy (bottom-right quadrant)
            h, w = dct.shape
            high_freq_region = dct[h//2:, w//2:]
            high_freq_energy = np.sum(np.abs(high_freq_region))
            
            # Low frequency energy (top-left quadrant)
            low_freq_region = dct[:h//2, :w//2]
            low_freq_energy = np.sum(np.abs(low_freq_region))
            
            # Ratio (deep fakes often have unusual frequency distribution)
            if low_freq_energy > 0:
                ratio = high_freq_energy / low_freq_energy
                # Normalize to 0-1 range (typical ratio: 0.1-0.5)
                score = 1.0 - min(abs(ratio - 0.3) / 0.3, 1.0)
                scores.append(score)
        
        return np.mean(scores) if scores else 0.5
    
    def _analyze_edge_consistency(self, frames: list) -> float:
        """
        Analyze edge sharpness and consistency
        Returns score 0-1 (higher = more consistent)
        """
        edge_densities = []
        
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Canny edge detection
            edges = cv2.Canny(gray, 50, 150)
            
            # Edge density
            density = np.sum(edges > 0) / edges.size
            edge_densities.append(density)
        
        # Consistent edge density = more natural
        std_dev = np.std(edge_densities)
        
        # Lower std_dev = more consistent
        score = 1.0 / (1.0 + std_dev * 10)
        
        return score
    
    def _analyze_temporal_consistency(self, frames: list) -> float:
        """
        Analyze temporal consistency between consecutive frames
        Returns score 0-1 (higher = more consistent)
        """
        if len(frames) < 2:
            return 0.5
        
        correlations = []
        
        for i in range(len(frames) - 1):
            frame1 = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            frame2 = cv2.cvtColor(frames[i+1], cv2.COLOR_BGR2GRAY)
            
            # Compute correlation
            correlation = np.corrcoef(frame1.flatten(), frame2.flatten())[0, 1]
            correlations.append(correlation)
        
        # High correlation = temporally consistent
        avg_correlation = np.mean(correlations)
        
        # Map correlation (typically 0.7-0.95) to score
        score = (avg_correlation - 0.5) * 2  # Maps 0.5-1.0 to 0-1
        score = max(0, min(1, score))
        
        return score
    
    def _create_uncertain_result(self, processing_time: float) -> Dict:
        """Return uncertain result when analysis fails"""
        return {
            'is_deepfake': False,
            'confidence': 0.3,  # Low confidence
            'lipsync_score': 0.5,
            'fact_check_score': 0.5,
            'method': 'uncertain',
            'processing_time': processing_time,
            'error': 'Analysis incomplete'
        }
```

#### Step A.6: Create Blockchain Uploader with Batching

Create `blockchain-pi/services/blockchain_uploader.py`:

```python
"""
Blockchain transaction uploader with batching support
Optimized to reduce gas costs on Raspberry Pi
"""
import logging
import time
import queue
import threading
from typing import Dict, List
from shared.blockchain.web3_client import Web3Client

logger = logging.getLogger(__name__)


class BlockchainUploader:
    """
    Manages batched blockchain uploads to minimize gas costs
    """
    
    def __init__(self, web3_client: Web3Client, batch_size: int = 20, batch_interval: int = 300):
        """
        Initialize uploader
        
        Args:
            web3_client: Web3Client instance
            batch_size: Number of transactions to batch
            batch_interval: Seconds between batch uploads
        """
        self.web3_client = web3_client
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        
        self.pending_queue = queue.Queue()
        self.upload_thread = None
        self.running = False
        
        logger.info(f"Blockchain uploader initialized (batch_size={batch_size}, interval={batch_interval}s)")
    
    def start(self):
        """Start background upload thread"""
        if self.running:
            logger.warning("Uploader already running")
            return
        
        self.running = True
        self.upload_thread = threading.Thread(target=self._upload_loop, daemon=True)
        self.upload_thread.start()
        logger.info("Background upload thread started")
    
    def stop(self):
        """Stop upload thread and flush pending transactions"""
        logger.info("Stopping uploader...")
        self.running = False
        
        # Upload remaining transactions
        self._flush_batch()
        
        if self.upload_thread:
            self.upload_thread.join(timeout=30)
        
        logger.info("Uploader stopped")
    
    def queue_video_registration(self, video_data: Dict):
        """
        Queue a video registration transaction
        
        Args:
            video_data: Dictionary with all required fields
        """
        self.pending_queue.put(('register_video', video_data))
        logger.debug(f"Queued video registration: {video_data['content_hash'][:16]}...")
    
    def queue_spread_event(self, spread_data: Dict):
        """Queue a spread event transaction"""
        self.pending_queue.put(('spread_event', spread_data))
        logger.debug(f"Queued spread event: {spread_data['video_hash'][:16]}...")
    
    def _upload_loop(self):
        """Background thread that processes batch uploads"""
        next_batch_time = time.time() + self.batch_interval
        
        while self.running:
            try:
                current_time = time.time()
                
                # Check if it's time to send batch or if batch is full
                queue_size = self.pending_queue.qsize()
                
                if queue_size >= self.batch_size or (current_time >= next_batch_time and queue_size > 0):
                    self._flush_batch()
                    next_batch_time = time.time() + self.batch_interval
                
                # Sleep briefly to avoid busy-waiting
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Upload loop error: {e}")
                time.sleep(5)
    
    def _flush_batch(self):
        """Send all pending transactions"""
        batch = []
        
        # Collect pending transactions
        while not self.pending_queue.empty() and len(batch) < self.batch_size:
            try:
                item = self.pending_queue.get_nowait()
                batch.append(item)
            except queue.Empty:
                break
        
        if not batch:
            return
        
        logger.info(f"Uploading batch of {len(batch)} transactions...")
        
        success_count = 0
        for tx_type, data in batch:
            try:
                if tx_type == 'register_video':
                    self._upload_video_registration(data)
                elif tx_type == 'spread_event':
                    self._upload_spread_event(data)
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"Failed to upload {tx_type}: {e}")
                # Re-queue failed transaction
                self.pending_queue.put((tx_type, data))
        
        logger.info(f"Batch upload complete: {success_count}/{len(batch)} successful")
    
    def _upload_video_registration(self, data: Dict):
        """Upload single video registration"""
        tx_hash = self.web3_client.register_video_on_chain(
            content_hash=data['content_hash'],
            perceptual_hash=data['perceptual_hash'],
            is_deepfake=data['is_deepfake'],
            confidence=data['confidence'],
            lipsync_score=data['lipsync_score'],
            fact_check_score=data['fact_check_score'],
            ip_hash=data['ip_hash'],
            country=data['country'],
            city=data['city'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            metadata=data['metadata']
        )
        logger.info(f"Video registered: {tx_hash}")
    
    def _upload_spread_event(self, data: Dict):
        """Upload single spread event"""
        tx_hash = self.web3_client.record_spread_event(
            video_hash=data['video_hash'],
            ip_hash=data['ip_hash'],
            country=data['country'],
            city=data['city'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            platform=data.get('platform', 'Direct Upload'),
            source_url=data.get('source_url', '')
        )
        logger.info(f"Spread event recorded: {tx_hash}")
```

*(Continue with remaining Pi implementation steps: main Pi service, systemd deployment, monitoring, testing...)*

---

## Implementation B: Distributed Laptop System

This implementation creates a peer-to-peer network where multiple laptops collaborate to process deepfake detection. One laptop acts as the **host/coordinator** (running full detection pipeline), while other laptops act as **clients** (uploading videos for analysis).

### Requirements

**Host Laptop (Minimum 1):**
- 8GB+ RAM
- Quad-core CPU (GPU with CUDA recommended)
- 20GB+ free disk space
- Python 3.10+
- Stable internet connection

**Client Laptop(s):**
- 4GB+ RAM
- Dual-core CPU
- 5GB+ free disk space
- Network access to host

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   Polygon Blockchain                      │
│          (Immutable Source of Truth)                      │
└────────────────────┬─────────────────────────────────────┘
                     │
      ┌──────────────┴──────────────┐
      │                             │
      ▼                             ▼
┌─────────────────────┐      ┌─────────────────────┐
│   Host Laptop       │      │   Host Laptop       │
│   (Coordinator 1)   │      │   (Coordinator 2)   │
├─────────────────────┤      ├─────────────────────┤
│ Full Detection      │      │ Full Detection      │
│ PostgreSQL Cache    │      │ PostgreSQL Cache    │
│ Alert Listener      │      │ Alert Listener      │
│ REST API (5000)     │      │ REST API (5000)     │
│ Web Dashboard       │      │ Web Dashboard       │
└──────────┬──────────┘      └──────────┬──────────┘
           │                            │
           │                            │
    ┌──────┴──────────┬────────────────┴──────┬──────────┐
    │                 │                       │          │
    ▼                 ▼                       ▼          ▼
┌────────┐      ┌────────┐              ┌────────┐  ┌────────┐
│Client 1│      │Client 2│              │Client 3│  │Client 4│
├────────┤      ├────────┤              ├────────┤  ├────────┤
│mDNS    │      │mDNS    │              │mDNS    │  │mDNS    │
│Auto-   │      │Auto-   │              │Auto-   │  │Auto-   │
│discover│      │discover│              │discover│  │discover│
│Upload  │      │Upload  │              │Upload  │  │Upload  │
│Only    │      │Only    │              │Only    │  │Only    │
└────────┘      └────────┘              └────────┘  └────────┘

Key Features:
• mDNS (Bonjour): Clients auto-discover hosts on LAN
• Load Balancing: Multiple hosts share analysis load
• WebSocket: Real-time progress updates to all clients
• Blockchain Sync: All nodes share same immutable state
• Failover: Clients fallback to direct blockchain writes
```

### Deployment Steps

---

#### Step B.1: Setup Folder Structure

Create the laptop implementation folder:

```bash
cd /Users/ajiteshsharma/Downloads/Hackathon\ copy
mkdir -p blockchain-laptop/{config,network,web,services,monitoring,scripts}
```

**Folder Structure:**
```
blockchain-laptop/
├── requirements-laptop.txt      # Full dependencies
├── setup_laptop.sh              # Setup script
├── host_node.py                 # Host/coordinator service
├── client_node.py               # Client uploader service
├── README.md                    # Laptop setup guide
├── .env.example                 # Environment template
├── config/
│   ├── host_config.yaml         # Host settings
│   ├── client_config.yaml       # Client settings
│   └── database.yaml            # PostgreSQL configuration
├── network/
│   ├── __init__.py
│   ├── peer_discovery.py        # mDNS/Bonjour discovery
│   ├── load_balancer.py         # Distribute load across hosts
│   ├── sync_manager.py          # Blockchain state sync
│   └── websocket_server.py      # Real-time client updates
├── web/
│   ├── host_api.py              # Full REST API (host)
│   ├── client_uploader.py       # Simple upload API (client)
│   └── templates/
│       ├── host_dashboard.html  # Host web UI
│       ├── client_uploader.html # Client web UI
│       └── network_map.html     # P2P network visualization
├── services/
│   ├── __init__.py
│   ├── detection_service.py     # Full detection pipeline
│   ├── cache_service.py         # PostgreSQL cache
│   └── batch_processor.py       # Batch video processing
├── monitoring/
│   ├── __init__.py
│   ├── network_monitor.py       # Monitor P2P health
│   ├── dashboard.py             # Grafana dashboard
│   └── metrics_collector.py     # Prometheus metrics
└── scripts/
    ├── install_dependencies.sh
    ├── setup_host.sh            # Host-specific setup
    ├── setup_client.sh          # Client-specific setup
    ├── generate_wallets.py      # Create wallets for all nodes
    └── test_network.py          # Test P2P connectivity
```

#### Step B.2: Create Requirements File

Create `blockchain-laptop/requirements-laptop.txt`:

```
# Full dependencies for laptop deployment
flask==3.0.0
flask-cors==4.0.0
flask-socketio==5.3.5
python-socketio==5.10.0

# Blockchain
web3==6.15.0
eth-account==0.10.0
eth-keyfile==0.7.0

# Database
psycopg2-binary==2.9.9  # PostgreSQL adapter
sqlalchemy==2.0.23

# P2P Networking
zeroconf==0.131.0  # mDNS/Bonjour
netifaces==0.11.0

# Deep Learning (full)
torch==2.1.0
torchvision==0.16.0
opencv-python==4.8.1.78
pillow==10.1.0
numpy==1.24.3

# AI APIs
google-generativeai==0.3.2

# Utilities
python-dotenv==1.0.0
pyyaml==6.0.1
requests==2.31.0
redis==5.0.1

# Monitoring
prometheus-client==0.19.0
grafana-client==3.6.0

# Alerts
python-telegram-bot==20.7
discord.py==2.3.2

# Task Queue (optional)
celery[redis]==5.3.4
```

#### Step B.3: Create Host Configuration

Create `blockchain-laptop/config/host_config.yaml`:

```yaml
# Host Laptop Configuration

node:
  type: "host"
  name: "Host-001"
  
  # API settings
  api:
    host: "0.0.0.0"
    port: 5000
    debug: false
    max_content_length: 524288000  # 500MB
  
  # WebSocket settings
  websocket:
    enabled: true
    port: 5001
    cors_allowed_origins: "*"
  
  # Detection settings
  detection:
    use_cnn: true
    use_gemini: true
    gemini_api_key: "${GEMINI_API_KEY}"
    model_path: "../models/best_model.pth"
    confidence_threshold: 0.7
    
    # Parallel processing
    max_workers: 4
    batch_size: 10

# Blockchain settings
blockchain:
  network: "polygon"
  rpc_url: "${POLYGON_RPC_URL}"
  contract_addresses_file: "../shared/contracts/deployed-addresses.json"
  
  # Sync settings
  sync_enabled: true
  sync_interval: 300  # Every 5 minutes
  
  # Transaction settings
  batch_enabled: false  # Host sends immediately
  gas_price_multiplier: 1.1  # Pay 10% above average

# Database (PostgreSQL) cache:
  backend: "postgresql"
  postgresql:
    host: "localhost"
    port: 5432
    database: "deepfake_cache"
    user: "deepfake_user"
    password: "${DB_PASSWORD}"
  
  # Connection pool
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30

# P2P Network
network:
  # mDNS service advertisement
  mdns:
    enabled: true
    service_type: "_deepfake-host._tcp.local."
    service_name: "DeepFake-Host-001"
  
  # Load balancing
  load_balancing:
    enabled: true
    max_concurrent_analyses: 5
    queue_max_size: 100
  
  # Client authentication
  authentication:
    enabled: false  # Set true for production
    require_api_key: false

# Monitoring
monitoring:
  prometheus_enabled: true
  prometheus_port: 9090
  grafana_enabled: true
  grafana_port: 3000
  
  # Health checks
  health_check_interval: 30
  
  # Metrics
  collect_system_metrics: true
  collect_blockchain_metrics: true

# Alerts (same as Pi config)
alerts:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
  
  email:
    enabled: false
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    from_address: "${EMAIL_FROM}"
    to_address: "${EMAIL_TO}"
    password: "${EMAIL_PASSWORD}"

# Logging
logging:
  level: "INFO"
  file: "logs/host_node.log"
  max_size_mb: 100
  backup_count: 5
```

#### Step B.4Create Client Configuration

Create `blockchain-laptop/config/client_config.yaml`:

```yaml
# Client Laptop Configuration

node:
  type: "client"
  name: "Client-001"
  
  # Simple upload API
  api:
    host: "0.0.0.0"
    port: 8080
    debug: false
  
  # Host discovery
  discovery:
    method: "mdns"  # mDNS auto-discovery
    service_type: "_deepfake-host._tcp.local."
    fallback_hosts:  # Manual fallback if mDNS fails
      - "192.168.1.100:5000"
      - "192.168.1.101:5000"
  
  # Direct blockchain access (fallback)
  blockchain_fallback:
    enabled: true
    use_when_host_unavailable: true

# Blockchain settings (for fallback mode)
blockchain:
  network: "polygon"
  rpc_url: "${POLYGON_RPC_URL}"
  contract_addresses_file: "../shared/contracts/deployed-addresses.json"

# Local cache (minimal)
cache:
  backend: "sqlite"
  sqlite_path: "client_cache.db"
  ttl: 3600  # 1 hour

# Logging
logging:
  level: "INFO"
  file: "logs/client_node.log"
  max_size_mb: 50
  backup_count: 3
```

#### Step B.5: Create Peer Discovery Service

Create `blockchain-laptop/network/peer_discovery.py`:

```python
"""
Peer discovery using mDNS/Bonjour for auto-configuration
"""
import logging
import socket
import time
from typing import List, Dict, Optional
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf, ServiceInfo
import netifaces

logger = logging.getLogger(__name__)


class HostDiscoveryListener(ServiceListener):
    """Listener for deepfake host services"""
    
    def __init__(self):
        self.discovered_hosts = []
    
    def add_service(self, zc: Zeroconf, type_: str, name: str):
        info = zc.get_service_info(type_, name)
        if info:
            host_info = {
                'name': name,
                'address': socket.inet_ntoa(info.addresses[0]),
                'port': info.port,
                'properties': info.properties
            }
            self.discovered_hosts.append(host_info)
            logger.info(f"Discovered host: {host_info['address']}:{host_info['port']}")
    
    def remove_service(self, zc: Zeroconf, type_: str, name: str):
        self.discovered_hosts = [h for h in self.discovered_hosts if h['name'] != name]
        logger.info(f"Host removed: {name}")
    
    def update_service(self, zc: Zeroconf, type_: str, name: str):
        logger.debug(f"Host updated: {name}")


class PeerDiscovery:
    """
    Manages peer discovery for client-host connections
    """
    
    def __init__(self, service_type: str = "_deepfake-host._tcp.local."):
        self.service_type = service_type
        self.zeroconf = None
        self.browser = None
        self.listener = None
    
    def start_discovery(self, timeout: int = 10) -> List[Dict]:
        """
        Discover available hosts on the network
        
        Args:
            timeout: Discovery timeout in seconds
            
        Returns:
            List of discovered host dictionaries
        """
        logger.info(f"Starting host discovery (timeout: {timeout}s)...")
        
        self.zeroconf = Zeroconf()
        self.listener = HostDiscoveryListener()
        self.browser = ServiceBrowser(self.zeroconf, self.service_type, self.listener)
        
        # Wait for discovery
        time.sleep(timeout)
        
        hosts = self.listener.discovered_hosts
        logger.info(f"Discovery complete: found {len(hosts)} host(s)")
        
        return hosts
    
    def stop_discovery(self):
        """Stop discovery service"""
        if self.zeroconf:
            self.zeroconf.close()
            logger.info("Discovery service stopped")
    
    def advertise_host(self, port: int, properties: Dict = None):
        """
        Advertise this machine as a host (for host nodes)
        
        Args:
            port: API port number
            properties: Optional service properties
        """
        hostname = socket.gethostname()
        local_ip = self._get_local_ip()
        
        info = ServiceInfo(
            self.service_type,
            f"{hostname}.{self.service_type}",
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            properties=properties or {},
            server=f"{hostname}.local."
        )
        
        self.zeroconf = Zeroconf()
        self.zeroconf.register_service(info)
        
        logger.info(f"Advertising host service at {local_ip}:{port}")
    
    def _get_local_ip(self) -> str:
        """Get local IP address"""
        try:
            # Get default gateway interface
            gateways = netifaces.gateways()
            default_interface = gateways['default'][netifaces.AF_INET][1]
            
            # Get IP of that interface
            addrs = netifaces.ifaddresses(default_interface)
            ip = addrs[netifaces.AF_INET][0]['addr']
            
            return ip
        except:
            # Fallback method
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            return ip


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    discovery = PeerDiscovery()
    
    # For client: discover hosts
    print("Discovering hosts...")
    hosts = discovery.start_discovery(timeout=5)
    
    for host in hosts:
        print(f"Found host: {host['address']}:{host['port']}")
    
    discovery.stop_discovery()
    
    # For host: advertise service
    # discovery.advertise_host(port=5000, properties={'version': '1.0'})
    # Keep running...
```

#### Step B.6: Create Host Node Service

Create `blockchain-laptop/host_node.py`:

```python
"""
Host Node: Coordinator laptop that runs full detection pipeline
"""
import logging
import os
import yaml
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

# Import existing modules
import sys
sys.path.append(str(Path(__file__).parent.parent))

from shared.blockchain.web3_client import Web3Client
from shared.alerts.alert_listener import AlertListener
from src.pipeline.enhanced_detector import EnhancedDeepfakeDetector
from blockchain_laptop.network.peer_discovery import PeerDiscovery

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
with open('blockchain-laptop/config/host_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Initialize Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = config['node']['api']['max_content_length']
CORS(app)

# Initialize SocketIO for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize components
web3_client = Web3Client()
detector = EnhancedDeepfakeDetector()
peer_discovery = PeerDiscovery()

# Upload folder
UPLOAD_FOLDER = Path("blockchain-laptop/uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        balance = web3_client.get_account_balance()
        return jsonify({
            'status': 'healthy',
            'node_type': 'host',
            'blockchain_connected': True,
            'wallet_balance': balance,
            'detector_ready': detector is not None
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.route('/api/analyze', methods=['POST'])
def analyze_video():
    """
    Main video analysis endpoint
    Accepts video upload and returns detection results
    """
    try:
        # Check if file present
        if 'video' not in request.files:
            return jsonify({'error': 'No video file provided'}), 400
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = UPLOAD_FOLDER / filename
        file.save(str(filepath))
        
        logger.info(f"Analyzing video: {filename}")
        
        # Emit progress update via WebSocket
        socketio.emit('analysis_started', {'filename': filename})
        
        # Run detection
        result = detector.analyze_video(str(filepath))
        
        socketio.emit('detection_complete', {
            'filename': filename,
            'is_deepfake': result.is_deepfake,
            'confidence': result.confidence
        })
        
        # Get client IP
        client_ip = request.remote_addr
        
        # Register on blockchain
        logger.info("Registering result on blockchain...")
        tx_hash = web3_client.register_video_on_chain(
            content_hash=result.video_hash,
            perceptual_hash=result.perceptual_hash,
            is_deepfake=result.is_deepfake,
            confidence=result.confidence,
            lipsync_score=result.lipsync_score,
            fact_check_score=result.fact_check_score,
            ip_hash=_hash_ip(client_ip),
            country="Unknown",  # Implement geo lookup
            city="Unknown",
            latitude=0.0,
            longitude=0.0,
            metadata={
                'filename': filename,
                'detection_method': result.detection_method,
                'processing_time': result.processing_time
            }
        )
        
        socketio.emit('blockchain_confirmed', {
            'filename': filename,
            'tx_hash': tx_hash
        })
        
        # Clean up uploaded file
        filepath.unlink()
        
        return jsonify({
            'success': True,
            'result': {
                'is_deepfake': result.is_deepfake,
                'confidence': result.confidence,
                'video_hash': result.video_hash,
                'lipsync_score': result.lipsync_score,
                'fact_check_score': result.fact_check_score
            },
            'blockchain': {
                'tx_hash': tx_hash,
                'network': 'polygon'
            },
            'processing_time': result.processing_time
        })
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    try:
        # Query blockchain for stats
        video_registry = web3_client.contracts['VideoRegistry']
        total_videos = video_registry.functions.getTotalVideos().call()
        
        alert_manager = web3_client.contracts['AlertManager']
        total_alerts = alert_manager.functions.getTotalAlerts().call()
        
        return jsonify({
            'total_videos': total_videos,
            'total_alerts': total_alerts,
            'wallet_balance': web3_client.get_account_balance()
        })
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return jsonify({'error': str(e)}), 500


@socketio.on('connect')
def handle_connect():
    """Handle client WebSocket connection"""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to host node'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")


def _hash_ip(ip: str) -> str:
    """Hash IP address for privacy"""
    import hashlib
    return hashlib.sha256(ip.encode()).hexdigest()[:32]


def start_host_node():
    """Start the host node service"""
    logger.info("="* 50)
    logger.info("Starting DeepFake Detection Host Node")
    logger.info("=" * 50)
    
    # Advertise service via mDNS
    if config['network']['mdns']['enabled']:
        port = config['node']['api']['port']
        peer_discovery.advertise_host(port, properties={'version': '1.0'})
        logger.info("Host service advertised via mDNS")
    
    # Start alert listener in background thread
    alert_listener = AlertListener(web3_client)
    alert_listener.start()
    logger.info("Alert listener started")
    
    # Start Flask + SocketIO server
    host = config['node']['api']['host']
    port = config['node']['api']['port']
    
    logger.info(f"Host node running at http://{host}:{port}")
    logger.info(f"WebSocket available at ws://{host}:{config['node']['websocket']['port']}")
    
    socketio.run(
        app,
        host=host,
        port=port,
        debug=config['node']['api']['debug']
    )


if __name__ == "__main__":
    start_host_node()
```

*(Continue with client node implementation, load balancer, sync manager, setup scripts, testing procedures...)*

---

## Testing & Deployment

### Testing Strategy

**Phase 1: Unit Tests**
- Smart contract tests (Hardhat)
- Web3 client tests (mock blockchain)
- Detection pipeline tests

**Phase 2: Integration Tests**
- End-to-end video upload → blockchain
- Alert system tests
- P2P network tests (laptop implementation)

**Phase 3: Testnet Deployment**
- Deploy to Polygon Mumbai
- Run for 1 week with test videos
- Monitor gas costs, performance

**Phase 4: Mainnet Migration**
- Deploy to Polygon mainnet
- Gradual rollout (Pi first, then laptops)
- Monitor for 2 weeks before full adoption

---

## Cost Analysis

### Polygon Transaction Costs

| Operation | Gas Estimate | Cost (at 30 gwei) | Monthly Cost (1000 videos) |
|-----------|--------------|-------------------|---------------------------|
| Register Video | 500,000 gas | ~$0.005 | ~$5 |
| Record Spread Event | 300,000 gas | ~$0.003 | ~$3 |
| Create Alert | 150,000 gas | ~$0.0015 | ~$1.50 |
| **Total** | - | - | **~$9.50/month** |

**Pi Batching Savings**: Batch 20 transactions → Save ~60% on gas costs → **~$4/month**

---

## Timeline

### Overall Implementation Timeline

| Phase | Duration | Parallel Work Possible? |
|-------|----------|------------------------|
| **Shared Infrastructure** | 6-8 days | No (foundation required) |
| **Pi Implementation** | 5-7 days | Yes (parallel with laptop)|
| **Laptop Implementation** | 6-8 days | Yes (parallel with Pi) |
| **Testing & Integration** | 3-5 days | No (requires both complete) |
| **Documentation & Deployment** | 2-3 days | Partial |
| **TOTAL (Sequential)** | 22-31 days | |
| **TOTAL (Optimized)** | 17-24 days | With parallel development |

### Recommended Schedule

**Week 1-2**: Shared infrastructure (contracts + Web3 integration)  
**Week 3**: Pi + Laptop implementations in parallel  
**Week 4**: Testing, debugging, documentation  
**Week 5**: Testnet deployment & monitoring  
**Week 6**: Mainnet deployment & handoff

---

## Next Steps

1. ✅ **Review this plan** - Confirm approach and technology choices
2. 📝 **Create tasks** - Break down into implementable tickets
3. 🔨 **Start Phase 1** - Deploy smart contracts to Mumbai testnet
4. 🧪 **Test early** - Validate blockchain integration before building Pi/laptop layers
5. 📊 **Monitor costs** - Track gas usage during testing
6. 📖 **Document** - Keep deployment guides updated as you build

---

## Support & Resources

**Polygon Documentation**: https://polygon.technology/developers  
**Hardhat Docs**: https://hardhat.org/docs  
**Web3.py Docs**: https://web3py.readthedocs.io/  
**Raspberry Pi Docs**: https://www.raspberrypi.com/documentation/  

**Questions?** Refer to `shared/docs/` for detailed API documentation.

---

**Document Version:** 1.0  
**Last Updated:** February 13, 2026  
**Status:** Ready for Implementation ✅
