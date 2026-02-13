# Core components for Enhanced Deepfake Detection System

from .detection_result import DetectionResult
from .video_hash_cache import VideoHashCache
from .gemini_fact_checker import GeminiFactChecker
from .gemini_deepfake_verifier import GeminiDeepfakeVerifier, verify_deepfake_with_gemini

__all__ = [
    'DetectionResult', 
    'VideoHashCache', 
    'GeminiFactChecker',
    'GeminiDeepfakeVerifier',
    'verify_deepfake_with_gemini'
]
