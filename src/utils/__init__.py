# Utility functions for Enhanced Deepfake Detection System

from .video_processing import (
    extract_frames,
    extract_consecutive_frame_pairs,
    detect_and_crop_face,
    extract_lip_region
)
from .hash_utils import (
    compute_perceptual_hash,
    compute_content_hash,
    hamming_distance,
    are_videos_similar
)
from .feature_extractors import (
    compute_temporal_consistency,
    analyze_frequency_artifacts,
    compute_lip_sync_score,
    extract_handcrafted_features
)

__all__ = [
    'extract_frames',
    'extract_consecutive_frame_pairs',
    'detect_and_crop_face',
    'extract_lip_region',
    'compute_perceptual_hash',
    'compute_content_hash',
    'hamming_distance',
    'are_videos_similar',
    'compute_temporal_consistency',
    'analyze_frequency_artifacts',
    'compute_lip_sync_score',
    'extract_handcrafted_features'
]
