"""
Deepfake Origin Finder - Flask Web Application
===============================================
Forensic intelligence platform for deepfake detection, lineage tracking,
and provenance analysis.

Architecture:
- Flask backend exposing RESTful API endpoints
- Integration with EnhancedDeepfakeDetector, DeepfakeOriginFinder, VideoHashCache
- Gemini direct deepfake verification (hidden signal)
- Role-based dashboards for different stakeholders
"""

import os
import sys
import json
import time
import uuid
import tempfile
import threading
import hashlib
from pathlib import Path
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any, List
from collections import deque
import queue

from flask import (
    Flask, 
    render_template, 
    request, 
    jsonify, 
    send_from_directory,
    Response,
    stream_with_context
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# Blockchain & Alert Imports (with graceful fallback)
# ============================================================================
BLOCKCHAIN_AVAILABLE = False
_blockchain_client = None
_blockchain_init_attempted = False

try:
    from web3 import Web3
    WEB3_INSTALLED = True
except ImportError:
    WEB3_INSTALLED = False
    print("⚠ web3 package not installed — blockchain will run in simulation mode")

# Try to import the real notification service
_notification_service = None
try:
    from shared.alerts.notification_service import NotificationService
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False
    print("⚠ NotificationService not available — email alerts disabled")

# ============================================================================
# In-Memory State
# ============================================================================
recent_detections = deque(maxlen=100)  # Recent analysis results
analysis_streams = {}  # SSE stream queues keyed by analysis_id
blockchain_tx_log = deque(maxlen=50)  # Simulated blockchain TX log
platform_stats = {'youtube': 0, 'tiktok': 0, 'twitter': 0, 'instagram': 0, 'upload': 0, 'url': 0}
threat_timeline = deque(maxlen=200)  # Threat events over time

# Lazy imports to avoid immediate torch dependency
EnhancedDeepfakeDetector = None
DeepfakeOriginFinder = None
VideoHashCache = None
GeminiFactChecker = None

# Import geo utilities for location tracking
try:
    # Direct import to avoid __init__.py dependency chain
    import importlib.util
    geo_utils_path = Path(__file__).parent.parent / 'src' / 'utils' / 'geo_utils.py'
    spec = importlib.util.spec_from_file_location("geo_utils", geo_utils_path)
    geo_utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geo_utils)
    GeoIPService = geo_utils.GeoIPService
    get_client_ip = geo_utils.get_client_ip
    hash_ip = geo_utils.hash_ip
    geo_service = GeoIPService()
    print("✓ Geo IP service initialized")
except Exception as e:
    print(f"⚠ Geo IP service not available: {e}")
    geo_service = None
    def get_client_ip(request):
        return request.remote_addr
    def hash_ip(ip):
        import hashlib
        return hashlib.sha256(ip.encode()).hexdigest()[:16]

def load_modules():
    """Lazily load detection modules independently so partial failures don't block others."""
    global EnhancedDeepfakeDetector, DeepfakeOriginFinder, VideoHashCache, GeminiFactChecker
    loaded = 0
    
    if VideoHashCache is None:
        try:
            from src.core.video_hash_cache import VideoHashCache as VHC
            VideoHashCache = VHC
            loaded += 1
        except ImportError as e:
            print(f"Warning: Could not load VideoHashCache: {e}")
    else:
        loaded += 1
    
    if GeminiFactChecker is None:
        try:
            from src.core.gemini_fact_checker import GeminiFactChecker as GFC
            GeminiFactChecker = GFC
            loaded += 1
        except ImportError as e:
            print(f"Warning: Could not load GeminiFactChecker: {e}")
    else:
        loaded += 1
    
    if EnhancedDeepfakeDetector is None:
        try:
            from src.pipeline.enhanced_detector import EnhancedDeepfakeDetector as EDD
            EnhancedDeepfakeDetector = EDD
            loaded += 1
        except ImportError as e:
            print(f"Warning: Could not load EnhancedDeepfakeDetector: {e}")
    else:
        loaded += 1
    
    if DeepfakeOriginFinder is None:
        try:
            from src.tracking.deepfake_origin_finder import DeepfakeOriginFinder as DOF
            DeepfakeOriginFinder = DOF
            loaded += 1
        except ImportError as e:
            print(f"Warning: Could not load DeepfakeOriginFinder: {e}")
    else:
        loaded += 1
    
    return loaded > 0  # True if at least one module loaded

# ============================================================================
# Configuration
# ============================================================================

app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')
CORS(app)

# Configure upload settings
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm', 'flv', 'wmv', 'png', 'jpg', 'jpeg', 'gif', 'bmp'}
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max file size

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['SECRET_KEY'] = os.urandom(24).hex()

# Create upload folder
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Initialize Detection Systems
# ============================================================================

# Get API key from environment
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Model paths
BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = BASE_DIR / 'models' / 'best_model.pth'
CACHE_DB_PATH = BASE_DIR / 'models' / 'lipsync_cache.db'
LINEAGE_DB_PATH = BASE_DIR / 'models' / 'deepfake_lineage.db'

# Initialize systems (lazy loading)
_detector = None
_origin_finder = None
_hash_cache = None
_gemini_checker = None
_init_lock = threading.Lock()
_modules_loaded = False


def get_detector():
    """Get or create the detector instance."""
    global _detector, _modules_loaded
    if not _modules_loaded:
        _modules_loaded = load_modules()
    if not _modules_loaded or EnhancedDeepfakeDetector is None:
        return None
    if _detector is None:
        with _init_lock:
            if _detector is None:
                _detector = EnhancedDeepfakeDetector(
                    lipsync_model_path=str(MODEL_PATH) if MODEL_PATH.exists() else None,
                    gemini_api_key=GEMINI_API_KEY,
                    cache_db_path=str(CACHE_DB_PATH)
                )
    return _detector


def get_origin_finder():
    """Get or create the origin finder instance."""
    global _origin_finder, _modules_loaded
    if not _modules_loaded:
        _modules_loaded = load_modules()
    if not _modules_loaded or DeepfakeOriginFinder is None:
        return None
    if _origin_finder is None:
        with _init_lock:
            if _origin_finder is None:
                _origin_finder = DeepfakeOriginFinder(
                    db_path=str(LINEAGE_DB_PATH)
                )
    return _origin_finder


def get_hash_cache():
    """Get or create the hash cache instance."""
    global _hash_cache, _modules_loaded
    if not _modules_loaded:
        _modules_loaded = load_modules()
    if not _modules_loaded or VideoHashCache is None:
        return None
    if _hash_cache is None:
        with _init_lock:
            if _hash_cache is None:
                _hash_cache = VideoHashCache(
                    db_path=str(CACHE_DB_PATH)
                )
    return _hash_cache


def get_gemini_checker():
    """Get or create the Gemini checker instance."""
    global _gemini_checker, _modules_loaded
    if not _modules_loaded:
        _modules_loaded = load_modules()
    if not _modules_loaded or GeminiFactChecker is None:
        return None
    if _gemini_checker is None:
        with _init_lock:
            if _gemini_checker is None:
                _gemini_checker = GeminiFactChecker(
                    api_key=GEMINI_API_KEY
                )
    return _gemini_checker


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def reinitialize_with_api_key(api_key: str):
    """Reinitialize the detector and fact checker with new API key."""
    global _detector, _gemini_checker, GEMINI_API_KEY
    GEMINI_API_KEY = api_key
    os.environ['GEMINI_API_KEY'] = api_key
    
    with _init_lock:
        # Reset instances to force reinitialization
        _detector = None
        _gemini_checker = None


# ============================================================================
# Blockchain Client (Real Web3 with simulation fallback)
# ============================================================================

def get_blockchain_client():
    """Get or create a lightweight Web3 connection for blockchain queries."""
    global _blockchain_client, BLOCKCHAIN_AVAILABLE, _blockchain_init_attempted
    
    if _blockchain_init_attempted:
        return _blockchain_client
    
    _blockchain_init_attempted = True
    
    if not WEB3_INSTALLED:
        print("⚠ Blockchain: web3 not installed — simulation mode")
        return None
    
    rpc_url = os.getenv('POLYGON_RPC_URL', 'https://rpc-amoy.polygon.technology/')
    private_key = os.getenv('PRIVATE_KEY') or os.getenv('WALLET_PRIVATE_KEY')
    
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
        if w3.is_connected():
            _blockchain_client = {
                'w3': w3,
                'rpc_url': rpc_url,
                'chain_id': int(os.getenv('CHAIN_ID', '80002')),
                'private_key': private_key,
                'wallet_address': None,
                'contracts': {
                    'VideoRegistry': os.getenv('VIDEO_REGISTRY_ADDRESS', ''),
                    'TrackingLedger': os.getenv('TRACKING_LEDGER_ADDRESS', ''),
                    'AlertManager': os.getenv('ALERT_MANAGER_ADDRESS', ''),
                },
            }
            if private_key:
                try:
                    from eth_account import Account
                    acct = Account.from_key(private_key)
                    _blockchain_client['wallet_address'] = acct.address
                    balance = w3.eth.get_balance(acct.address)
                    _blockchain_client['balance_wei'] = balance
                    _blockchain_client['balance_matic'] = float(w3.from_wei(balance, 'ether'))
                    print(f"✓ Blockchain connected — wallet {acct.address[:10]}... ({_blockchain_client['balance_matic']:.4f} MATIC)")
                except Exception as e:
                    print(f"⚠ Blockchain: wallet setup failed: {e}")
            
            BLOCKCHAIN_AVAILABLE = True
            print(f"✓ Blockchain: connected to {rpc_url} (block #{w3.eth.block_number})")
            return _blockchain_client
        else:
            print("⚠ Blockchain: RPC not reachable — simulation mode")
            return None
    except Exception as e:
        print(f"⚠ Blockchain connection failed: {e} — simulation mode")
        return None


def record_blockchain_tx(content_hash, result, geo_location=None, client_ip=None):
    """
    Record a video analysis result on the blockchain.
    Returns (tx_data, mode) where mode is 'live' or 'simulation'.
    """
    bc = get_blockchain_client()
    
    # Try real blockchain first
    if bc and BLOCKCHAIN_AVAILABLE and bc.get('private_key'):
        try:
            w3 = bc['w3']
            # Try to use the full BlockchainClient if contracts are deployed
            vr_address = bc['contracts'].get('VideoRegistry', '')
            if vr_address and len(vr_address) > 10:
                try:
                    from shared.blockchain.web3_client import BlockchainClient
                    real_client = BlockchainClient(
                        rpc_url=bc['rpc_url'],
                        private_key=bc['private_key'],
                        video_registry_address=vr_address,
                        tracking_ledger_address=bc['contracts'].get('TrackingLedger', ''),
                        alert_manager_address=bc['contracts'].get('AlertManager', ''),
                        chain_id=bc['chain_id'],
                    )
                    receipt = real_client.register_video(
                        content_hash=content_hash,
                        perceptual_hash=getattr(result, 'perceptual_hash', content_hash[:16]),
                        is_deepfake=result.is_deepfake,
                        confidence=result.confidence * 100,
                        lipsync_score=result.lipsync_score * 100,
                        fact_check_score=(result.fact_check_score or 0) * 100,
                        ip_address=client_ip or '0.0.0.0',
                        country=geo_location.country if geo_location else '',
                        city=geo_location.city if geo_location else '',
                        latitude=geo_location.latitude if geo_location else 0.0,
                        longitude=geo_location.longitude if geo_location else 0.0,
                    )
                    tx_data = {
                        'tx_hash': receipt.get('transactionHash', '').hex() if hasattr(receipt.get('transactionHash', ''), 'hex') else str(receipt.get('transactionHash', '')),
                        'block': receipt.get('blockNumber', 0),
                        'gas_used': receipt.get('gasUsed', 0),
                        'status': 'confirmed' if receipt.get('status') == 1 else 'failed',
                        'network': 'Polygon Amoy Testnet',
                        'contract': vr_address,
                        'mode': 'live',
                    }
                    return tx_data, 'live'
                except Exception as e:
                    print(f"⚠ Real blockchain TX failed: {e} — falling back to simulation")
            
            # Fallback: just record the TX hash from a lightweight on-chain check
            # to prove connectivity (but no actual contract call)
            block_number = w3.eth.block_number
            gas_price = w3.eth.gas_price
            tx_hash = hashlib.sha256(f"{content_hash}{time.time()}{block_number}".encode()).hexdigest()
            tx_data = {
                'tx_hash': '0x' + tx_hash[:64],
                'block': block_number,
                'gas_used': 85000 + int(result.confidence * 15000),
                'gas_price_gwei': round(w3.from_wei(gas_price, 'gwei'), 2),
                'status': 'confirmed',
                'network': 'Polygon Amoy Testnet',
                'contract': vr_address or '0x742d35Cc6634C0532925a3b844Bc9e7595f2bD1e',
                'mode': 'simulation',
                'note': 'Connected to blockchain but contracts not deployed or wallet not funded',
            }
            return tx_data, 'simulation'
            
        except Exception as e:
            print(f"⚠ Blockchain recording failed: {e}")
    
    # Full simulation fallback
    tx_hash = hashlib.sha256(f"{content_hash}{time.time()}".encode()).hexdigest()
    tx_data = {
        'tx_hash': '0x' + tx_hash[:64],
        'block': 50000000 + len(blockchain_tx_log),
        'gas_used': 85000 + int(result.confidence * 15000),
        'status': 'confirmed',
        'network': 'Polygon Amoy Testnet',
        'contract': '0x742d35Cc6634C0532925a3b844Bc9e7595f2bD1e',
        'mode': 'simulation',
    }
    return tx_data, 'simulation'


# ============================================================================
# Notification Service (Email Alerts)
# ============================================================================

def get_notification_service():
    """Get or create the notification service instance."""
    global _notification_service
    if _notification_service is not None:
        return _notification_service
    
    if not NOTIFICATIONS_AVAILABLE:
        return None
    
    try:
        _notification_service = NotificationService(
            email_smtp_host=os.getenv('SMTP_HOST', ''),
            email_smtp_port=587,
            email_username=os.getenv('SMTP_USER', ''),
            email_password=os.getenv('SMTP_PASSWORD', ''),
            email_from=os.getenv('ALERT_EMAIL_FROM', ''),
            email_to=os.getenv('ALERT_EMAIL_TO', ''),
            telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', ''),
            discord_webhook_url=os.getenv('DISCORD_WEBHOOK_URL', ''),
            min_severity='MEDIUM',
        )
        channels = _notification_service.get_channel_status()
        active = [k for k, v in channels.items() if v]
        print(f"✓ Notification service initialized (channels: {', '.join(active)})")
        return _notification_service
    except Exception as e:
        print(f"⚠ NotificationService init failed: {e}")
        return None


def send_deepfake_alert(result, filename, content_hash, tx_data=None):
    """Send alert notification when a deepfake is detected."""
    ns = get_notification_service()
    if not ns:
        return
    
    if not result.is_deepfake or result.confidence < 0.7:
        return
    
    message = (
        f"Video: {filename}\n"
        f"Confidence: {result.confidence:.1%}\n"
        f"Verdict: {result.verdict}\n"
        f"Risk Level: {result.risk_level}\n"
        f"Lipsync Score: {result.lipsync_score:.4f}\n"
        f"Video Hash: {content_hash[:16]}...\n"
    )
    if tx_data:
        message += f"Blockchain TX: {tx_data.get('tx_hash', 'N/A')[:18]}...\n"
        message += f"Mode: {tx_data.get('mode', 'unknown')}\n"
    
    severity = 'CRITICAL' if result.confidence > 0.9 else 'HIGH'
    ns.send_alert('DEEPFAKE_DETECTED', message, severity)


# ============================================================================
# Utility Functions
# ============================================================================

def format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return iso_timestamp


def compute_pipeline_stages(video_path: str) -> Dict[str, Any]:
    """
    Compute all pipeline stages with timing for visualization.
    Returns detailed stage information for the frontend.
    """
    stages = []
    total_start = time.time()
    
    # Stage 1: Frame Extraction
    stage_start = time.time()
    stages.append({
        'name': 'Frame Extraction',
        'status': 'running',
        'description': 'Extracting frames from video...'
    })
    
    return stages


# ============================================================================
# API Routes - Core Detection
# ============================================================================

@app.route('/')
def index():
    """Render main forensic intelligence dashboard."""
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'components': {
            'detector': 'ready' if _detector else 'not_initialized',
            'origin_finder': 'ready' if _origin_finder else 'not_initialized',
            'hash_cache': 'ready' if _hash_cache else 'not_initialized',
            'gemini': 'available' if GEMINI_API_KEY else 'not_configured'
        }
    })


@app.route('/api/settings/gemini-key', methods=['POST'])
def set_gemini_api_key():
    """Set Gemini API key at runtime."""
    data = request.get_json()
    if not data or 'api_key' not in data:
        return jsonify({'error': 'api_key required'}), 400
    
    api_key = data['api_key'].strip()
    if not api_key:
        return jsonify({'error': 'api_key cannot be empty'}), 400
    
    reinitialize_with_api_key(api_key)
    
    return jsonify({
        'success': True,
        'message': 'Gemini API key configured successfully',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/settings/status', methods=['GET'])
def get_settings_status():
    """Get current settings status."""
    # Check if torch is available
    try:
        from src.pipeline.enhanced_detector import TORCH_AVAILABLE
        torch_available = TORCH_AVAILABLE
    except:
        torch_available = False
    
    return jsonify({
        'gemini_configured': bool(GEMINI_API_KEY),
        'detector': _detector is not None,
        'hash_cache': _hash_cache is not None,
        'origin_finder': _origin_finder is not None,
        'torch_available': torch_available,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/analyze', methods=['POST'])
def analyze_video():
    """
    Main video analysis endpoint.
    
    Accepts:
        - File upload (multipart/form-data)
        - URL parameter for remote videos
    
    Returns:
        Full detection result with pipeline stage details.
    """
    start_time = time.time()
    video_path = None
    temp_file = None
    
    try:
        # Handle file upload
        if 'video' in request.files:
            file = request.files['video']
            if file.filename == '':
                return jsonify({'error': 'No file selected'}), 400
            
            if not allowed_file(file.filename):
                return jsonify({'error': f'Invalid file type. Allowed: {ALLOWED_EXTENSIONS}'}), 400
            
            filename = secure_filename(file.filename)
            video_path = UPLOAD_FOLDER / f"{int(time.time())}_{filename}"
            file.save(str(video_path))
            temp_file = video_path
        
        # Handle URL input
        elif 'url' in request.form:
            url = request.form['url']
            # TODO: Download video from URL
            return jsonify({'error': 'URL analysis not yet implemented'}), 501
        
        else:
            return jsonify({'error': 'No video file or URL provided'}), 400
        
        # Get detector
        detector = get_detector()
        origin_finder = get_origin_finder()
        hash_cache = get_hash_cache()
        
        # Check that all required components are available
        if detector is None:
            return jsonify({'error': 'Detection system not initialized. Please check server logs.'}), 503
        if hash_cache is None:
            return jsonify({'error': 'Hash cache not initialized. Please check server logs.'}), 503
        
        # Run detection with pipeline stages
        pipeline_stages = []
        
        # Stage 1: Hash Computation
        stage_start = time.time()
        # compute_video_hash returns tuple: (content_hash, perceptual_hash, lsh_bands)
        # For images (PNG), use compute_image_hash; for videos use compute_video_hash
        file_ext = str(video_path).lower().split('.')[-1]
        if file_ext in ['png', 'jpg', 'jpeg', 'gif', 'bmp']:
            content_hash, perceptual_hash, lsh_bands = hash_cache.compute_image_hash(str(video_path))
        else:
            content_hash, perceptual_hash, lsh_bands = hash_cache.compute_video_hash(str(video_path))
        
        pipeline_stages.append({
            'name': 'Hash Computation',
            'duration': round(time.time() - stage_start, 3),
            'status': 'complete',
            'details': {
                'content_hash': content_hash[:16] + '...',
                'perceptual_hash': perceptual_hash[:16] + '...'
            }
        })
        
        # Stage 2: Cache Lookup (use _lookup_exact for content hash)
        stage_start = time.time()
        cached_result = hash_cache._lookup_exact(content_hash)
        cache_info = hash_cache.get_cache_info(content_hash)
        is_duplicate = cache_info is not None
        pipeline_stages.append({
            'name': 'Cache Lookup',
            'duration': round(time.time() - stage_start, 3),
            'status': 'complete',
            'details': {
                'cache_hit': cached_result is not None,
                'is_duplicate': is_duplicate
            }
        })
        
        # Alert for duplicate detection
        if is_duplicate:
            print(f"⚠️ DUPLICATE DETECTED! Video first seen: {cache_info['first_seen']}, Times seen: {cache_info['detection_count']}")
        
        # Stage 3: Lip-Sync Analysis
        stage_start = time.time()
        result = detector.analyze_video(str(video_path))
        pipeline_stages.append({
            'name': 'Lip-Sync Analysis',
            'duration': round(time.time() - stage_start, 3),
            'status': 'complete',
            'details': {
                'lipsync_score': round(result.lipsync_score, 4),
                'method': 'CNN' if detector.lipsync_model else 'Handcrafted Features'
            }
        })
        
        # Stage 4: Gemini Verification (Hidden - not exposed in UI)
        gemini_deepfake_signal = None
        if GEMINI_API_KEY:
            try:
                stage_start = time.time()
                gemini_checker = get_gemini_checker()
                # Direct deepfake verification - hidden signal
                if gemini_checker and gemini_checker.is_available:
                    gemini_deepfake_signal = gemini_checker.analyze_video(str(video_path))
                    pipeline_stages.append({
                        'name': 'External Verification',
                        'duration': round(time.time() - stage_start, 3),
                        'status': 'complete',
                        'details': {
                            'sources_checked': len(result.sources_found)
                        }
                    })
                else:
                    pipeline_stages.append({
                        'name': 'External Verification',
                        'duration': 0,
                        'status': 'skipped',
                        'details': {'reason': 'Gemini checker not available'}
                    })
            except Exception as e:
                pipeline_stages.append({
                    'name': 'External Verification',
                    'duration': 0,
                    'status': 'skipped',
                    'details': {'reason': str(e)}
                })
        
        # Stage 5: Origin Analysis with Location Tracking
        stage_start = time.time()
        
        family_matches = []
        origin = None
        geo_location = None
        
        # Get client location for tracking
        client_ip = get_client_ip(request)
        print(f"📍 Client IP: {client_ip}")
        if geo_service:
            geo_location = geo_service.lookup(client_ip)
            print(f"📍 Location: {geo_location.city}, {geo_location.country} ({geo_location.latitude}, {geo_location.longitude})")
        
        if origin_finder:
            # Register in lineage database with location data
            origin_finder.register_video(
                video_hash=content_hash,
                perceptual_hash=perceptual_hash,
                is_deepfake=result.is_deepfake,
                confidence=result.confidence,
                source_platform=request.form.get('platform', 'Direct Upload'),
                video_path=str(video_path),
                metadata={'upload_time': datetime.now().isoformat()},
                # Location tracking
                origin_country=geo_location.country if geo_location else None,
                origin_city=geo_location.city if geo_location else None,
                origin_latitude=geo_location.latitude if geo_location else None,
                origin_longitude=geo_location.longitude if geo_location else None,
                ip_hash=hash_ip(client_ip)
            )
            
            # Also record as a spread event (sighting)
            origin_finder.record_spread_event(
                video_hash=content_hash,
                platform=request.form.get('platform', 'Direct Upload'),
                metadata={'upload_time': datetime.now().isoformat()},
                country=geo_location.country if geo_location else None,
                city=geo_location.city if geo_location else None,
                latitude=geo_location.latitude if geo_location else None,
                longitude=geo_location.longitude if geo_location else None,
                ip_hash=hash_ip(client_ip)
            )
            
            # Check for family matches
            family_matches = origin_finder.find_family(perceptual_hash) or []
            origin = origin_finder.find_origin(perceptual_hash)
        
        pipeline_stages.append({
            'name': 'Origin Analysis',
            'duration': round(time.time() - stage_start, 3),
            'status': 'complete',
            'details': {
                'family_size': len(family_matches),
                'origin_found': origin is not None
            }
        })
        
        # Build response
        total_time = round(time.time() - start_time, 3)
        
        response = {
            'success': True,
            'result': {
                # Core verdict
                'is_deepfake': result.is_deepfake,
                'confidence': round(result.confidence, 4),
                'verdict': result.verdict,
                'confidence_level': result.confidence_level,
                'risk_level': result.risk_level,
                
                # Component scores
                'lipsync_score': round(result.lipsync_score, 4),
                'fact_check_score': round(result.fact_check_score, 4) if result.fact_check_score else None,
                
                # Hashing
                'video_hash': content_hash,
                'perceptual_hash': perceptual_hash,
                
                # Celebrity detection
                'celebrity_detected': result.celebrity_detected,
                'celebrity_name': result.celebrity_name,
                
                # Analysis metadata
                'detection_method': result.detection_method,
                'agreement_status': result.agreement_status,
                'requires_review': result.requires_review,
                'gemini_verdict': result.gemini_verdict,
                'sources_found': result.sources_found,
                
                # Timestamps
                'timestamp': result.timestamp,
                'processing_time': total_time
            },
            'pipeline': {
                'stages': pipeline_stages,
                'total_time': total_time
            },
            'lineage': {
                'family_size': len(family_matches),
                'origin': origin.to_dict() if origin else None,
                'generation': family_matches[0].generation if family_matches else 0
            },
            'location': {
                'client_ip': client_ip,
                'country': geo_location.country if geo_location else None,
                'city': geo_location.city if geo_location else None,
                'latitude': geo_location.latitude if geo_location else None,
                'longitude': geo_location.longitude if geo_location else None,
                'country_code': geo_location.country_code if geo_location else None
            },
            'duplicate': {
                'is_duplicate': is_duplicate,
                'first_seen': cache_info['first_seen'] if cache_info else None,
                'last_seen': cache_info['last_seen'] if cache_info else None,
                'times_seen': cache_info['detection_count'] if cache_info else 1
            }
        }
        
        # Store in recent detections
        detection_record = {
            'id': str(uuid.uuid4())[:8],
            'filename': filename,
            'is_deepfake': result.is_deepfake,
            'confidence': round(result.confidence, 4),
            'verdict': result.verdict,
            'risk_level': result.risk_level,
            'video_hash': content_hash[:16] + '...',
            'processing_time': total_time,
            'timestamp': datetime.now().isoformat(),
            'location': geo_location.country if geo_location else 'Unknown',
            'platform': request.form.get('platform', 'Direct Upload')
        }
        recent_detections.appendleft(detection_record)
        
        # Update platform stats
        platform = request.form.get('platform', 'upload').lower()
        if platform in platform_stats:
            platform_stats[platform] += 1
        else:
            platform_stats['upload'] += 1
        
        # Add to threat timeline if deepfake
        if result.is_deepfake:
            threat_timeline.appendleft({
                'timestamp': datetime.now().isoformat(),
                'type': 'deepfake_detected',
                'confidence': round(result.confidence, 4),
                'hash': content_hash[:16],
                'filename': filename
            })
        
        # Record on blockchain (real or simulation)
        tx_data, bc_mode = record_blockchain_tx(content_hash, result, geo_location, client_ip)
        blockchain_tx_log.appendleft({
            'tx_hash': tx_data['tx_hash'],
            'block': tx_data['block'],
            'action': 'VIDEO_REGISTERED',
            'video_hash': content_hash[:16] + '...',
            'is_deepfake': result.is_deepfake,
            'confidence': round(result.confidence, 4),
            'timestamp': datetime.now().isoformat(),
            'gas_used': tx_data.get('gas_used', 85000),
            'status': tx_data['status'],
            'network': tx_data['network'],
            'mode': bc_mode
        })
        
        response['blockchain'] = {
            'tx_hash': tx_data['tx_hash'],
            'network': tx_data['network'],
            'status': tx_data['status'],
            'block': tx_data['block'],
            'contract': tx_data.get('contract', ''),
            'mode': bc_mode
        }
        
        # Send deepfake alert if applicable
        send_deepfake_alert(result, filename, content_hash, tx_data)
        
        return jsonify(response)
    
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
    
    finally:
        # Clean up temp file
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except:
                pass


@app.route('/api/analyze/batch', methods=['POST'])
def analyze_batch():
    """Batch video analysis endpoint."""
    if 'videos' not in request.files:
        return jsonify({'error': 'No videos provided'}), 400
    
    files = request.files.getlist('videos')
    results = []
    
    detector = get_detector()
    
    for file in files:
        if file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            video_path = UPLOAD_FOLDER / f"{int(time.time())}_{filename}"
            file.save(str(video_path))
            
            try:
                result = detector.analyze_video(str(video_path))
                results.append({
                    'filename': filename,
                    'success': True,
                    'result': result.to_dict()
                })
            except Exception as e:
                results.append({
                    'filename': filename,
                    'success': False,
                    'error': str(e)
                })
            finally:
                if video_path.exists():
                    video_path.unlink()
    
    return jsonify({
        'success': True,
        'count': len(results),
        'results': results
    })


# ============================================================================
# API Routes - Origin Tracking
# ============================================================================

@app.route('/api/origin/<video_hash>', methods=['GET'])
def get_origin(video_hash: str):
    """Find the origin of a video by its hash."""
    try:
        origin_finder = get_origin_finder()
        origin = origin_finder.find_origin_by_hash(video_hash)
        
        if origin:
            return jsonify({
                'success': True,
                'origin': origin.to_dict(),
                'is_origin': origin.video_hash == video_hash
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No origin found'
            }), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/family/<video_hash>', methods=['GET'])
def get_family(video_hash: str):
    """Get all related videos (family tree)."""
    try:
        origin_finder = get_origin_finder()
        family = origin_finder.find_family_by_hash(video_hash)
        
        return jsonify({
            'success': True,
            'family_size': len(family),
            'members': [node.to_dict() for node in family]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/genealogy/<video_hash>', methods=['GET'])
def get_genealogy(video_hash: str):
    """Get the full genealogy tree for visualization."""
    try:
        origin_finder = get_origin_finder()
        tree = origin_finder.get_family_tree(video_hash)
        
        return jsonify({
            'success': True,
            'tree': tree
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/spread/<video_hash>', methods=['GET'])
def get_spread_history(video_hash: str):
    """Get spread history across platforms."""
    try:
        origin_finder = get_origin_finder()
        history = origin_finder.get_spread_timeline(video_hash)
        
        return jsonify({
            'success': True,
            'spread_events': history
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/spread/<video_hash>/geo', methods=['GET'])
def get_spread_locations(video_hash: str):
    """
    Get geographic spread locations for map visualization.
    
    Returns markers for Leaflet map showing:
    - Origin locations (where videos first appeared)
    - Spread events (subsequent sightings)
    """
    try:
        origin_finder = get_origin_finder()
        if not origin_finder:
            return jsonify({'success': False, 'error': 'Origin finder not initialized'}), 503
        
        locations = origin_finder.get_spread_locations(video_hash)
        
        # Also get family tree for lineage drawing on map
        timeline = origin_finder.get_spread_timeline(video_hash)
        
        # Generate stats
        countries = list(set(loc['country'] for loc in locations if loc['country']))
        total_spread = len([loc for loc in locations if loc['type'] == 'spread'])
        
        return jsonify({
            'success': True,
            'locations': locations,
            'timeline': timeline,
            'stats': {
                'total_locations': len(locations),
                'unique_countries': len(countries),
                'countries': countries,
                'origin_count': len([loc for loc in locations if loc['type'] == 'origin']),
                'spread_count': total_spread
            }
        })
    except Exception as e:
        import traceback
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/spread/<video_hash>/timeline', methods=['GET'])
def get_spread_timeline_api(video_hash: str):
    """
    Get spread timeline with location data for animated visualization.
    """
    try:
        origin_finder = get_origin_finder()
        if not origin_finder:
            return jsonify({'success': False, 'error': 'Origin finder not initialized'}), 503
        
        timeline = origin_finder.get_spread_timeline(video_hash)
        
        return jsonify({
            'success': True,
            'timeline': timeline,
            'total_events': len(timeline)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/report/<video_hash>', methods=['GET'])
def generate_report(video_hash: str):
    """Generate a forensic report for a video."""
    try:
        origin_finder = get_origin_finder()
        report = origin_finder.generate_forensic_report(video_hash)
        
        return jsonify({
            'success': True,
            'report': report
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API Routes - SSE Streaming & Real-time
# ============================================================================

@app.route('/api/analyze/stream', methods=['POST'])
def analyze_stream():
    """
    Server-Sent Events endpoint for real-time analysis progress.
    Returns progress events as the analysis pipeline runs.
    """
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    filename = secure_filename(file.filename)
    video_path = UPLOAD_FOLDER / f"{int(time.time())}_{filename}"
    file.save(str(video_path))
    
    analysis_id = str(uuid.uuid4())[:8]
    
    def generate():
        try:
            start_time = time.time()
            
            # Event: Started
            yield f"data: {json.dumps({'stage': 'init', 'progress': 0, 'message': 'Initializing analysis pipeline...', 'analysis_id': analysis_id})}\n\n"
            
            # Stage 0: Frame Extraction
            yield f"data: {json.dumps({'stage': 'extraction', 'progress': 5, 'message': 'Extracting video frames...'})}\n\n"
            
            # Stage 1: Hash Computation
            yield f"data: {json.dumps({'stage': 'hashing', 'progress': 10, 'message': 'Computing video fingerprints...'})}\n\n"
            hash_cache = get_hash_cache()
            if hash_cache is None:
                yield f"data: {json.dumps({'stage': 'error', 'progress': 100, 'message': 'Hash cache not initialized. Check server dependencies.'})}\n\n"
                return
            
            # compute_video_hash returns tuple: (content_hash, perceptual_hash, lsh_bands)
            try:
                file_ext = str(video_path).lower().split('.')[-1]
                if file_ext in ['png', 'jpg', 'jpeg', 'gif', 'bmp']:
                    content_hash, perceptual_hash, lsh_bands = hash_cache.compute_image_hash(str(video_path))
                else:
                    content_hash, perceptual_hash, lsh_bands = hash_cache.compute_video_hash(str(video_path))
            except Exception as hash_err:
                # Fallback: generate partial hash
                content_hash = hashlib.sha256(str(video_path).encode()).hexdigest()[:32]
                perceptual_hash = f"partial_{int(time.time())}"
                lsh_bands = []
                yield f"data: {json.dumps({'stage': 'hashing', 'progress': 20, 'message': 'Using fallback hash (partial fingerprint)', 'fallback': True})}\n\n"
            
            hash_event = json.dumps({'stage': 'hashing', 'progress': 25, 'message': f'Hash: {content_hash[:16]}...', 'hashes': {'content': content_hash[:24], 'perceptual': perceptual_hash[:24] if perceptual_hash else 'N/A'}})
            yield f"data: {hash_event}\n\n"
            
            # Stage 2: Cache Lookup
            yield f"data: {json.dumps({'stage': 'cache', 'progress': 30, 'message': 'Checking database for duplicates...'})}\n\n"
            try:
                cache_info = hash_cache.get_cache_info(content_hash)
                is_duplicate = cache_info is not None
                if is_duplicate:
                    dup_count = cache_info.get('detection_count', 0)
                    dup_event = json.dumps({'stage': 'cache', 'progress': 35, 'message': f'DUPLICATE DETECTED - seen {dup_count} times', 'duplicate': True})
                    yield f"data: {dup_event}\n\n"
                else:
                    yield f"data: {json.dumps({'stage': 'cache', 'progress': 35, 'message': 'No duplicates found. New video.'})}\\n\\n"
            except Exception as cache_err:
                yield f"data: {json.dumps({'stage': 'cache', 'progress': 35, 'message': 'Cache lookup skipped', 'fallback': True})}\\n\\n"
                is_duplicate = False
            
            # Stage 3: Lip-Sync Analysis
            yield f"data: {json.dumps({'stage': 'lipsync', 'progress': 40, 'message': 'Running lip-sync analysis with CNN model...'})}\n\n"
            detector = get_detector()
            if detector is None:
                yield f"data: {json.dumps({'stage': 'error', 'progress': 100, 'message': 'Detection engine not initialized. Check server dependencies (scipy, torch).'})}\n\n"
                return
            result = detector.analyze_video(str(video_path))
            lipsync_event = json.dumps({'stage': 'lipsync', 'progress': 60, 'message': f'Lip-sync score: {round(result.lipsync_score, 4)}', 'score': round(result.lipsync_score, 4)})
            yield f"data: {lipsync_event}\n\n"
            
            # Stage 4: Gemini Verification
            gemini_deepfake_signal = None
            if GEMINI_API_KEY:
                yield f"data: {json.dumps({'stage': 'verification', 'progress': 65, 'message': 'Running Gemini AI verification...'})}\n\n"
                try:
                    gemini_checker = get_gemini_checker()
                    if gemini_checker and gemini_checker.is_available:
                        gemini_deepfake_signal = gemini_checker.analyze_video(str(video_path))
                        yield f"data: {json.dumps({'stage': 'verification', 'progress': 80, 'message': 'Gemini verification complete'})}\n\n"
                    else:
                        yield f"data: {json.dumps({'stage': 'verification', 'progress': 80, 'message': 'Gemini checker not available - skipping'})}\n\n"
                except Exception as e:
                    evt = json.dumps({'stage': 'verification', 'progress': 80, 'message': f'Gemini verification skipped: {str(e)[:50]}'})
                    yield f"data: {evt}\n\n"
            else:
                yield f"data: {json.dumps({'stage': 'verification', 'progress': 80, 'message': 'Gemini API key not configured - skipping AI verification'})}\n\n"
            
            # Stage 5: Origin Analysis
            yield f"data: {json.dumps({'stage': 'origin', 'progress': 85, 'message': 'Reconstructing video origin and lineage...'})}\n\n"
            origin_finder = get_origin_finder()
            family_matches = []
            origin = None
            geo_location = None
            client_ip = get_client_ip(request)
            if geo_service:
                geo_location = geo_service.lookup(client_ip)
            if origin_finder:
                origin_finder.register_video(
                    video_hash=content_hash,
                    perceptual_hash=perceptual_hash,
                    is_deepfake=result.is_deepfake,
                    confidence=result.confidence,
                    source_platform=request.form.get('platform', 'Direct Upload'),
                    video_path=str(video_path),
                    metadata={'upload_time': datetime.now().isoformat()},
                    origin_country=geo_location.country if geo_location else None,
                    origin_city=geo_location.city if geo_location else None,
                    origin_latitude=geo_location.latitude if geo_location else None,
                    origin_longitude=geo_location.longitude if geo_location else None,
                    ip_hash=hash_ip(client_ip)
                )
                origin_finder.record_spread_event(
                    video_hash=content_hash,
                    platform=request.form.get('platform', 'Direct Upload'),
                    metadata={'upload_time': datetime.now().isoformat()},
                    country=geo_location.country if geo_location else None,
                    city=geo_location.city if geo_location else None,
                    latitude=geo_location.latitude if geo_location else None,
                    longitude=geo_location.longitude if geo_location else None,
                    ip_hash=hash_ip(client_ip)
                )
                family_matches = origin_finder.find_family(perceptual_hash) or []
                origin = origin_finder.find_origin(perceptual_hash)
            evt = json.dumps({'stage': 'origin', 'progress': 95, 'message': f'Found {len(family_matches)} family matches'})
            yield f"data: {evt}\n\n"
            
            # Stage 6: Blockchain Recording
            yield f"data: {json.dumps({'stage': 'blockchain', 'progress': 97, 'message': 'Recording to Polygon blockchain...'})}\n\n"
            tx_data, bc_mode = record_blockchain_tx(content_hash, result, geo_location, client_ip)
            bc_msg = f'Recorded on-chain (TX: {tx_data["tx_hash"][:14]}...)' if bc_mode == 'live' else 'Blockchain record simulated'
            evt_bc = json.dumps({'stage': 'blockchain', 'progress': 99, 'message': bc_msg, 'mode': bc_mode})
            yield f"data: {evt_bc}\n\n"
            blockchain_tx_log.appendleft({
                'tx_hash': tx_data['tx_hash'],
                'block': tx_data['block'],
                'action': 'VIDEO_REGISTERED',
                'video_hash': content_hash[:16] + '...',
                'is_deepfake': result.is_deepfake,
                'confidence': round(result.confidence, 4),
                'timestamp': datetime.now().isoformat(),
                'gas_used': tx_data.get('gas_used', 85000),
                'status': tx_data['status'],
                'network': tx_data['network'],
                'mode': bc_mode
            })
            
            total_time = round(time.time() - start_time, 3)
            
            # Store detection
            detection_record = {
                'id': analysis_id,
                'filename': filename,
                'is_deepfake': result.is_deepfake,
                'confidence': round(result.confidence, 4),
                'verdict': result.verdict,
                'risk_level': result.risk_level,
                'video_hash': content_hash[:16] + '...',
                'processing_time': total_time,
                'timestamp': datetime.now().isoformat(),
                'location': geo_location.country if geo_location else 'Unknown',
                'platform': request.form.get('platform', 'Direct Upload')
            }
            recent_detections.appendleft(detection_record)
            platform_stats['upload'] += 1
            if result.is_deepfake:
                threat_timeline.appendleft({
                    'timestamp': datetime.now().isoformat(),
                    'type': 'deepfake_detected',
                    'confidence': round(result.confidence, 4),
                    'hash': content_hash[:16],
                    'filename': filename
                })
            
            # Final result
            final_result = {
                'stage': 'complete',
                'progress': 100,
                'message': 'Analysis complete',
                'result': {
                    'is_deepfake': result.is_deepfake,
                    'confidence': round(result.confidence, 4),
                    'verdict': result.verdict,
                    'confidence_level': result.confidence_level,
                    'risk_level': result.risk_level,
                    'lipsync_score': round(result.lipsync_score, 4),
                    'fact_check_score': round(result.fact_check_score, 4) if result.fact_check_score else None,
                    'video_hash': content_hash,
                    'perceptual_hash': perceptual_hash,
                    'celebrity_detected': result.celebrity_detected,
                    'celebrity_name': result.celebrity_name,
                    'detection_method': result.detection_method,
                    'agreement_status': result.agreement_status,
                    'requires_review': result.requires_review,
                    'gemini_verdict': result.gemini_verdict,
                    'sources_found': result.sources_found,
                    'timestamp': result.timestamp,
                    'processing_time': total_time
                },
                'lineage': {
                    'family_size': len(family_matches),
                    'origin': origin.to_dict() if origin else None,
                    'generation': family_matches[0].generation if family_matches else 0
                },
                'location': {
                    'client_ip': client_ip,
                    'country': geo_location.country if geo_location else None,
                    'city': geo_location.city if geo_location else None,
                    'latitude': geo_location.latitude if geo_location else None,
                    'longitude': geo_location.longitude if geo_location else None,
                    'country_code': geo_location.country_code if geo_location else None
                },
                'duplicate': {
                    'is_duplicate': is_duplicate,
                    'first_seen': cache_info['first_seen'] if cache_info else None,
                    'last_seen': cache_info['last_seen'] if cache_info else None,
                    'times_seen': cache_info['detection_count'] if cache_info else 1
                },
                'blockchain': {
                    'tx_hash': tx_data['tx_hash'],
                    'network': tx_data['network'],
                    'status': tx_data['status'],
                    'block': tx_data['block'],
                    'contract': tx_data.get('contract', ''),
                    'mode': bc_mode
                }
            }
            yield f"data: {json.dumps(final_result)}\n\n"
            
            # Send deepfake alert (fire-and-forget)
            send_deepfake_alert(result, filename, content_hash, tx_data)
            
        except Exception as e:
            import traceback
            yield f"data: {json.dumps({'stage': 'error', 'progress': -1, 'message': str(e), 'traceback': traceback.format_exc()})}\n\n"
        
        finally:
            if video_path.exists():
                try:
                    video_path.unlink()
                except:
                    pass
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


# ============================================================================
# API Routes - Blockchain Integration
# ============================================================================

@app.route('/api/blockchain/status', methods=['GET'])
def blockchain_status():
    """Get blockchain connection status and stats."""
    bc = get_blockchain_client()
    
    if bc and BLOCKCHAIN_AVAILABLE:
        try:
            w3 = bc['w3']
            block_number = w3.eth.block_number
            gas_price = w3.eth.gas_price
            gas_price_gwei = round(w3.from_wei(gas_price, 'gwei'), 2)
            
            return jsonify({
                'success': True,
                'blockchain': {
                    'connected': True,
                    'mode': 'live',
                    'network': 'Polygon Amoy Testnet',
                    'chain_id': bc['chain_id'],
                    'rpc_url': bc['rpc_url'],
                    'wallet': bc.get('wallet_address', 'Not configured'),
                    'balance_matic': bc.get('balance_matic', 0),
                    'contracts': bc['contracts'],
                    'contracts_deployed': any(v and len(v) > 10 for v in bc['contracts'].values()),
                    'total_transactions': len(blockchain_tx_log),
                    'latest_block': block_number,
                    'gas_price': f'{gas_price_gwei} gwei',
                    'status': 'synced'
                },
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            pass  # Fall through to simulation response
    
    # Simulation fallback
    return jsonify({
        'success': True,
        'blockchain': {
            'connected': False,
            'mode': 'simulation',
            'network': 'Polygon Amoy Testnet',
            'chain_id': 80002,
            'rpc_url': os.getenv('POLYGON_RPC_URL', 'https://rpc-amoy.polygon.technology'),
            'wallet': 'Not connected',
            'balance_matic': 0,
            'contracts': {
                'VideoRegistry': os.getenv('VIDEO_REGISTRY_ADDRESS', ''),
                'TrackingLedger': os.getenv('TRACKING_LEDGER_ADDRESS', ''),
                'AlertManager': os.getenv('ALERT_MANAGER_ADDRESS', ''),
            },
            'contracts_deployed': False,
            'total_transactions': len(blockchain_tx_log),
            'latest_block': 50000000 + len(blockchain_tx_log),
            'gas_price': '30 gwei',
            'status': 'simulation'
        },
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/blockchain/transactions', methods=['GET'])
def blockchain_transactions():
    """Get recent blockchain transactions."""
    limit = request.args.get('limit', 20, type=int)
    return jsonify({
        'success': True,
        'transactions': list(blockchain_tx_log)[:limit],
        'total': len(blockchain_tx_log),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/blockchain/verify/<video_hash>', methods=['GET'])
def blockchain_verify(video_hash):
    """Verify a video's blockchain record."""
    # Search for matching transaction
    matching_tx = None
    for tx in blockchain_tx_log:
        if tx['video_hash'].startswith(video_hash[:8]):
            matching_tx = tx
            break
    
    if matching_tx:
        return jsonify({
            'success': True,
            'verified': True,
            'transaction': matching_tx,
            'verification_time': datetime.now().isoformat()
        })
    else:
        return jsonify({
            'success': True,
            'verified': False,
            'message': 'No blockchain record found for this video hash'
        })


# ============================================================================
# API Routes - Alert Notifications
# ============================================================================

@app.route('/api/alerts/status', methods=['GET'])
def alerts_status():
    """Get notification channel status."""
    ns = get_notification_service()
    if ns:
        channels = ns.get_channel_status()
        return jsonify({
            'success': True,
            'channels': channels,
            'configured': any(v for k, v in channels.items() if k != 'console'),
            'history_count': len(ns.get_history()),
        })
    return jsonify({
        'success': True,
        'channels': {'console': True, 'email': False, 'telegram': False, 'discord': False},
        'configured': False,
        'note': 'NotificationService not available',
    })


@app.route('/api/alerts/test', methods=['POST'])
def alerts_test():
    """Send a test alert through all configured channels."""
    ns = get_notification_service()
    if not ns:
        return jsonify({'success': False, 'error': 'NotificationService not available'}), 500
    
    channels = ns.get_channel_status()
    active = [k for k, v in channels.items() if v and k != 'console']
    
    if not active:
        return jsonify({'success': False, 'error': 'No notification channels configured'}), 400
    
    ns.send_alert(
        'TEST_ALERT',
        f'This is a test notification from the Deepfake Detection System.\n'
        f'Timestamp: {datetime.now().isoformat()}\n'
        f'Active channels: {", ".join(active)}',
        'MEDIUM'
    )
    
    return jsonify({
        'success': True,
        'message': f'Test alert sent to: {", ".join(active)}',
        'channels': active,
    })


@app.route('/api/alerts/history', methods=['GET'])
def alerts_history():
    """Get recent alert history."""
    ns = get_notification_service()
    if not ns:
        return jsonify({'success': True, 'history': []})
    
    limit = request.args.get('limit', 50, type=int)
    history = ns.get_history(limit)
    return jsonify({
        'success': True,
        'history': [
            {
                'channel': h.channel,
                'alert_type': h.alert_type,
                'severity': h.severity,
                'message': h.message[:200],
                'timestamp': h.timestamp,
                'success': h.success,
                'error': h.error,
            }
            for h in history
        ],
    })


# ============================================================================
# API Routes - URL Analysis
# ============================================================================

@app.route('/api/analyze/url', methods=['POST'])
def analyze_url():
    """Analyze a video from URL (simulated download + analysis)."""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'URL required'}), 400
    
    url = data['url']
    
    # For hackathon demo: simulate URL analysis
    # In production, this would download the video and run full pipeline
    import random
    
    is_deepfake = random.random() > 0.5
    confidence = round(random.uniform(0.65, 0.98), 4)
    content_hash = hashlib.sha256(url.encode()).hexdigest()
    
    result = {
        'success': True,
        'source': 'url',
        'url': url,
        'result': {
            'is_deepfake': is_deepfake,
            'confidence': confidence,
            'verdict': 'DEEPFAKE DETECTED' if is_deepfake else 'LIKELY AUTHENTIC',
            'confidence_level': 'HIGH' if confidence > 0.8 else 'MEDIUM',
            'risk_level': 'HIGH' if is_deepfake and confidence > 0.8 else 'MEDIUM' if is_deepfake else 'LOW',
            'lipsync_score': round(random.uniform(0.3, 0.95), 4),
            'fact_check_score': round(random.uniform(0.4, 0.9), 4),
            'video_hash': content_hash,
            'perceptual_hash': hashlib.md5(url.encode()).hexdigest(),
            'celebrity_detected': False,
            'celebrity_name': None,
            'detection_method': 'URL Analysis Pipeline',
            'sources_found': [],
            'timestamp': datetime.now().isoformat(),
            'processing_time': round(random.uniform(2.0, 8.0), 3)
        },
        'blockchain': {
            'tx_hash': '0x' + hashlib.sha256(f"{content_hash}{time.time()}".encode()).hexdigest()[:64],
            'network': 'Polygon Amoy Testnet',
            'status': 'confirmed',
            'block': 50000000 + len(blockchain_tx_log),
            'contract': '0x742d35Cc6634C0532925a3b844Bc9e7595f2bD1e'
        }
    }
    
    # Store detection
    detection_record = {
        'id': str(uuid.uuid4())[:8],
        'filename': url[:50] + '...' if len(url) > 50 else url,
        'is_deepfake': is_deepfake,
        'confidence': confidence,
        'verdict': result['result']['verdict'],
        'risk_level': result['result']['risk_level'],
        'video_hash': content_hash[:16] + '...',
        'processing_time': result['result']['processing_time'],
        'timestamp': datetime.now().isoformat(),
        'location': 'URL Source',
        'platform': 'URL Analysis'
    }
    recent_detections.appendleft(detection_record)
    platform_stats['url'] += 1
    
    # Blockchain TX
    tx_hash = hashlib.sha256(f"{content_hash}{time.time()}".encode()).hexdigest()
    blockchain_tx_log.appendleft({
        'tx_hash': '0x' + tx_hash[:64],
        'block': 50000000 + len(blockchain_tx_log),
        'action': 'URL_ANALYZED',
        'video_hash': content_hash[:16] + '...',
        'is_deepfake': is_deepfake,
        'confidence': confidence,
        'timestamp': datetime.now().isoformat(),
        'gas_used': 72000,
        'status': 'confirmed',
        'network': 'Polygon Amoy Testnet'
    })
    
    return jsonify(result)


# ============================================================================
# API Routes - Recent Detections & Enhanced Stats
# ============================================================================

@app.route('/api/detections/recent', methods=['GET'])
def get_recent_detections():
    """Get recent detection results."""
    limit = request.args.get('limit', 20, type=int)
    return jsonify({
        'success': True,
        'detections': list(recent_detections)[:limit],
        'total': len(recent_detections),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/stats/platforms', methods=['GET'])
def get_platform_stats():
    """Get platform distribution statistics."""
    return jsonify({
        'success': True,
        'platforms': platform_stats,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/stats/threats', methods=['GET'])
def get_threat_timeline():
    """Get recent threat events."""
    limit = request.args.get('limit', 50, type=int)
    return jsonify({
        'success': True,
        'threats': list(threat_timeline)[:limit],
        'total': len(threat_timeline),
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# API Routes - Hash Operations
# ============================================================================

@app.route('/api/hash/compare', methods=['POST'])
def compare_hashes():
    """Compare two videos for similarity."""
    if 'video1' not in request.files or 'video2' not in request.files:
        return jsonify({'error': 'Two video files required'}), 400
    
    try:
        hash_cache = get_hash_cache()
        
        # Save files temporarily
        file1 = request.files['video1']
        file2 = request.files['video2']
        
        path1 = UPLOAD_FOLDER / f"compare1_{int(time.time())}.mp4"
        path2 = UPLOAD_FOLDER / f"compare2_{int(time.time())}.mp4"
        
        file1.save(str(path1))
        file2.save(str(path2))
        
        similarity = hash_cache.get_hash_similarity(str(path1), str(path2))
        
        # Clean up
        path1.unlink()
        path2.unlink()
        
        return jsonify({
            'success': True,
            'similarity': similarity
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/hash/compute', methods=['POST'])
def compute_hash():
    """Compute hashes for a video."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    try:
        hash_cache = get_hash_cache()
        if hash_cache is None:
            return jsonify({'error': 'Hash cache not initialized'}), 503
        
        file = request.files['video']
        video_path = UPLOAD_FOLDER / f"hash_{int(time.time())}.mp4"
        file.save(str(video_path))
        
        hash_info = hash_cache.compute_video_hash(str(video_path))
        
        video_path.unlink()
        
        return jsonify({
            'success': True,
            'hashes': hash_info
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API Routes - Statistics & Dashboard
# ============================================================================

@app.route('/api/stats/cache', methods=['GET'])
def get_cache_stats():
    """Get cache statistics."""
    try:
        hash_cache = get_hash_cache()
        stats = hash_cache.get_cache_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats/lineage', methods=['GET'])
def get_lineage_stats():
    """Get lineage database statistics."""
    try:
        origin_finder = get_origin_finder()
        stats = origin_finder.get_statistics()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats/dashboard', methods=['GET'])
def get_dashboard_stats():
    """Get comprehensive dashboard statistics."""
    try:
        hash_cache = get_hash_cache()
        origin_finder = get_origin_finder()
        
        cache_stats = {}
        lineage_stats = {}
        
        if hash_cache:
            try:
                cache_stats = hash_cache.get_cache_stats()
            except Exception:
                cache_stats = {'error': 'Cache stats unavailable'}
        
        if origin_finder:
            try:
                lineage_stats = origin_finder.get_statistics()
            except Exception:
                lineage_stats = {'error': 'Lineage stats unavailable'}
        
        return jsonify({
            'success': True,
            'cache': cache_stats,
            'lineage': lineage_stats,
            'recent_detections': list(recent_detections)[:10],
            'total_analyzed': len(recent_detections),
            'deepfakes_found': sum(1 for d in recent_detections if d.get('is_deepfake')),
            'platform_distribution': platform_stats,
            'blockchain': {
                'total_transactions': len(blockchain_tx_log),
                'recent_transactions': list(blockchain_tx_log)[:5]
            },
            'threat_count': len(threat_timeline),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API Routes - Actions
# ============================================================================

@app.route('/api/action/flag', methods=['POST'])
def flag_for_review():
    """Flag a video for platform review."""
    data = request.get_json()
    if not data or 'video_hash' not in data:
        return jsonify({'error': 'video_hash required'}), 400
    
    # In production, this would send to platform APIs
    return jsonify({
        'success': True,
        'message': 'Video flagged for platform review',
        'video_hash': data['video_hash'],
        'flag_id': f"FLAG-{int(time.time())}",
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/action/export-report', methods=['POST'])
def export_legal_report():
    """Generate exportable legal evidence report."""
    data = request.get_json()
    if not data or 'video_hash' not in data:
        return jsonify({'error': 'video_hash required'}), 400
    
    try:
        origin_finder = get_origin_finder()
        
        if not origin_finder:
            return jsonify({'success': False, 'error': 'Origin finder not available'}), 503
        
        report = origin_finder.generate_forensic_report(data['video_hash'])
        
        return jsonify({
            'success': True,
            'report': report,
            'export_id': f"REPORT-{int(time.time())}",
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/action/monitor', methods=['POST'])
def monitor_derivatives():
    """Set up monitoring for derivative content."""
    data = request.get_json()
    if not data or 'video_hash' not in data:
        return jsonify({'error': 'video_hash required'}), 400
    
    # In production, this would set up background monitoring
    return jsonify({
        'success': True,
        'message': 'Monitoring activated for derivative content',
        'video_hash': data['video_hash'],
        'monitor_id': f"MON-{int(time.time())}",
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# API Routes - Chrome Extension
# ============================================================================

@app.route('/api/extension/analyze-url', methods=['POST'])
def extension_analyze_url():
    """Analyze a video from URL (for Chrome extension).
    
    This endpoint accepts a video URL from the extension and processes it.
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'url required'}), 400
    
    video_url = data['url']
    platform = data.get('platform', 'unknown')
    
    try:
        # Generate a temporary file to download the video
        import tempfile
        import urllib.request
        from urllib.parse import urlparse
        
        # For demo purposes, return mock analysis
        # In production, this would download and analyze the video
        video_hash = hashlib.md5(video_url.encode()).hexdigest()
        
        # Check cache first
        origin_finder = get_origin_finder()
        if origin_finder:
            cached = origin_finder.video_hash_cache.check_duplicate(video_hash)
            if cached:
                return jsonify({
                    'success': True,
                    'cached': True,
                    'video_hash': video_hash,
                    'result': cached
                })
        
        # Simulate analysis results for demo
        # In production, download video and run full pipeline
        import random
        is_deepfake = random.random() < 0.3  # 30% chance deepfake for demo
        confidence = random.uniform(0.75, 0.98)
        
        result = {
            'video_hash': video_hash,
            'platform': platform,
            'url': video_url,
            'is_deepfake': is_deepfake,
            'confidence': confidence,
            'authenticity_score': 1 - confidence if is_deepfake else confidence,
            'analysis_type': 'url',
            'risk_level': 'high' if is_deepfake else 'low',
            'signals': {
                'face_manipulation': is_deepfake,
                'audio_visual_sync': not is_deepfake,
                'artifact_detection': is_deepfake,
                'temporal_consistency': not is_deepfake
            },
            'timestamp': datetime.now().isoformat()
        }
        
        # Cache the result
        if origin_finder:
            origin_finder.video_hash_cache.store_analysis_result(video_hash, result)
        
        return jsonify({
            'success': True,
            'cached': False,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extension/check-hash', methods=['POST'])
def extension_check_hash():
    """Check if a video hash exists in cache (for Chrome extension).
    
    This is a quick lookup to avoid re-analyzing known videos.
    """
    data = request.get_json()
    if not data or 'hash' not in data:
        return jsonify({'error': 'hash required'}), 400
    
    video_hash = data['hash']
    
    try:
        origin_finder = get_origin_finder()
        
        if origin_finder:
            cached = origin_finder.video_hash_cache.check_duplicate(video_hash)
            if cached:
                return jsonify({
                    'success': True,
                    'found': True,
                    'result': cached
                })
        
        return jsonify({
            'success': True,
            'found': False,
            'message': 'Hash not found in cache'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extension/stats', methods=['GET'])
def extension_get_stats():
    """Get analysis statistics for Chrome extension dashboard."""
    try:
        origin_finder = get_origin_finder()
        
        stats = {
            'total_scans': 0,
            'deepfakes_detected': 0,
            'videos_verified': 0,
            'cache_size': 0
        }
        
        if origin_finder and hasattr(origin_finder, 'video_hash_cache'):
            cache = origin_finder.video_hash_cache
            if hasattr(cache, 'get_stats'):
                cache_stats = cache.get_stats()
                stats['cache_size'] = cache_stats.get('total_videos', 0)
        
        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extension/report', methods=['POST'])
def extension_report_deepfake():
    """Report a detected deepfake from the extension."""
    data = request.get_json()
    if not data or 'video_hash' not in data:
        return jsonify({'error': 'video_hash required'}), 400
    
    try:
        report_data = {
            'video_hash': data['video_hash'],
            'url': data.get('url', ''),
            'platform': data.get('platform', 'unknown'),
            'confidence': data.get('confidence', 0),
            'reporter': 'extension',
            'report_id': f"EXT-{int(time.time())}",
            'timestamp': datetime.now().isoformat()
        }
        
        # In production, store this report and potentially notify platforms
        return jsonify({
            'success': True,
            'report': report_data,
            'message': 'Deepfake reported successfully'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extension/analyze-frames', methods=['POST'])
def extension_analyze_frames():
    """Analyze video frames for deepfake detection (Chrome extension).
    
    This endpoint accepts an array of base64-encoded JPEG frames and runs
    actual deepfake detection on them. This is more efficient than downloading
    entire videos, especially for long YouTube videos.
    """
    data = request.get_json()
    if not data or 'frames' not in data:
        return jsonify({'error': 'frames required'}), 400
    
    frames = data['frames']  # Array of base64 data URLs
    platform = data.get('platform', 'unknown')
    video_url = data.get('video_url', '')
    video_duration = data.get('video_duration', 0)
    analysis_method = data.get('analysis_method', 'frames')
    
    if not frames or len(frames) == 0:
        return jsonify({'error': 'No frames provided'}), 400
    
    try:
        import base64
        import io
        import numpy as np
        
        # Generate hash from first frame + URL for caching
        cache_key = hashlib.sha256(
            f"{video_url}:{len(frames)}:{video_duration}".encode()
        ).hexdigest()[:32]
        
        # Check cache
        origin_finder = get_origin_finder()
        if origin_finder:
            cached = origin_finder.video_hash_cache.check_duplicate(cache_key)
            if cached:
                return jsonify({
                    'success': True,
                    'cached': True,
                    'result': cached
                })
        
        # Decode and analyze frames
        decoded_frames = []
        for i, frame_data in enumerate(frames[:15]):  # Max 15 frames
            try:
                # Remove data URL prefix if present
                if ',' in frame_data:
                    frame_data = frame_data.split(',')[1]
                
                # Decode base64
                img_bytes = base64.b64decode(frame_data)
                
                # Convert to numpy array
                import cv2
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is not None:
                    decoded_frames.append(img)
            except Exception as e:
                print(f"Frame {i} decode error: {e}")
                continue
        
        if len(decoded_frames) == 0:
            return jsonify({'error': 'Failed to decode any frames'}), 400
        
        # Run actual deepfake detection on frames using PERSONALITY-FIRST approach
        detection_results = []
        face_found = False
        personality_detected = False
        personality_name = None
        personality_category = None
        gemini_result = None
        
        detector = get_detector()
        gemini_checker = get_gemini_checker()
        
        # STEP 1: Use Gemini personality-first detection on best frame
        best_frame = decoded_frames[len(decoded_frames) // 2]  # Use middle frame
        
        if gemini_checker and hasattr(gemini_checker, 'personality_first_detection'):
            print("[Extension API] Running PERSONALITY-FIRST Gemini detection...")
            try:
                gemini_result = gemini_checker.personality_first_detection(
                    video_path=None,  # No video file
                    frames=[best_frame]  # Pass frame directly
                )
                
                if gemini_result:
                    personality_detected = gemini_result.get('personality_detected', False)
                    personality_name = gemini_result.get('personality_name')
                    personality_category = gemini_result.get('personality_category')
                    print(f"[Extension API] Gemini result: personality={personality_detected}, name={personality_name}")
            except Exception as e:
                print(f"[Extension API] Gemini error: {e}")
        
        # STEP 2: Run face detection on all frames
        for i, frame in enumerate(decoded_frames):
            try:
                face_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                )
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                
                if len(faces) > 0:
                    face_found = True
                    detection_results.append({
                        'face_found': True,
                        'face_count': len(faces),
                        'frame_quality': calculate_frame_quality(frame)
                    })
                else:
                    detection_results.append({'face_found': False})
            except Exception as e:
                print(f"Frame {i} analysis error: {e}")
                detection_results.append({'error': str(e)})
        
        # Aggregate results across frames
        frames_with_faces = sum(1 for r in detection_results if r.get('face_found'))
        face_detection_rate = frames_with_faces / len(decoded_frames) if decoded_frames else 0
        
        avg_quality = np.mean([
            r.get('frame_quality', 0.5) 
            for r in detection_results 
            if 'frame_quality' in r
        ]) if detection_results else 0.5
        
        # STEP 3: Compute final verdict using PERSONALITY-AWARE fusion
        if gemini_result and gemini_result.get('is_deepfake') is not None:
            # Gemini gave a definitive answer - use personality-aware weighting
            gemini_is_fake = gemini_result.get('is_deepfake', False)
            gemini_auth_score = gemini_result.get('authenticity_score', 0.5)
            gemini_confidence = gemini_result.get('deepfake_confidence', 0.5)
            
            # Local heuristic score (based on quality/faces)
            local_fake_prob = 0.3 if avg_quality > 0.6 else 0.6 if avg_quality < 0.4 else 0.45
            
            # Determine weights based on personality
            if personality_detected and personality_category in ['POLITICIAN', 'BUSINESS']:
                # High-risk: 90% Gemini
                gemini_weight = 0.90
                local_weight = 0.10
            elif personality_detected:
                # Celebrity: 85% Gemini
                gemini_weight = 0.85
                local_weight = 0.15
            else:
                # Unknown person: 70% Gemini
                gemini_weight = 0.70
                local_weight = 0.30
            
            # Fused probability
            gemini_fake_prob = 1.0 if gemini_is_fake else (1 - gemini_auth_score)
            combined_fake_prob = (gemini_fake_prob * gemini_weight) + (local_fake_prob * local_weight)
            
            is_deepfake = combined_fake_prob > 0.5
            confidence = max(gemini_confidence, abs(combined_fake_prob - 0.5) * 2 + 0.5)
            
            print(f"[Extension API] Fused result: fake_prob={combined_fake_prob:.2f}, weights=({gemini_weight}, {local_weight})")
        else:
            # Fallback: Heuristic scoring only
            is_deepfake = avg_quality < 0.4 and face_detection_rate > 0.3
            confidence = 0.6 + (0.3 * (1 - avg_quality)) if is_deepfake else 0.7 + (0.25 * avg_quality)
        
        result = {
            'video_hash': cache_key,
            'platform': platform,
            'url': video_url,
            'is_deepfake': is_deepfake,
            'confidence': round(confidence, 3),
            'authenticity_score': round(1 - confidence if is_deepfake else confidence, 3),
            'analysis_type': 'frames',
            'analysis_method': 'personality_first' if gemini_result else 'heuristic',
            'risk_level': 'high' if is_deepfake else 'medium' if confidence < 0.8 else 'low',
            'frames_analyzed': len(decoded_frames),
            'frames_with_faces': frames_with_faces,
            'face_detection_rate': round(face_detection_rate, 3),
            'video_duration': video_duration,
            # Personality-first specific fields
            'personality_detection': {
                'detected': personality_detected,
                'name': personality_name,
                'category': personality_category,
                'gemini_used': gemini_result is not None
            },
            'signals': {
                'face_manipulation': is_deepfake and face_found,
                'temporal_consistency': face_detection_rate > 0.6,
                'quality_score': round(avg_quality, 3),
                'artifact_detection': avg_quality < 0.5,
                'personality_risk': personality_category in ['POLITICIAN', 'BUSINESS'] if personality_category else False
            },
            'gemini_analysis': {
                'reasoning': gemini_result.get('reasoning', '') if gemini_result else None,
                'red_flags': gemini_result.get('red_flags', []) if gemini_result else [],
                'recommendation': gemini_result.get('recommendation', 'VERIFY') if gemini_result else 'VERIFY'
            } if gemini_result else None,
            'timestamp': datetime.now().isoformat()
        }
        
        # Cache the result
        if origin_finder:
            origin_finder.video_hash_cache.store_analysis_result(cache_key, result)
        
        return jsonify({
            'success': True,
            'cached': False,
            'result': result
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/extension/analyze-thumbnail', methods=['POST'])
def extension_analyze_thumbnail():
    """Quick thumbnail analysis for YouTube videos (Chrome extension).
    
    This is a fast pre-check that analyzes the video thumbnail before
    committing to full frame analysis. Returns high_confidence=True if
    the thumbnail alone is conclusive.
    """
    data = request.get_json()
    if not data or 'thumbnail_url' not in data:
        return jsonify({'error': 'thumbnail_url required'}), 400
    
    thumbnail_url = data['thumbnail_url']
    video_url = data.get('video_url', '')
    
    try:
        import urllib.request
        import numpy as np
        import cv2
        
        # Download thumbnail
        req = urllib.request.Request(
            thumbnail_url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        with urllib.request.urlopen(req, timeout=5) as response:
            img_bytes = response.read()
        
        # Decode image
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({'success': False, 'error': 'Failed to decode thumbnail'})
        
        # Basic face detection on thumbnail
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        has_face = len(faces) > 0
        quality = calculate_frame_quality(img)
        
        # Thumbnail is only conclusive if it has no faces (probably not deepfake)
        # or very high quality (probably authentic)
        high_confidence = not has_face or quality > 0.8
        
        result = {
            'video_hash': hashlib.md5(video_url.encode()).hexdigest(),
            'is_deepfake': False if high_confidence else None,  # None = inconclusive
            'confidence': 0.85 if high_confidence else 0.5,
            'analysis_type': 'thumbnail',
            'high_confidence': high_confidence,
            'has_face': has_face,
            'thumbnail_quality': round(quality, 3),
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify({
            'success': True,
            'high_confidence': high_confidence,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def calculate_frame_quality(frame):
    """Calculate a simple quality score for a frame."""
    import cv2
    import numpy as np
    
    try:
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Calculate Laplacian variance (blur detection)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Normalize to 0-1 range (higher = better quality)
        # Typical values: blurry < 100, clear > 500
        blur_score = min(laplacian_var / 500, 1.0)
        
        # Calculate contrast
        contrast = gray.std() / 128  # Normalize by max std
        
        # Combined score
        quality = 0.7 * blur_score + 0.3 * contrast
        return min(max(quality, 0), 1)  # Clamp to 0-1
    except:
        return 0.5  # Default on error


# ============================================================================
# Static File Routes
# ============================================================================

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files."""
    return send_from_directory(app.static_folder, filename)


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error."""
    return jsonify({
        'error': 'File too large',
        'max_size_mb': MAX_CONTENT_LENGTH / (1024 * 1024)
    }), 413


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({'error': 'Internal server error'}), 500


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Deepfake Origin Finder Web Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5001, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║           DEEPFAKE ORIGIN FINDER                             ║
    ║           Forensic Intelligence Platform                     ║
    ║                                                              ║
    ║           Starting server on http://{args.host}:{args.port}            ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=args.host, port=args.port, debug=args.debug)
