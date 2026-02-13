"""
Video Processing Utilities
==========================
Functions for video frame extraction, face detection, and preprocessing.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Union


def extract_frames(
    video_path: str,
    count: int = 5,
    distribution: str = 'uniform'
) -> List[np.ndarray]:
    """
    Extract frames from a video file.
    
    Args:
        video_path: Path to video file
        count: Number of frames to extract
        distribution: 'uniform' for evenly spaced, 'random' for random selection
        
    Returns:
        List of frames as numpy arrays (BGR format)
    """
    cap = cv2.VideoCapture(str(video_path))
    frames = []
    
    if not cap.isOpened():
        return frames
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames == 0:
        cap.release()
        return frames
    
    if total_frames < count:
        indices = list(range(total_frames))
    elif distribution == 'uniform':
        indices = np.linspace(0, total_frames - 1, count, dtype=int)
    else:  # random
        indices = sorted(np.random.choice(total_frames, count, replace=False))
    
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    
    cap.release()
    return frames


def extract_consecutive_frame_pairs(
    video_path: str,
    num_pairs: int = 10
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Extract pairs of consecutive frames for temporal analysis.
    
    Args:
        video_path: Path to video file
        num_pairs: Number of frame pairs to extract
        
    Returns:
        List of (frame_i, frame_i+1) tuples
    """
    cap = cv2.VideoCapture(str(video_path))
    pairs = []
    
    if not cap.isOpened():
        return pairs
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if total_frames < 2:
        cap.release()
        return pairs
    
    # Calculate indices for first frame of each pair
    max_start_idx = total_frames - 2
    if max_start_idx < num_pairs:
        indices = list(range(max_start_idx + 1))
    else:
        indices = np.linspace(0, max_start_idx, num_pairs, dtype=int)
    
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret1, frame1 = cap.read()
        ret2, frame2 = cap.read()
        
        if ret1 and ret2:
            pairs.append((frame1, frame2))
    
    cap.release()
    return pairs


def detect_and_crop_face(
    frame: np.ndarray,
    padding: float = 0.15,
    min_face_size: Tuple[int, int] = (50, 50)
) -> np.ndarray:
    """
    Detect and crop face region from a frame.
    
    Args:
        frame: Input frame (BGR format)
        padding: Padding around detected face as fraction of face size
        min_face_size: Minimum face size to detect
        
    Returns:
        Cropped face region, or original frame if no face detected
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Load face cascade
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )
    
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=min_face_size
    )
    
    if len(faces) == 0:
        return frame
    
    # Use largest face
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    
    # Add padding
    pad = int(w * padding)
    x = max(0, x - pad)
    y = max(0, y - pad)
    w = min(frame.shape[1] - x, w + 2 * pad)
    h = min(frame.shape[0] - y, h + 2 * pad)
    
    return frame[y:y+h, x:x+w]


def extract_lip_region(
    face_img: np.ndarray,
    lip_ratio: Tuple[float, float, float, float] = (0.55, 0.95, 0.15, 0.85)
) -> np.ndarray:
    """
    Extract the lip/mouth region from a face image.
    
    Args:
        face_img: Face image
        lip_ratio: (y_start, y_end, x_start, x_end) as fractions
        
    Returns:
        Cropped lip region
    """
    h, w = face_img.shape[:2]
    y_start, y_end, x_start, x_end = lip_ratio
    
    lip_y_start = int(h * y_start)
    lip_y_end = int(h * y_end)
    lip_x_start = int(w * x_start)
    lip_x_end = int(w * x_end)
    
    return face_img[lip_y_start:lip_y_end, lip_x_start:lip_x_end]


def get_video_info(video_path: str) -> dict:
    """
    Get video metadata.
    
    Args:
        video_path: Path to video file
        
    Returns:
        Dictionary with video info
    """
    cap = cv2.VideoCapture(str(video_path))
    
    info = {
        'path': str(video_path),
        'exists': cap.isOpened(),
        'frame_count': 0,
        'fps': 0,
        'width': 0,
        'height': 0,
        'duration': 0
    }
    
    if cap.isOpened():
        info['frame_count'] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        info['fps'] = cap.get(cv2.CAP_PROP_FPS)
        info['width'] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        info['height'] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        if info['fps'] > 0:
            info['duration'] = info['frame_count'] / info['fps']
    
    cap.release()
    return info


def preprocess_frame(
    frame: np.ndarray,
    target_size: Tuple[int, int] = (224, 224),
    normalize: bool = True,
    mean: List[float] = [0.485, 0.456, 0.406],
    std: List[float] = [0.229, 0.224, 0.225]
) -> np.ndarray:
    """
    Preprocess a frame for model input.
    
    Args:
        frame: Input frame (BGR format)
        target_size: Target (height, width)
        normalize: Whether to apply ImageNet normalization
        mean: Normalization mean values
        std: Normalization std values
        
    Returns:
        Preprocessed frame
    """
    # Resize
    resized = cv2.resize(frame, (target_size[1], target_size[0]))
    
    # Convert to RGB and float
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    processed = rgb.astype(np.float32) / 255.0
    
    # Normalize
    if normalize:
        processed = (processed - mean) / std
    
    return processed


def split_frame_pair(frame: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Split a horizontally concatenated frame pair.
    
    Args:
        frame: Frame containing two frames side by side
        
    Returns:
        Tuple of (left_frame, right_frame)
    """
    h, w = frame.shape[:2]
    mid = w // 2
    return frame[:, :mid], frame[:, mid:]
