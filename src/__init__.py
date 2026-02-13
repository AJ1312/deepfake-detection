# Enhanced Deepfake Detection System
# Multi-layered detection combining lip-sync analysis, video hashing, and fact-checking

__version__ = "1.0.0"
__author__ = "Enhanced AI Detection Team"

from .core.detection_result import DetectionResult
from .core.video_hash_cache import VideoHashCache
from .core.gemini_fact_checker import GeminiFactChecker
from .pipeline.enhanced_detector import EnhancedDeepfakeDetector

__all__ = [
    'DetectionResult',
    'VideoHashCache', 
    'GeminiFactChecker',
    'EnhancedDeepfakeDetector'
]
