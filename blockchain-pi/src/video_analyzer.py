"""
Lightweight Video Analyzer for Raspberry Pi.

Uses ONLY handcrafted features (no CNN / PyTorch) to stay within
the Pi's memory constraints. Extracts:
  • Optical flow irregularities
  • Colour histogram anomalies
  • Edge consistency
  • Frequency-domain (FFT) artefacts
  • Noise pattern analysis
"""

import hashlib
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy import fftpack, stats

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    content_hash: str          # SHA-256 of file
    perceptual_hash: str       # Concatenated pHash of sampled frames
    is_deepfake: bool
    confidence: float          # 0.0 – 100.0
    lipsync_score: float       # 0.0 – 100.0 (estimated from flow)
    fact_check_score: float    # N/A for Pi — always 0
    feature_scores: Dict[str, float] = field(default_factory=dict)
    frame_count: int = 0
    duration_seconds: float = 0.0
    error: str = ""


class VideoAnalyzer:
    """
    Lightweight deepfake detector for Raspberry Pi.
    """

    def __init__(
        self,
        max_frames: int = 5,
        frame_interval: int = 30,
        confidence_threshold: float = 65.0,
        max_file_size_mb: int = 200,
        temp_dir: str = "/tmp/deepfake-pi",
    ):
        self.max_frames = max_frames
        self.frame_interval = frame_interval
        self.confidence_threshold = confidence_threshold
        self.max_file_size_mb = max_file_size_mb
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Main analysis entry point
    # ------------------------------------------------------------------

    def analyze(self, video_path: str) -> AnalysisResult:
        """Analyze a video file and return detection result."""
        path = Path(video_path)
        if not path.exists():
            return AnalysisResult(
                content_hash="", perceptual_hash="",
                is_deepfake=False, confidence=0,
                lipsync_score=0, fact_check_score=0,
                error=f"File not found: {video_path}",
            )

        # File size check
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self.max_file_size_mb:
            return AnalysisResult(
                content_hash="", perceptual_hash="",
                is_deepfake=False, confidence=0,
                lipsync_score=0, fact_check_score=0,
                error=f"File too large: {size_mb:.1f}MB > {self.max_file_size_mb}MB",
            )

        # Compute content hash
        content_hash = self._compute_sha256(path)

        # Open video and extract frames
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return AnalysisResult(
                content_hash=content_hash, perceptual_hash="",
                is_deepfake=False, confidence=0,
                lipsync_score=0, fact_check_score=0,
                error="Cannot open video file",
            )

        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        frames = self._sample_frames(cap, total_frames)
        cap.release()

        if len(frames) < 2:
            return AnalysisResult(
                content_hash=content_hash, perceptual_hash="",
                is_deepfake=False, confidence=0,
                lipsync_score=0, fact_check_score=0,
                frame_count=len(frames),
                duration_seconds=duration,
                error="Not enough frames extracted",
            )

        # Compute perceptual hash
        perceptual_hash = self._compute_perceptual_hash(frames)

        # Run feature extractors
        scores: Dict[str, float] = {}
        scores["optical_flow"] = self._analyze_optical_flow(frames)
        scores["color_histogram"] = self._analyze_color_histogram(frames)
        scores["edge_detection"] = self._analyze_edge_consistency(frames)
        scores["frequency_analysis"] = self._analyze_frequency(frames)
        scores["noise_analysis"] = self._analyze_noise_patterns(frames)

        # Aggregate score (weighted average)
        weights = {
            "optical_flow": 0.25,
            "color_histogram": 0.15,
            "edge_detection": 0.20,
            "frequency_analysis": 0.25,
            "noise_analysis": 0.15,
        }
        confidence = sum(scores[k] * weights[k] for k in weights)
        is_deepfake = confidence >= self.confidence_threshold

        # Estimate lipsync score from optical flow
        lipsync_score = max(0, 100 - scores["optical_flow"])

        logger.info(
            "Analysis complete: hash=%s…, deepfake=%s, confidence=%.1f%%",
            content_hash[:16], is_deepfake, confidence,
        )

        return AnalysisResult(
            content_hash=content_hash,
            perceptual_hash=perceptual_hash,
            is_deepfake=is_deepfake,
            confidence=confidence,
            lipsync_score=lipsync_score,
            fact_check_score=0.0,
            feature_scores=scores,
            frame_count=len(frames),
            duration_seconds=duration,
        )

    # ------------------------------------------------------------------
    # Frame sampling
    # ------------------------------------------------------------------

    def _sample_frames(self, cap, total_frames: int) -> List[np.ndarray]:
        """Sample evenly spaced frames from the video."""
        if total_frames <= 0:
            return []

        indices = np.linspace(0, total_frames - 1, self.max_frames, dtype=int)
        frames = []

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ret, frame = cap.read()
            if ret:
                # Resize to 256x256 for consistent analysis and memory savings
                frame = cv2.resize(frame, (256, 256))
                frames.append(frame)

        return frames

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _analyze_optical_flow(self, frames: List[np.ndarray]) -> float:
        """
        Check inter-frame motion consistency using Farneback optical flow.
        Deepfakes often have unnatural motion patterns.
        Score: 0 (natural) to 100 (suspicious).
        """
        scores = []
        for i in range(len(frames) - 1):
            gray1 = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(frames[i + 1], cv2.COLOR_BGR2GRAY)

            flow = cv2.calcOpticalFlowFarneback(
                gray1, gray2, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )

            # Compute magnitude and angle
            mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])

            # Check for unnatural uniformity in motion
            mag_std = np.std(mag)
            ang_std = np.std(ang)

            # Very low variance = possibly synthetic
            motion_score = 0
            if mag_std < 0.5:
                motion_score += 30
            if ang_std < 0.3:
                motion_score += 20

            # Check for boundary artefacts (flow discontinuities around face)
            center = mag[64:192, 64:192]
            border = np.concatenate([
                mag[:64, :].flatten(),
                mag[192:, :].flatten(),
                mag[:, :64].flatten(),
                mag[:, 192:].flatten(),
            ])
            if len(border) > 0 and np.mean(center) > 0:
                ratio = np.mean(border) / (np.mean(center) + 1e-6)
                if ratio > 3.0 or ratio < 0.1:
                    motion_score += 30

            scores.append(min(100, motion_score))

        return np.mean(scores) if scores else 0

    def _analyze_color_histogram(self, frames: List[np.ndarray]) -> float:
        """
        Detect unnatural colour distribution shifts between frames.
        Score: 0 (natural) to 100 (suspicious).
        """
        histograms = []
        for frame in frames:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            histograms.append(hist)

        # Compare adjacent frame histograms
        diffs = []
        for i in range(len(histograms) - 1):
            corr = cv2.compareHist(histograms[i], histograms[i + 1], cv2.HISTCMP_BHATTACHARYYA)
            diffs.append(corr)

        if not diffs:
            return 0

        # High variance in histogram correlation suggests manipulation
        mean_diff = np.mean(diffs)
        std_diff = np.std(diffs)

        score = 0
        if mean_diff > 0.4:
            score += 40
        if std_diff > 0.2:
            score += 30
        if max(diffs) > 0.7:
            score += 30

        return min(100, score)

    def _analyze_edge_consistency(self, frames: List[np.ndarray]) -> float:
        """
        Detect edge artefacts common in deepfakes (blurry boundaries, etc.).
        Score: 0 (natural) to 100 (suspicious).
        """
        scores = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)

            # Laplacian variance (blur detection)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

            frame_score = 0
            # Very low edge density could indicate over-smoothing
            edge_density = np.count_nonzero(edges) / edges.size
            if edge_density < 0.02:
                frame_score += 40

            # Low Laplacian variance = blurry (common in generated faces)
            if laplacian_var < 100:
                frame_score += 30

            # Check for unnatural edge patterns in centre (face region)
            centre_edges = edges[64:192, 64:192]
            centre_density = np.count_nonzero(centre_edges) / centre_edges.size
            if centre_density < 0.01:
                frame_score += 30

            scores.append(min(100, frame_score))

        return np.mean(scores) if scores else 0

    def _analyze_frequency(self, frames: List[np.ndarray]) -> float:
        """
        FFT-based analysis to detect GAN artefacts in frequency domain.
        Score: 0 (natural) to 100 (suspicious).
        """
        scores = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(float)

            # 2D FFT
            f_transform = fftpack.fft2(gray)
            f_shifted = fftpack.fftshift(f_transform)
            magnitude = np.abs(f_shifted)
            log_magnitude = np.log1p(magnitude)

            # Check for periodic artefacts (peaks in frequency domain)
            h, w = log_magnitude.shape
            centre_y, centre_x = h // 2, w // 2

            # Radial average
            Y, X = np.ogrid[:h, :w]
            r = np.sqrt((X - centre_x) ** 2 + (Y - centre_y) ** 2).astype(int)
            max_r = min(centre_x, centre_y)

            radial_profile = np.zeros(max_r)
            for radius in range(max_r):
                mask = r == radius
                if np.any(mask):
                    radial_profile[radius] = np.mean(log_magnitude[mask])

            # GAN artefacts often show unexpected peaks in mid-frequencies
            mid_start = max_r // 4
            mid_end = 3 * max_r // 4
            mid_freq = radial_profile[mid_start:mid_end]

            frame_score = 0
            if len(mid_freq) > 2:
                # Check for sharp peaks
                peaks = np.where(mid_freq > np.mean(mid_freq) + 2 * np.std(mid_freq))[0]
                if len(peaks) > 3:
                    frame_score += 50

                # Check frequency distribution kurtosis
                kurt = stats.kurtosis(mid_freq)
                if abs(kurt) > 5:
                    frame_score += 30

            scores.append(min(100, frame_score))

        return np.mean(scores) if scores else 0

    def _analyze_noise_patterns(self, frames: List[np.ndarray]) -> float:
        """
        Detect inconsistent noise patterns that indicate synthesis.
        Score: 0 (natural) to 100 (suspicious).
        """
        scores = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(float)

            # Extract noise using median filter difference
            denoised = cv2.medianBlur(gray.astype(np.uint8), 3).astype(float)
            noise = gray - denoised

            # Split into regions and compare noise characteristics
            h, w = noise.shape
            regions = [
                noise[:h // 2, :w // 2],   # top-left
                noise[:h // 2, w // 2:],    # top-right
                noise[h // 2:, :w // 2],    # bottom-left
                noise[h // 2:, w // 2:],    # bottom-right
            ]

            region_stds = [np.std(r) for r in regions]
            region_means = [np.mean(np.abs(r)) for r in regions]

            frame_score = 0

            # Very different noise levels between regions = manipulation
            std_range = max(region_stds) - min(region_stds)
            if std_range > 3.0:
                frame_score += 40

            # Very low overall noise = possibly synthetic
            overall_std = np.std(noise)
            if overall_std < 1.0:
                frame_score += 30

            # Unnatural noise distribution (should be roughly Gaussian)
            noise_flat = noise.flatten()
            if len(noise_flat) > 100:
                _, p_value = stats.normaltest(noise_flat[:1000])
                if p_value < 0.001:
                    frame_score += 30

            scores.append(min(100, frame_score))

        return np.mean(scores) if scores else 0

    # ------------------------------------------------------------------
    # Hashing
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def _compute_perceptual_hash(frames: List[np.ndarray]) -> str:
        """Compute DCT-based perceptual hash by concatenating frame hashes."""
        hashes = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (32, 32))
            dct = cv2.dct(resized.astype(np.float64))
            dct_low = dct[:8, :8]
            median = np.median(dct_low)
            bits = (dct_low > median).flatten()
            hex_str = hex(int("".join(str(int(b)) for b in bits), 2))[2:].zfill(16)
            hashes.append(hex_str[:8].upper())
        return "-".join(hashes)
