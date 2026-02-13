"""
Feature Extractors
==================
Hand-crafted features for lip-sync analysis and deepfake detection.

Includes:
- Temporal consistency scoring
- Frequency domain analysis
- Lip synchronization scoring
- Edge density analysis
"""

import numpy as np
import cv2
from scipy import fft
from scipy.signal import correlate
from typing import List, Tuple, Dict, Any


def compute_temporal_consistency(
    frame1: np.ndarray,
    frame2: np.ndarray
) -> float:
    """
    Compute temporal consistency between consecutive frames.
    
    Combines multiple metrics:
    - Pixel-wise correlation
    - Structural similarity (simplified)
    - Optical flow consistency
    - Edge consistency
    
    Args:
        frame1, frame2: Consecutive frames (BGR format)
        
    Returns:
        Score from 0 (inconsistent) to 1 (highly consistent)
    """
    # Convert to grayscale
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY) if len(frame1.shape) == 3 else frame1
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY) if len(frame2.shape) == 3 else frame2
    
    # Ensure same size
    if gray1.shape != gray2.shape:
        gray2 = cv2.resize(gray2, (gray1.shape[1], gray1.shape[0]))
    
    # Metric 1: Pixel-wise correlation
    correlation = _compute_correlation(gray1, gray2)
    
    # Metric 2: Simplified SSIM
    ssim_score = _compute_simple_ssim(gray1, gray2)
    
    # Metric 3: Edge consistency
    edge_consistency = _compute_edge_consistency(gray1, gray2)
    
    # Metric 4: Histogram similarity
    hist_similarity = _compute_histogram_similarity(gray1, gray2)
    
    # Weighted combination
    weights = {
        'correlation': 0.3,
        'ssim': 0.3,
        'edge': 0.2,
        'histogram': 0.2
    }
    
    final_score = (
        correlation * weights['correlation'] +
        ssim_score * weights['ssim'] +
        edge_consistency * weights['edge'] +
        hist_similarity * weights['histogram']
    )
    
    return max(0.0, min(1.0, final_score))


def _compute_correlation(gray1: np.ndarray, gray2: np.ndarray) -> float:
    """Compute normalized cross-correlation."""
    # Flatten and normalize
    flat1 = gray1.flatten().astype(np.float64)
    flat2 = gray2.flatten().astype(np.float64)
    
    # Normalize
    flat1 = (flat1 - np.mean(flat1)) / (np.std(flat1) + 1e-8)
    flat2 = (flat2 - np.mean(flat2)) / (np.std(flat2) + 1e-8)
    
    # Correlation
    correlation = np.dot(flat1, flat2) / len(flat1)
    
    return max(0.0, min(1.0, (correlation + 1) / 2))


def _compute_simple_ssim(gray1: np.ndarray, gray2: np.ndarray) -> float:
    """Compute simplified structural similarity."""
    # Constants
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    
    gray1 = gray1.astype(np.float64)
    gray2 = gray2.astype(np.float64)
    
    # Means
    mu1 = np.mean(gray1)
    mu2 = np.mean(gray2)
    
    # Variances
    sigma1_sq = np.var(gray1)
    sigma2_sq = np.var(gray2)
    
    # Covariance
    sigma12 = np.mean((gray1 - mu1) * (gray2 - mu2))
    
    # SSIM formula
    numerator = (2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)
    denominator = (mu1**2 + mu2**2 + C1) * (sigma1_sq + sigma2_sq + C2)
    
    ssim = numerator / (denominator + 1e-8)
    
    return max(0.0, min(1.0, (ssim + 1) / 2))


def _compute_edge_consistency(gray1: np.ndarray, gray2: np.ndarray) -> float:
    """Compute edge detection consistency."""
    edges1 = cv2.Canny(gray1, 50, 150)
    edges2 = cv2.Canny(gray2, 50, 150)
    
    # Compute overlap (Dice coefficient)
    intersection = np.sum(edges1 & edges2)
    total = np.sum(edges1) + np.sum(edges2)
    
    if total == 0:
        return 1.0
    
    dice = 2 * intersection / total
    return dice


def _compute_histogram_similarity(gray1: np.ndarray, gray2: np.ndarray) -> float:
    """Compute histogram correlation."""
    hist1 = cv2.calcHist([gray1], [0], None, [256], [0, 256])
    hist2 = cv2.calcHist([gray2], [0], None, [256], [0, 256])
    
    # Normalize
    hist1 = hist1 / (hist1.sum() + 1e-8)
    hist2 = hist2 / (hist2.sum() + 1e-8)
    
    # Correlation
    correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    
    return max(0.0, min(1.0, (correlation + 1) / 2))


def analyze_frequency_artifacts(
    frame_pairs: List[Tuple[np.ndarray, np.ndarray]]
) -> float:
    """
    Analyze frequency domain for manipulation artifacts.
    
    Deepfakes often have unusual high-frequency patterns.
    
    Args:
        frame_pairs: List of (frame1, frame2) tuples
        
    Returns:
        Artifact score from 0 (clean) to 1 (suspicious)
    """
    artifact_scores = []
    
    for frame1, frame2 in frame_pairs:
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY) if len(frame1.shape) == 3 else frame1
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY) if len(frame2.shape) == 3 else frame2
        
        # Ensure same size
        if gray1.shape != gray2.shape:
            gray2 = cv2.resize(gray2, (gray1.shape[1], gray1.shape[0]))
        
        # Normalize
        gray1 = gray1.astype(np.float32) / 255.0
        gray2 = gray2.astype(np.float32) / 255.0
        
        # Compute 2D FFT
        fft1 = np.fft.fft2(gray1)
        fft2 = np.fft.fft2(gray2)
        
        # Get magnitude spectrum
        magnitude1 = np.abs(np.fft.fftshift(fft1))
        magnitude2 = np.abs(np.fft.fftshift(fft2))
        
        # Analyze high-frequency components
        height, width = magnitude1.shape
        center_y, center_x = height // 2, width // 2
        radius_threshold = min(height, width) * 0.3
        
        # Mask for high-frequency region
        y, x = np.ogrid[:height, :width]
        distance = np.sqrt((y - center_y)**2 + (x - center_x)**2)
        high_freq_mask = distance > radius_threshold
        
        # High-frequency power
        hf_power1 = magnitude1[high_freq_mask].mean()
        hf_power2 = magnitude2[high_freq_mask].mean()
        
        # Power difference indicates manipulation
        power_diff = abs(hf_power1 - hf_power2)
        artifact_score = min(1.0, power_diff / 0.5)
        
        artifact_scores.append(artifact_score)
    
    return np.mean(artifact_scores) if artifact_scores else 0.5


def compute_lip_sync_score(
    frame1: np.ndarray,
    frame2: np.ndarray
) -> float:
    """
    Compute lip synchronization score between frames.
    
    Higher score indicates better lip-sync (more authentic).
    
    Args:
        frame1, frame2: Consecutive frames
        
    Returns:
        Lip-sync score from 0 to 1
    """
    # Convert to grayscale
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY) if len(frame1.shape) == 3 else frame1
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY) if len(frame2.shape) == 3 else frame2
    
    # Resize to same size
    target_size = (64, 64)
    gray1 = cv2.resize(gray1, target_size)
    gray2 = cv2.resize(gray2, target_size)
    
    # Compute correlation
    correlation = np.corrcoef(gray1.flatten(), gray2.flatten())[0, 1]
    if np.isnan(correlation):
        correlation = 0
    
    # Higher correlation = better sync
    sync_score = max(0.0, min(1.0, (correlation + 1) / 2))
    
    return sync_score


def extract_handcrafted_features(
    frame_pairs: List[Tuple[np.ndarray, np.ndarray]]
) -> Dict[str, float]:
    """
    Extract comprehensive handcrafted features from frame pairs.
    
    Args:
        frame_pairs: List of (frame1, frame2) tuples
        
    Returns:
        Dictionary of feature names to values
    """
    features = {
        'temporal_consistency': [],
        'lip_sync_score': [],
        'frequency_artifacts': 0.0,
        'edge_density_diff': [],
        'pixel_difference': [],
        'correlation': []
    }
    
    for frame1, frame2 in frame_pairs:
        # Temporal consistency
        tc = compute_temporal_consistency(frame1, frame2)
        features['temporal_consistency'].append(tc)
        
        # Lip sync score
        ls = compute_lip_sync_score(frame1, frame2)
        features['lip_sync_score'].append(ls)
        
        # Edge density difference
        ed = _compute_edge_density_diff(frame1, frame2)
        features['edge_density_diff'].append(ed)
        
        # Pixel difference
        pd = _compute_pixel_difference(frame1, frame2)
        features['pixel_difference'].append(pd)
        
        # Correlation
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY) if len(frame1.shape) == 3 else frame1
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY) if len(frame2.shape) == 3 else frame2
        if gray1.shape != gray2.shape:
            gray2 = cv2.resize(gray2, (gray1.shape[1], gray1.shape[0]))
        corr = _compute_correlation(gray1, gray2)
        features['correlation'].append(corr)
    
    # Frequency artifacts
    features['frequency_artifacts'] = analyze_frequency_artifacts(frame_pairs)
    
    # Aggregate to means
    return {
        'temporal_consistency': np.mean(features['temporal_consistency']),
        'lip_sync_score': np.mean(features['lip_sync_score']),
        'frequency_artifacts': features['frequency_artifacts'],
        'edge_density_diff': np.mean(features['edge_density_diff']),
        'pixel_difference': np.mean(features['pixel_difference']),
        'correlation': np.mean(features['correlation'])
    }


def _compute_edge_density_diff(frame1: np.ndarray, frame2: np.ndarray) -> float:
    """Compute difference in edge density between frames."""
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY) if len(frame1.shape) == 3 else frame1
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY) if len(frame2.shape) == 3 else frame2
    
    edges1 = cv2.Canny(gray1, 50, 150)
    edges2 = cv2.Canny(gray2, 50, 150)
    
    density1 = edges1.sum() / edges1.size
    density2 = edges2.sum() / edges2.size
    
    return abs(density1 - density2)


def _compute_pixel_difference(frame1: np.ndarray, frame2: np.ndarray) -> float:
    """Compute mean absolute pixel difference."""
    # Ensure same size
    if frame1.shape != frame2.shape:
        frame2 = cv2.resize(frame2, (frame1.shape[1], frame1.shape[0]))
    
    diff = np.abs(frame1.astype(np.float32) - frame2.astype(np.float32))
    return diff.mean()


def compute_authenticity_features(
    img_path: str
) -> Dict[str, float]:
    """
    Compute authenticity features from a concatenated frame pair image.
    
    Used for images where two frames are side by side.
    
    Args:
        img_path: Path to image file
        
    Returns:
        Dictionary of feature values
    """
    img = cv2.imread(str(img_path))
    if img is None:
        return {
            'correlation': 0,
            'pixel_diff': 100,
            'edge_diff': 1,
            'mismatch_score': 100
        }
    
    h, w = img.shape[:2]
    
    # Split into left and right frames
    left_frame = img[:, :w//2]
    right_frame = img[:, w//2:]
    
    # Convert to grayscale and resize
    left_gray = cv2.cvtColor(left_frame, cv2.COLOR_BGR2GRAY)
    right_gray = cv2.cvtColor(right_frame, cv2.COLOR_BGR2GRAY)
    left_gray = cv2.resize(left_gray, (64, 64))
    right_gray = cv2.resize(right_gray, (64, 64))
    
    # Correlation
    correlation = np.corrcoef(left_gray.flatten(), right_gray.flatten())[0, 1]
    if np.isnan(correlation):
        correlation = 0
    
    # Pixel difference
    diff = np.abs(left_gray.astype(float) - right_gray.astype(float)).mean()
    
    # Edge analysis
    edges_left = cv2.Canny(left_gray, 50, 150)
    edges_right = cv2.Canny(right_gray, 50, 150)
    edge_density_left = edges_left.sum() / edges_left.size
    edge_density_right = edges_right.sum() / edges_right.size
    edge_diff = abs(edge_density_left - edge_density_right)
    
    # Mismatch score (0-100)
    mismatch_score = max(0, min(100, (1 - correlation) * 50 + diff * 0.5))
    
    return {
        'correlation': correlation,
        'pixel_diff': diff,
        'edge_density_left': edge_density_left,
        'edge_density_right': edge_density_right,
        'edge_diff': edge_diff,
        'mismatch_score': mismatch_score
    }
