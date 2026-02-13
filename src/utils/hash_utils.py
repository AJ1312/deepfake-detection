"""
Hash Utilities
==============
Functions for computing perceptual and content hashes for video fingerprinting.
"""

import hashlib
import numpy as np
import cv2
from typing import List, Tuple, Union


def compute_perceptual_hash(
    image: np.ndarray,
    hash_size: int = 8
) -> int:
    """
    Compute perceptual hash (pHash) using DCT.
    
    Algorithm:
    1. Convert to grayscale
    2. Resize to (hash_size+1) × (hash_size+1)
    3. Compute DCT
    4. Keep top-left hash_size × hash_size coefficients
    5. Create binary hash based on median
    
    Args:
        image: Input image (BGR or grayscale)
        hash_size: Size of hash (8 = 64-bit hash)
        
    Returns:
        Integer perceptual hash
    """
    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    
    # Resize to hash_size+1 (need extra for DCT)
    resized = cv2.resize(
        gray,
        (hash_size + 1, hash_size + 1),
        interpolation=cv2.INTER_LINEAR
    ).astype(np.float32)
    
    # Compute DCT
    dct = cv2.dct(resized)
    
    # Keep top-left coefficients (low frequency)
    dct_cropped = dct[:hash_size, :hash_size]
    
    # Compute median
    median = np.median(dct_cropped)
    
    # Create binary hash
    hash_bits = (dct_cropped > median).flatten()
    
    # Convert to integer
    hash_int = 0
    for bit in hash_bits:
        hash_int = (hash_int << 1) | int(bit)
    
    return hash_int


def compute_dhash(
    image: np.ndarray,
    hash_size: int = 8
) -> int:
    """
    Compute difference hash (dHash).
    
    Compares adjacent pixels horizontally to create hash.
    More robust to slight scaling changes than pHash.
    
    Args:
        image: Input image
        hash_size: Size of hash (8 = 64-bit hash)
        
    Returns:
        Integer difference hash
    """
    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    
    # Resize to (hash_size+1) x hash_size (extra column for differences)
    resized = cv2.resize(
        gray,
        (hash_size + 1, hash_size),
        interpolation=cv2.INTER_LINEAR
    )
    
    # Compute differences
    diff = resized[:, 1:] > resized[:, :-1]
    
    # Convert to integer
    hash_int = 0
    for bit in diff.flatten():
        hash_int = (hash_int << 1) | int(bit)
    
    return hash_int


def compute_content_hash(
    data: Union[bytes, np.ndarray, List[np.ndarray]],
    algorithm: str = 'sha256'
) -> str:
    """
    Compute content hash for exact matching.
    
    Args:
        data: Raw bytes, single frame, or list of frames
        algorithm: Hash algorithm ('sha256', 'md5', 'sha1')
        
    Returns:
        Hexadecimal hash string
    """
    if algorithm == 'sha256':
        hasher = hashlib.sha256()
    elif algorithm == 'md5':
        hasher = hashlib.md5()
    elif algorithm == 'sha1':
        hasher = hashlib.sha1()
    else:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    
    if isinstance(data, bytes):
        hasher.update(data)
    elif isinstance(data, np.ndarray):
        hasher.update(data.tobytes())
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, np.ndarray):
                hasher.update(item.tobytes())
            else:
                hasher.update(bytes(item))
    
    return hasher.hexdigest()


def hamming_distance(hash1: int, hash2: int) -> int:
    """
    Compute Hamming distance between two hashes.
    
    Args:
        hash1, hash2: Integer hashes to compare
        
    Returns:
        Number of differing bits
    """
    xor_result = hash1 ^ hash2
    return bin(xor_result).count('1')


def are_videos_similar(
    phash1: str,
    phash2: str,
    threshold: int = 10
) -> Tuple[bool, float]:
    """
    Determine if two videos are similar based on perceptual hashes.
    
    Args:
        phash1, phash2: Concatenated perceptual hashes ("hash1-hash2-...")
        threshold: Maximum average Hamming distance to consider similar
        
    Returns:
        Tuple of (is_similar, average_distance)
    """
    hashes1 = phash1.split('-')
    hashes2 = phash2.split('-')
    
    if len(hashes1) != len(hashes2):
        return False, float('inf')
    
    total_distance = 0
    for h1, h2 in zip(hashes1, hashes2):
        try:
            hash1_int = int(h1)
            hash2_int = int(h2)
            distance = hamming_distance(hash1_int, hash2_int)
            total_distance += distance
        except (ValueError, TypeError):
            return False, float('inf')
    
    avg_distance = total_distance / len(hashes1)
    is_similar = avg_distance <= threshold
    
    return is_similar, avg_distance


def compute_video_fingerprint(
    frames: List[np.ndarray],
    hash_size: int = 8
) -> Tuple[str, str]:
    """
    Compute complete video fingerprint.
    
    Args:
        frames: List of video frames
        hash_size: Size for perceptual hashes
        
    Returns:
        Tuple of (content_hash, perceptual_hash_string)
    """
    # Content hash
    content_hash = compute_content_hash(frames)
    
    # Perceptual hashes
    phashes = []
    for frame in frames:
        phash = compute_perceptual_hash(frame, hash_size)
        phashes.append(str(phash))
    
    perceptual_hash = '-'.join(phashes)
    
    return content_hash, perceptual_hash


def hash_similarity_score(
    phash1: str,
    phash2: str,
    max_distance: int = 64
) -> float:
    """
    Compute similarity score between two perceptual hashes.
    
    Args:
        phash1, phash2: Perceptual hash strings
        max_distance: Maximum possible distance (64 for 64-bit hash)
        
    Returns:
        Similarity score from 0 (completely different) to 1 (identical)
    """
    is_similar, avg_distance = are_videos_similar(phash1, phash2, threshold=max_distance)
    
    if avg_distance == float('inf'):
        return 0.0
    
    # Convert distance to similarity
    similarity = 1.0 - (avg_distance / max_distance)
    return max(0.0, min(1.0, similarity))
