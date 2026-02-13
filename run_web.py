#!/usr/bin/env python3
"""
Deepfake Origin Finder - Web Application Launcher
==================================================
Quick start script for the forensic intelligence platform.

Usage:
    python run_web.py [--host HOST] [--port PORT] [--debug]
    
Examples:
    python run_web.py                    # Start on localhost:5000
    python run_web.py --port 8080        # Start on localhost:8080
    python run_web.py --debug            # Start in debug mode
"""

import os
import sys
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

def check_dependencies():
    """Check if required dependencies are installed."""
    missing = []
    
    try:
        import flask
    except ImportError:
        missing.append('flask')
    
    try:
        import flask_cors
    except ImportError:
        missing.append('flask-cors')
    
    # torch is optional - handcrafted features will be used if not available
    try:
        import torch
        print("   ✓ PyTorch available")
    except ImportError:
        print("   ⚠ PyTorch not available (will use handcrafted features)")
    
    try:
        import cv2
    except ImportError:
        missing.append('opencv-python')
    
    if missing:
        print("❌ Missing dependencies:")
        for dep in missing:
            print(f"   - {dep}")
        print(f"\nInstall with: pip install {' '.join(missing)}")
        return False
    
    return True


def check_model():
    """Check if the trained model exists."""
    model_path = PROJECT_ROOT / 'models' / 'best_model.pth'
    if not model_path.exists():
        print("⚠️  Warning: Trained model not found at models/best_model.pth")
        print("   The system will use handcrafted features for detection.")
        print("   Train a model using the Jupyter notebook for better accuracy.")
        return False
    return True


def check_gemini_api():
    """Check if Gemini API key is configured."""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("⚠️  Warning: GEMINI_API_KEY environment variable not set")
        print("   Fact-checking and Gemini verification will be disabled.")
        print("   Set with: export GEMINI_API_KEY='your-api-key'")
        return False
    return True


def print_banner():
    """Print startup banner."""
    banner = """
    ╔══════════════════════════════════════════════════════════════════╗
    ║                                                                  ║
    ║     ██████╗ ███████╗███████╗██████╗ ███████╗ █████╗ ██╗  ██╗    ║
    ║     ██╔══██╗██╔════╝██╔════╝██╔══██╗██╔════╝██╔══██╗██║ ██╔╝    ║
    ║     ██║  ██║█████╗  █████╗  ██████╔╝█████╗  ███████║█████╔╝     ║
    ║     ██║  ██║██╔══╝  ██╔══╝  ██╔═══╝ ██╔══╝  ██╔══██║██╔═██╗     ║
    ║     ██████╔╝███████╗███████╗██║     ██║     ██║  ██║██║  ██╗    ║
    ║     ╚═════╝ ╚══════╝╚══════╝╚═╝     ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝    ║
    ║                                                                  ║
    ║              ORIGIN FINDER | FORENSIC INTELLIGENCE               ║
    ║                                                                  ║
    ╚══════════════════════════════════════════════════════════════════╝
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description='Deepfake Origin Finder - Forensic Intelligence Platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_web.py                    Start on http://localhost:5000
  python run_web.py --port 8080        Start on http://localhost:8080
  python run_web.py --host 0.0.0.0     Allow external connections
  python run_web.py --debug            Enable debug mode with auto-reload
        """
    )
    parser.add_argument('--host', default='127.0.0.1', 
                        help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000,
                        help='Port to bind to (default: 5000)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode')
    
    args = parser.parse_args()
    
    print_banner()
    
    print("🔍 Checking dependencies...")
    if not check_dependencies():
        sys.exit(1)
    print("✅ Dependencies OK\n")
    
    print("🧠 Checking model...")
    check_model()
    print()
    
    print("🔑 Checking Gemini API...")
    check_gemini_api()
    print()
    
    # Import and run Flask app
    print("🚀 Starting server...")
    print(f"   URL: http://{args.host}:{args.port}")
    print(f"   Debug: {'Enabled' if args.debug else 'Disabled'}")
    print("\n   Press Ctrl+C to stop\n")
    
    # Change to web directory
    os.chdir(PROJECT_ROOT / 'web')
    
    from web.app import app
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
