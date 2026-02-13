"""
Gemini Deepfake Verifier Extension
==================================
Extends GeminiFactChecker with direct deepfake verification capability.

This module adds a hidden signal that directly asks Gemini to analyze
video frames for deepfake manipulation signs. This is a supplementary
verification layer not exposed in the presentation UI.
"""

import os
import cv2
import time
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass


@dataclass
class GeminiDeepfakeVerdict:
    """Result from Gemini direct deepfake verification."""
    
    is_deepfake: bool = False
    confidence: float = 0.5  # 0-1 scale
    manipulation_score: float = 0.5  # 0=real, 1=fake
    
    # Analysis details
    lip_sync_issues: bool = False
    face_blending_artifacts: bool = False
    lighting_inconsistencies: bool = False
    temporal_anomalies: bool = False
    texture_abnormalities: bool = False
    
    # Reasoning
    reasoning: str = ""
    detailed_analysis: str = ""
    
    # Metadata
    frames_analyzed: int = 0
    processing_time: float = 0.0
    model_used: str = ""


class GeminiDeepfakeVerifier:
    """
    Direct deepfake verification using Gemini multimodal AI.
    
    This is a HIDDEN signal not exposed in the presentation layer.
    It provides supplementary verification by directly asking Gemini
    to analyze video frames for deepfake manipulation signs.
    
    The verification focuses on:
    1. Lip-sync inconsistencies
    2. Face blending artifacts
    3. Lighting mismatches
    4. Temporal anomalies
    5. Texture abnormalities (uncanny valley)
    """
    
    # Direct deepfake analysis prompt
    DEEPFAKE_ANALYSIS_PROMPT = """You are a forensic video analyst specializing in deepfake detection. 
Analyze these video frames carefully for signs of AI-generated or manipulated facial content.

Examine EACH of these specific manipulation indicators:

1. LIP SYNC: Do the lip movements appear natural and synchronized with potential speech? 
   Look for jerky movements, misaligned phonemes, or unnatural mouth shapes.

2. FACE BLENDING: Check the face boundary for blending artifacts, edge misalignment, 
   color discontinuities, or unnatural transitions between face and background.

3. LIGHTING: Analyze lighting consistency - are shadows, reflections, and highlights 
   consistent with a single light source? Look for impossible lighting scenarios.

4. TEMPORAL: Do these frames show natural motion progression? Look for flickering, 
   morphing, or unnatural frame-to-frame transitions in facial features.

5. TEXTURE: Check for AI-typical artifacts - overly smooth skin, perfect symmetry, 
   missing pores/wrinkles, uncanny valley features, or synthetic-looking eyes.

Provide your analysis in EXACTLY this format:

VERDICT: [REAL/FAKE/UNCERTAIN]
CONFIDENCE: [0-100 percentage]
MANIPULATION_SCORE: [0-10 where 0=definitely real, 10=definitely AI-generated]

LIP_SYNC_ISSUES: [YES/NO]
FACE_BLENDING_ARTIFACTS: [YES/NO]
LIGHTING_INCONSISTENCIES: [YES/NO]
TEMPORAL_ANOMALIES: [YES/NO]
TEXTURE_ABNORMALITIES: [YES/NO]

REASONING: [2-3 sentences explaining your key observations]

DETAILED_ANALYSIS: [Technical breakdown of what you observed in each category]

Be thorough but objective. Only mark as FAKE if you see clear manipulation signs."""

    MULTI_FRAME_COMPARISON_PROMPT = """Compare these consecutive video frames for deepfake indicators.

Focus on TEMPORAL consistency:
1. Do facial features maintain consistent shape across frames?
2. Are there any morphing or warping artifacts between frames?
3. Do eyes blink naturally? Is there unnatural eye movement?
4. Are lip movements smooth and natural between frames?
5. Is there any flickering or instability in the face region?

Frame-by-frame analysis:
- Look for "jumps" in facial position or expression
- Check for inconsistent head pose transitions
- Examine micro-expressions for authenticity

Respond in this format:
TEMPORAL_VERDICT: [NATURAL/SUSPICIOUS/MANIPULATED]
CONSISTENCY_SCORE: [0-10 where 10=perfectly consistent, 0=clearly manipulated]
KEY_FINDINGS: [What specific temporal issues did you observe?]"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        num_frames: int = 8,
        max_retries: int = 3
    ):
        """
        Initialize the Gemini deepfake verifier.
        
        Args:
            api_key: Google Gemini API key
            model: Gemini model to use
            num_frames: Number of frames to analyze
            max_retries: Maximum API retry attempts
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        self.model = model
        self.num_frames = num_frames
        self.max_retries = max_retries
        
        self._client = None
        self._genai = None
        
        if self.api_key:
            self._init_client()
    
    def _init_client(self):
        """Initialize Gemini client."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._genai = genai
            self._client = genai.GenerativeModel(self.model)
        except ImportError:
            print("Warning: google-generativeai not installed")
            self._client = None
        except Exception as e:
            print(f"Warning: Could not initialize Gemini: {e}")
            self._client = None
    
    @property
    def is_available(self) -> bool:
        """Check if Gemini API is available."""
        return self._client is not None
    
    def _extract_analysis_frames(
        self, 
        video_path: str
    ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """
        Extract frames for analysis.
        
        Returns:
            Tuple of (evenly_spaced_frames, consecutive_frame_pairs)
        """
        cap = cv2.VideoCapture(str(video_path))
        
        if not cap.isOpened():
            return [], []
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        # Get evenly spaced frames for overall analysis
        spaced_indices = np.linspace(0, total_frames - 1, self.num_frames, dtype=int)
        spaced_frames = []
        
        for idx in spaced_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                spaced_frames.append(frame)
        
        # Get consecutive frames from middle for temporal analysis
        mid_point = total_frames // 2
        consecutive_frames = []
        
        for i in range(min(4, total_frames)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, mid_point + i)
            ret, frame = cap.read()
            if ret:
                consecutive_frames.append(frame)
        
        cap.release()
        return spaced_frames, consecutive_frames
    
    def _frames_to_pil_images(self, frames: List[np.ndarray]):
        """Convert frames to PIL images."""
        from PIL import Image
        pil_images = []
        for frame in frames:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_images.append(Image.fromarray(rgb))
        return pil_images
    
    def _create_frame_grid(
        self, 
        frames: List[np.ndarray], 
        grid_cols: int = 4
    ) -> np.ndarray:
        """Create a grid image from multiple frames."""
        if not frames:
            return None
        
        # Resize all frames to consistent size
        target_size = (320, 240)
        resized = [cv2.resize(f, target_size) for f in frames]
        
        # Calculate grid dimensions
        n_frames = len(resized)
        grid_rows = (n_frames + grid_cols - 1) // grid_cols
        
        # Pad with black frames if needed
        while len(resized) < grid_rows * grid_cols:
            resized.append(np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8))
        
        # Create grid
        rows = []
        for i in range(grid_rows):
            row_frames = resized[i*grid_cols:(i+1)*grid_cols]
            rows.append(np.hstack(row_frames))
        
        return np.vstack(rows)
    
    def _call_gemini_with_images(
        self, 
        prompt: str, 
        images: List
    ) -> Optional[str]:
        """Make Gemini API call with multiple images."""
        if not self.is_available:
            return None
        
        for attempt in range(self.max_retries):
            try:
                content = [prompt] + images
                response = self._client.generate_content(
                    content,
                    generation_config={
                        "max_output_tokens": 1000,
                        "temperature": 0.1
                    }
                )
                return response.text
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    time.sleep(wait_time)
                else:
                    print(f"Gemini API failed: {e}")
                    return None
        return None
    
    def _parse_deepfake_response(self, response: str) -> Dict[str, Any]:
        """Parse the deepfake analysis response."""
        import re
        
        result = {
            'verdict': 'UNCERTAIN',
            'confidence': 50,
            'manipulation_score': 5,
            'lip_sync_issues': False,
            'face_blending_artifacts': False,
            'lighting_inconsistencies': False,
            'temporal_anomalies': False,
            'texture_abnormalities': False,
            'reasoning': '',
            'detailed_analysis': ''
        }
        
        if not response:
            return result
        
        # Parse verdict
        verdict_match = re.search(r'VERDICT:\s*(REAL|FAKE|UNCERTAIN)', response, re.IGNORECASE)
        if verdict_match:
            result['verdict'] = verdict_match.group(1).upper()
        
        # Parse confidence
        conf_match = re.search(r'CONFIDENCE:\s*(\d+)', response, re.IGNORECASE)
        if conf_match:
            result['confidence'] = int(conf_match.group(1))
        
        # Parse manipulation score
        score_match = re.search(r'MANIPULATION_SCORE:\s*(\d+(?:\.\d+)?)', response, re.IGNORECASE)
        if score_match:
            result['manipulation_score'] = float(score_match.group(1))
        
        # Parse boolean flags
        for flag in ['LIP_SYNC_ISSUES', 'FACE_BLENDING_ARTIFACTS', 
                     'LIGHTING_INCONSISTENCIES', 'TEMPORAL_ANOMALIES', 
                     'TEXTURE_ABNORMALITIES']:
            match = re.search(rf'{flag}:\s*(YES|NO)', response, re.IGNORECASE)
            if match:
                key = flag.lower()
                result[key] = match.group(1).upper() == 'YES'
        
        # Parse reasoning
        reasoning_match = re.search(
            r'REASONING:\s*(.+?)(?=DETAILED_ANALYSIS:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            result['reasoning'] = reasoning_match.group(1).strip()
        
        # Parse detailed analysis
        detail_match = re.search(
            r'DETAILED_ANALYSIS:\s*(.+?)$', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if detail_match:
            result['detailed_analysis'] = detail_match.group(1).strip()
        
        return result
    
    def verify_video(self, video_path: str) -> GeminiDeepfakeVerdict:
        """
        Perform direct deepfake verification on a video.
        
        This is the main entry point for hidden Gemini verification.
        NOT exposed in the presentation layer.
        
        Args:
            video_path: Path to video file
            
        Returns:
            GeminiDeepfakeVerdict with analysis results
        """
        start_time = time.time()
        
        if not self.is_available:
            return GeminiDeepfakeVerdict(
                reasoning="Gemini API not available",
                processing_time=0
            )
        
        # Extract frames
        spaced_frames, consecutive_frames = self._extract_analysis_frames(video_path)
        
        if not spaced_frames:
            return GeminiDeepfakeVerdict(
                reasoning="Could not extract frames from video",
                processing_time=time.time() - start_time
            )
        
        # Convert to PIL images
        pil_images = self._frames_to_pil_images(spaced_frames[:6])  # Limit to 6 frames
        
        # Run main deepfake analysis
        response = self._call_gemini_with_images(
            self.DEEPFAKE_ANALYSIS_PROMPT,
            pil_images
        )
        
        parsed = self._parse_deepfake_response(response)
        
        # Build result
        is_deepfake = parsed['verdict'] == 'FAKE'
        confidence = parsed['confidence'] / 100.0
        
        # Count manipulation indicators
        indicators_found = sum([
            parsed['lip_sync_issues'],
            parsed['face_blending_artifacts'],
            parsed['lighting_inconsistencies'],
            parsed['temporal_anomalies'],
            parsed['texture_abnormalities']
        ])
        
        # Adjust confidence based on indicators
        if indicators_found >= 3:
            confidence = min(0.95, confidence * 1.2)
        elif indicators_found == 0 and not is_deepfake:
            confidence = min(0.95, confidence * 1.1)
        
        return GeminiDeepfakeVerdict(
            is_deepfake=is_deepfake,
            confidence=confidence,
            manipulation_score=parsed['manipulation_score'] / 10.0,
            lip_sync_issues=parsed['lip_sync_issues'],
            face_blending_artifacts=parsed['face_blending_artifacts'],
            lighting_inconsistencies=parsed['lighting_inconsistencies'],
            temporal_anomalies=parsed['temporal_anomalies'],
            texture_abnormalities=parsed['texture_abnormalities'],
            reasoning=parsed['reasoning'],
            detailed_analysis=parsed['detailed_analysis'],
            frames_analyzed=len(spaced_frames),
            processing_time=time.time() - start_time,
            model_used=self.model
        )
    
    def quick_verify(self, video_path: str) -> Dict[str, Any]:
        """
        Quick verification returning dictionary format.
        Convenience method for API integration.
        """
        result = self.verify_video(video_path)
        return {
            'is_deepfake': result.is_deepfake,
            'confidence': result.confidence,
            'manipulation_score': result.manipulation_score,
            'indicators': {
                'lip_sync': result.lip_sync_issues,
                'face_blending': result.face_blending_artifacts,
                'lighting': result.lighting_inconsistencies,
                'temporal': result.temporal_anomalies,
                'texture': result.texture_abnormalities
            },
            'reasoning': result.reasoning,
            'processing_time': result.processing_time
        }


# Convenience function for integration
def verify_deepfake_with_gemini(
    video_path: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    One-shot function to verify a video using Gemini.
    
    Args:
        video_path: Path to video
        api_key: Optional API key (uses env var if not provided)
        
    Returns:
        Dictionary with verification results
    """
    verifier = GeminiDeepfakeVerifier(api_key=api_key)
    return verifier.quick_verify(video_path)
