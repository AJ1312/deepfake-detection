"""
Enhanced Deepfake Detector
==========================
Main detection pipeline integrating all components:
- Video Hash Cache (50x faster re-detection)
- Lip-Sync CNN Model (primary detection)
- Gemini Fact-Checker (external verification)

The pipeline uses weighted fusion:
- Lip-sync analysis: 70% weight
- Fact-checking: 30% weight

With confidence boosting when both agree, and flagging when they disagree.
"""

import os
import time
import numpy as np
import cv2
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings

# Try to import PyTorch (optional)
TORCH_AVAILABLE = False
torch = None
nn = None
try:
    import torch as _torch
    import torch.nn as _nn
    torch = _torch
    nn = _nn
    TORCH_AVAILABLE = True
except ImportError:
    pass

# Import our components
from ..core.detection_result import DetectionResult
from ..core.video_hash_cache import VideoHashCache
from ..core.gemini_fact_checker import GeminiFactChecker, FactCheckResult
from ..utils.video_processing import (
    extract_frames,
    extract_consecutive_frame_pairs,
    preprocess_frame
)
from ..utils.feature_extractors import (
    compute_temporal_consistency,
    analyze_frequency_artifacts,
    compute_lip_sync_score,
    extract_handcrafted_features
)


class EnhancedDeepfakeDetector:
    """
    Enhanced multi-tier deepfake detection system.
    
    Architecture:
        Tier 1: Hash Cache - Instant re-detection (0.08s)
        Tier 2: Lip-Sync CNN - Primary analysis (3-5s)
        Tier 3: Gemini Fact-Check - External verification
    
    Fusion weights:
        - Lip-sync: 70%
        - Fact-check: 30%
    
    Confidence adjustments:
        - Agreement: +20% boost
        - Disagreement: -30% penalty, flag for review
    
    Attributes:
        lipsync_model: Trained lip-sync detection model
        cache: VideoHashCache for instant re-detection
        fact_checker: GeminiFactChecker for external verification
        device: PyTorch device (cuda/cpu)
    """
    
    # Fusion weights - adjusted for when PyTorch is not available
    # When using handcrafted features only, trust Gemini more
    LIPSYNC_WEIGHT = 0.7
    FACT_CHECK_WEIGHT = 0.3
    LIPSYNC_WEIGHT_NO_CNN = 0.3  # Lower weight when no CNN model
    FACT_CHECK_WEIGHT_NO_CNN = 0.7  # Higher weight for Gemini when no CNN
    AGREEMENT_BOOST = 1.2
    DISAGREEMENT_PENALTY = 0.7
    
    # Model configuration
    IMG_SIZE = (128, 256)  # Height x Width for paired frames
    NUM_FRAME_PAIRS = 10
    
    def __init__(
        self,
        lipsync_model_path: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        cache_db_path: str = "models/lipsync_cache.db",
        device: Optional[str] = None
    ):
        """
        Initialize the enhanced detector.
        
        Args:
            lipsync_model_path: Path to trained lip-sync model weights
            gemini_api_key: Google Gemini API key (or set GEMINI_API_KEY env)
            cache_db_path: Path to SQLite cache database
            device: PyTorch device ('cuda' or 'cpu')
        """
        # Set device (only if PyTorch available)
        if TORCH_AVAILABLE:
            if device is None:
                self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            else:
                self.device = torch.device(device)
            print(f"✓ Device: {self.device}")
        else:
            self.device = None
            print("⚠ PyTorch not available - using handcrafted features only")
        
        # Initialize cache
        self.cache = VideoHashCache(db_path=cache_db_path)
        print(f"✓ Video hash cache initialized: {cache_db_path}")
        
        # Initialize fact-checker
        api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        self.fact_checker = GeminiFactChecker(api_key=api_key)
        if self.fact_checker.is_available:
            print("✓ Gemini fact-checker ready")
        else:
            print("⚠ Gemini API not configured - fact-checking disabled")
        
        # Load lip-sync model (only if PyTorch available)
        self.lipsync_model = None
        if TORCH_AVAILABLE and lipsync_model_path and Path(lipsync_model_path).exists():
            self._load_lipsync_model(lipsync_model_path)
        else:
            if not TORCH_AVAILABLE:
                print("⚠ PyTorch not available - using handcrafted features only")
            else:
                print("⚠ No lip-sync model loaded - using handcrafted features only")
    
    def _load_lipsync_model(self, model_path: str):
        """Load the trained lip-sync detection model."""
        if not TORCH_AVAILABLE:
            print("⚠ PyTorch not available - cannot load model")
            return
        try:
            checkpoint = torch.load(model_path, map_location=self.device)
            
            # Build model architecture
            self.lipsync_model = self._build_model()
            
            # Load weights
            if 'model_state_dict' in checkpoint:
                self.lipsync_model.load_state_dict(checkpoint['model_state_dict'])
            else:
                self.lipsync_model.load_state_dict(checkpoint)
            
            self.lipsync_model.to(self.device)
            self.lipsync_model.eval()
            
            print(f"✓ Lip-sync model loaded: {model_path}")
        except Exception as e:
            print(f"⚠ Could not load lip-sync model: {e}")
            self.lipsync_model = None
    
    def _build_model(self):
        """Build the lip-sync model architecture."""
        if not TORCH_AVAILABLE or nn is None:
            return None
        # Recreate LipSyncAuthenticityNet from the notebook
        class LipSyncAuthenticityNet(nn.Module):
            def __init__(self, num_classes=2):
                super(LipSyncAuthenticityNet, self).__init__()
                
                self.features = nn.Sequential(
                    # Block 1
                    nn.Conv2d(3, 32, kernel_size=3, padding=1),
                    nn.BatchNorm2d(32),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(32, 32, kernel_size=3, padding=1),
                    nn.BatchNorm2d(32),
                    nn.ReLU(inplace=True),
                    nn.MaxPool2d(2, 2),
                    
                    # Block 2
                    nn.Conv2d(32, 64, kernel_size=3, padding=1),
                    nn.BatchNorm2d(64),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(64, 64, kernel_size=3, padding=1),
                    nn.BatchNorm2d(64),
                    nn.ReLU(inplace=True),
                    nn.MaxPool2d(2, 2),
                    
                    # Block 3
                    nn.Conv2d(64, 128, kernel_size=3, padding=1),
                    nn.BatchNorm2d(128),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(128, 128, kernel_size=3, padding=1),
                    nn.BatchNorm2d(128),
                    nn.ReLU(inplace=True),
                    nn.MaxPool2d(2, 2),
                    
                    # Block 4
                    nn.Conv2d(128, 256, kernel_size=3, padding=1),
                    nn.BatchNorm2d(256),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(256, 256, kernel_size=3, padding=1),
                    nn.BatchNorm2d(256),
                    nn.ReLU(inplace=True),
                    nn.MaxPool2d(2, 2),
                    
                    # Block 5
                    nn.Conv2d(256, 512, kernel_size=3, padding=1),
                    nn.BatchNorm2d(512),
                    nn.ReLU(inplace=True),
                    nn.MaxPool2d(2, 2),
                )
                
                self.attention = nn.Sequential(
                    nn.Conv2d(512, 128, kernel_size=1),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(128, 1, kernel_size=1),
                    nn.Sigmoid()
                )
                
                self.classifier = nn.Sequential(
                    nn.AdaptiveAvgPool2d((1, 1)),
                    nn.Flatten(),
                    nn.Dropout(0.5),
                    nn.Linear(512, 256),
                    nn.ReLU(inplace=True),
                    nn.Dropout(0.3),
                    nn.Linear(256, num_classes)
                )
            
            def forward(self, x):
                features = self.features(x)
                attention_weights = self.attention(features)
                features = features * attention_weights
                output = self.classifier(features)
                return output
        
        return LipSyncAuthenticityNet(num_classes=2)
    
    # =========================================================================
    # Main Detection Pipeline
    # =========================================================================
    
    def analyze_video(
        self,
        video_path: str,
        use_cache: bool = True,
        use_fact_check: bool = True
    ) -> DetectionResult:
        """
        Analyze a video for deepfake detection.
        
        Pipeline:
        1. Compute video hash
        2. Check cache (if enabled)
        3. Run parallel analysis (lip-sync + fact-check)
        4. Fuse results
        5. Cache result (if enabled)
        
        Args:
            video_path: Path to video file
            use_cache: Whether to use hash cache
            use_fact_check: Whether to run Gemini fact-checking
            
        Returns:
            DetectionResult with comprehensive analysis
        """
        start_time = time.time()
        video_path = str(video_path)
        
        print(f"\n{'='*60}")
        print(f"ANALYZING: {Path(video_path).name}")
        print(f"{'='*60}")
        
        # Stage 1: Hash computation and cache lookup
        if use_cache:
            print("Checking cache...")
            cached_result = self.cache.check_cache(video_path)
            
            if cached_result is not None:
                print("✓✓✓ CACHE HIT! Returning cached result")
                cached_result.processing_time = time.time() - start_time
                self._print_result_summary(cached_result)
                return cached_result
            
            print("→ Cache miss. Running full analysis...")
        
        # Stage 2: Parallel analysis
        print("\nRunning parallel analysis...")
        
        lipsync_result = None
        fact_check_result = None
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit lip-sync analysis
            lipsync_future = executor.submit(
                self._run_lipsync_analysis, video_path
            )
            
            # Submit fact-check analysis (if enabled)
            if use_fact_check and self.fact_checker.is_available:
                fact_check_future = executor.submit(
                    self._run_fact_check, video_path
                )
            else:
                fact_check_future = None
            
            # Collect results
            lipsync_result = lipsync_future.result()
            
            if fact_check_future is not None:
                fact_check_result = fact_check_future.result()
        
        # Stage 3: Result fusion
        print("\nCombining results...")
        final_result = self._fuse_results(
            video_path,
            lipsync_result,
            fact_check_result
        )
        
        # Set processing time
        final_result.processing_time = time.time() - start_time
        
        # Stage 4: Cache storage
        if use_cache:
            print("Storing in cache...")
            self.cache.store_result(video_path, final_result)
            print("✓ Result cached for future instant retrieval")
        
        # Print summary
        self._print_result_summary(final_result)
        
        return final_result
    
    def _run_lipsync_analysis(self, video_path: str) -> Dict[str, Any]:
        """
        Run lip-sync model analysis.
        
        Returns:
            Dictionary with is_deepfake, confidence, lipsync_score
        """
        print("  [Lip-Sync] Extracting frame pairs...")
        
        # Extract frame pairs
        frame_pairs = extract_consecutive_frame_pairs(
            video_path,
            num_pairs=self.NUM_FRAME_PAIRS
        )
        
        if len(frame_pairs) == 0:
            print("  [Lip-Sync] ⚠ No frames extracted")
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'lipsync_score': 0.5,
                'method': 'failed'
            }
        
        print(f"  [Lip-Sync] Extracted {len(frame_pairs)} frame pairs")
        
        # Use CNN model if available
        if self.lipsync_model is not None:
            print("  [Lip-Sync] Running CNN inference...")
            result = self._run_cnn_inference(frame_pairs)
        else:
            print("  [Lip-Sync] Using handcrafted features...")
            result = self._run_handcrafted_analysis(frame_pairs)
        
        print("  [Lip-Sync] ✓ Analysis complete")
        print(f"  [Lip-Sync]   - Verdict: {'FAKE' if result['is_deepfake'] else 'REAL'}")
        print(f"  [Lip-Sync]   - Confidence: {result['confidence']*100:.1f}%")
        
        return result
    
    def _run_cnn_inference(
        self, 
        frame_pairs: List[Tuple[np.ndarray, np.ndarray]]
    ) -> Dict[str, Any]:
        """Run CNN model inference on frame pairs."""
        if not TORCH_AVAILABLE or torch is None:
            # Fall back to handcrafted if torch not available
            return self._run_handcrafted_analysis(frame_pairs)
        
        import torchvision.transforms as transforms
        from PIL import Image
        
        # Custom NumPy-free PIL to tensor conversion
        def pil_to_tensor_no_numpy(pic):
            """Convert PIL Image to tensor without using NumPy."""
            channels = len(pic.getbands())
            width, height = pic.size
            byte_tensor = torch.ByteTensor(torch.ByteStorage.from_buffer(pic.tobytes()))
            byte_tensor = byte_tensor.view(height, width, channels)
            return byte_tensor.permute(2, 0, 1).float().div(255.0)
        
        class PILToTensorNoNumpy:
            def __call__(self, pic):
                if not isinstance(pic, Image.Image):
                    pic = Image.fromarray(pic)
                return pil_to_tensor_no_numpy(pic)
        
        # Prepare transform with NumPy-free conversion
        transform = transforms.Compose([
            PILToTensorNoNumpy(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])
        
        predictions = []
        
        self.lipsync_model.eval()
        with torch.no_grad():
            for frame1, frame2 in frame_pairs:
                # Combine frames side by side
                combined = np.hstack([
                    cv2.resize(frame1, (self.IMG_SIZE[1]//2, self.IMG_SIZE[0])),
                    cv2.resize(frame2, (self.IMG_SIZE[1]//2, self.IMG_SIZE[0]))
                ])
                
                # Convert to RGB
                combined_rgb = cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)
                
                # Transform and add batch dimension
                tensor = transform(combined_rgb).unsqueeze(0).to(self.device)
                
                # Forward pass
                outputs = self.lipsync_model(tensor)
                probs = torch.softmax(outputs, dim=1)
                
                predictions.append(probs.cpu().tolist()[0])
        
        # Aggregate predictions
        predictions_arr = np.array(predictions)
        avg_probs = np.mean(predictions_arr, axis=0)
        predicted_class = np.argmax(avg_probs)
        confidence = avg_probs[predicted_class]
        
        is_deepfake = (predicted_class == 1)  # Class 1 is FAKE_DESYNC
        lipsync_score = avg_probs[0]  # Probability of being real
        
        return {
            'is_deepfake': is_deepfake,
            'confidence': float(confidence),
            'lipsync_score': float(lipsync_score),
            'method': 'cnn'
        }
    
    def _run_handcrafted_analysis(
        self, 
        frame_pairs: List[Tuple[np.ndarray, np.ndarray]]
    ) -> Dict[str, Any]:
        """Run analysis using handcrafted features.
        
        NOTE: Without the CNN model, handcrafted features are LIMITED.
        The GRID dataset training used frame pairs from DIFFERENT videos for "fake",
        but real deepfakes have CONSISTENT frames within the same video.
        
        Therefore, we focus on:
        1. Frequency artifacts (AI-generated content has patterns)
        2. Edge density anomalies (face boundaries in deepfakes)
        3. Return UNCERTAIN confidence to defer to Gemini fact-checker
        """
        # Extract features
        features = extract_handcrafted_features(frame_pairs)
        
        # CRITICAL: For real-world deepfakes, frequency artifacts are the key indicator
        # High frequency artifacts = more likely manipulated
        # Temporal consistency is NOT reliable for deepfake detection
        # (deepfakes have smooth transitions too)
        
        freq_artifacts = features.get('frequency_artifacts', 0.5)
        edge_diff = features.get('edge_density_diff', 0)
        
        # Focus primarily on artifacts that indicate manipulation
        # Higher artifacts = more likely fake
        fake_probability = (
            freq_artifacts * 0.6 +  # Frequency artifacts are most reliable
            abs(edge_diff) * 0.2 +   # Edge density differences at face boundaries
            0.2  # Base uncertainty - always be cautious without CNN
        )
        
        # Normalize to 0-1 range
        fake_probability = min(1.0, max(0.0, fake_probability))
        
        # If artifacts are high, mark as likely fake
        # If low, mark as UNCERTAIN (let Gemini decide)
        if freq_artifacts > 0.4:  # Suspicious artifacts detected
            is_deepfake = True
            confidence = 0.5 + (freq_artifacts - 0.4) * 0.5  # 50-80% confidence
        else:
            # Cannot reliably determine - return uncertain
            is_deepfake = False  # Default to not-fake, but low confidence
            confidence = 0.4  # Low confidence - needs Gemini verification
        
        return {
            'is_deepfake': is_deepfake,
            'confidence': float(confidence),
            'lipsync_score': float(1.0 - fake_probability),  # Inverse for "authenticity"
            'method': 'handcrafted',
            'features': features,
            'uncertain': confidence < 0.6  # Flag uncertainty
        }
    
    def _run_fact_check(self, video_path: str) -> Optional[FactCheckResult]:
        """Run Gemini fact-checking analysis with personality-first detection.
        
        NEW FLOW (Personality-First):
        1. Gemini identifies if person is a famous personality
        2. If YES -> Use personality-specific deepfake detection (higher scrutiny)
        3. If NO -> Use technical artifact analysis (standard detection)
        """
        print("  [Fact-Check] Starting PERSONALITY-FIRST detection...")
        
        try:
            # Try personality-first detection first
            if hasattr(self.fact_checker, 'personality_first_detection'):
                pf_result = self.fact_checker.personality_first_detection(video_path)
                
                if pf_result and pf_result.get('is_deepfake') is not None:
                    print("  [Fact-Check] ✓ Personality-first analysis complete")
                    
                    personality_detected = pf_result.get('personality_detected', False)
                    personality_name = pf_result.get('personality_name')
                    personality_category = pf_result.get('personality_category', 'UNKNOWN')
                    
                    # Map to FactCheckResult
                    result = FactCheckResult(
                        artifact_score=pf_result.get('authenticity_score', 0.5),
                        artifact_confidence=pf_result.get('personality_confidence', 'MEDIUM'),
                        artifact_reasoning=pf_result.get('reasoning', ''),
                        celebrity_detected=personality_detected,
                        celebrity_name=personality_name,
                        celebrity_context=f"Category: {personality_category}",
                        risk_level='HIGH' if personality_category in ['POLITICIAN', 'BUSINESS'] else 'MEDIUM' if personality_detected else 'LOW',
                        authenticity_score=pf_result.get('authenticity_score', 0.5),
                        final_verdict='FAKE' if pf_result.get('is_deepfake') else 'AUTHENTIC' if pf_result.get('is_deepfake') is False else 'UNCERTAIN',
                        news_verdict='UNKNOWN'
                    )
                    
                    # Store additional info in metadata-style attributes
                    result._personality_method = pf_result.get('analysis_method', 'standard')
                    result._red_flags = pf_result.get('red_flags', [])
                    result._recommendation = pf_result.get('recommendation', 'VERIFY')
                    
                    print(f"  [Fact-Check]   - Personality Detected: {personality_detected}")
                    if personality_detected:
                        print(f"  [Fact-Check]   - ⚠️ Person: {personality_name} ({personality_category})")
                    print(f"  [Fact-Check]   - Is Deepfake: {pf_result.get('is_deepfake')}")
                    print(f"  [Fact-Check]   - Authenticity: {result.authenticity_score*100:.1f}%")
                    print(f"  [Fact-Check]   - Verdict: {result.final_verdict}")
                    
                    return result
            
            # Fallback to standard fact-check
            result = self.fact_checker.fact_check_video(video_path)
            
            print("  [Fact-Check] ✓ Standard analysis complete")
            print(f"  [Fact-Check]   - Authenticity: {result.authenticity_score*100:.1f}%")
            print(f"  [Fact-Check]   - Verdict: {result.final_verdict}")
            
            if result.celebrity_detected:
                print(f"  [Fact-Check]   - ⚠️ Celebrity: {result.celebrity_name}")
            
            return result
        except Exception as e:
            print(f"  [Fact-Check] ⚠ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _fuse_results(
        self,
        video_path: str,
        lipsync_result: Dict[str, Any],
        fact_check_result: Optional[FactCheckResult]
    ) -> DetectionResult:
        """
        Fuse lip-sync and fact-check results with PERSONALITY-AWARE weighting.
        
        FUSION STRATEGY:
        - Politician detected: 90% Gemini, 10% Local (highest risk)
        - Celebrity detected: 85% Gemini, 15% Local  
        - Unknown person: 70% Gemini, 30% Local (or 30/70 with CNN)
        
        AGREEMENT BOOST: +20% confidence when both agree
        DISAGREEMENT: Flag for manual review
        """
        # Determine weights based on whether we have the CNN model
        is_uncertain = lipsync_result.get('uncertain', False)
        using_handcrafted = lipsync_result.get('method') == 'handcrafted'
        
        # Base prediction from lip-sync (will be overridden by Gemini)
        is_deepfake = lipsync_result['is_deepfake']
        confidence = lipsync_result['confidence']
        lipsync_score = lipsync_result['lipsync_score']
        
        # Initialize result fields
        fact_check_score = None
        gemini_verdict = "Not performed"
        sources_found = []
        celebrity_detected = False
        celebrity_name = None
        agreement_status = None
        requires_review = is_uncertain
        
        # GEMINI IS PRIMARY - adjust based on fact-checking
        if fact_check_result is not None:
            fact_check_score = fact_check_result.authenticity_score
            gemini_verdict = fact_check_result.final_verdict
            sources_found = fact_check_result.sources_found
            celebrity_detected = fact_check_result.celebrity_detected
            celebrity_name = fact_check_result.celebrity_name
            
            print(f"  → Gemini authenticity score: {fact_check_score:.2f}")
            print(f"  → Gemini verdict: {gemini_verdict}")
            
            # CRITICAL: For celebrity content, Gemini is the AUTHORITY
            # Check personality category for risk-based weighting
            personality_category = getattr(fact_check_result, '_personality_method', None)
            red_flags = getattr(fact_check_result, '_red_flags', [])
            
            # Determine risk level from category stored in context
            is_politician = 'POLITICIAN' in fact_check_result.celebrity_context.upper() if fact_check_result.celebrity_context else False
            is_high_risk = fact_check_result.risk_level == 'HIGH'
            
            if celebrity_detected:
                print(f"  → ⚠️ CELEBRITY DETECTED: {celebrity_name}")
                print(f"  → Risk Level: {fact_check_result.risk_level}")
                
                # Check for NEWS VERIFICATION OVERRIDE first
                news_override = None
                if "CONFIRMED_FAKE" in fact_check_result.news_verdict:
                    news_override = "FAKE"
                    print(f"  → 🚨 NEWS CONFIRMED FAKE - Override active")
                elif "CONFIRMED_REAL" in fact_check_result.news_verdict:
                    news_override = "REAL"
                    print(f"  → ✅ NEWS CONFIRMED REAL - Override active")
                
                # POLITICIAN: Highest scrutiny (90% Gemini trust)
                if is_politician or is_high_risk:
                    print(f"  → Applying POLITICIAN/HIGH-RISK mode (90% Gemini weight)")
                    gemini_weight = 0.90
                    local_weight = 0.10
                else:
                    # Standard celebrity (90% Gemini trust - increased from 85%)
                    print(f"  → Applying CELEBRITY mode (90% Gemini weight)")
                    gemini_weight = 0.90
                    local_weight = 0.10
                
                # Compute weighted decision
                gemini_fake_prob = 1 - fact_check_score
                local_fake_prob = 1 - lipsync_score
                combined_fake_prob = (gemini_fake_prob * gemini_weight) + (local_fake_prob * local_weight)
                
                # Apply red flag penalties (capped at 25%)
                if red_flags and len(red_flags) > 0:
                    penalty = min(0.25, 0.08 * len(red_flags))  # 8% per flag, max 25%
                    combined_fake_prob = min(1.0, combined_fake_prob + penalty)
                    print(f"  → Red flags detected ({len(red_flags)}): {red_flags} (penalty: {penalty:.2%})")
                
                is_deepfake = combined_fake_prob > 0.5
                confidence = abs(combined_fake_prob - 0.5) * 2 + 0.5  # Scale to 0.5-1.0
                
                # Apply news override if present
                if news_override == "FAKE":
                    is_deepfake = True
                    confidence = max(confidence, 0.95)
                    requires_review = False  # News confirmed, no manual review needed
                    print(f"  → OVERRIDE APPLIED: Marking as FAKE (news confirmed)")
                elif news_override == "REAL":
                    is_deepfake = False
                    confidence = max(confidence, 0.95)
                    requires_review = False
                    print(f"  → OVERRIDE APPLIED: Marking as REAL (news confirmed)")
                # Conservative threshold for high-risk content (lowered to 0.60)
                elif is_high_risk and fact_check_score < 0.60:
                    is_deepfake = True
                    requires_review = True
                    confidence = max(confidence, 0.75)
                    print(f"  → HIGH RISK + LOW SCORE: Marking as FAKE for review")
                elif fact_check_score < 0.5:
                    is_deepfake = True
                    print(f"  → FAKE - Low Gemini authenticity score")
                elif fact_check_score > 0.8 and not red_flags:
                    is_deepfake = False
                    confidence = fact_check_score
                    print(f"  → Likely authentic - high Gemini score, no red flags")
            else:
                # Non-celebrity content - use weighted combination
                if using_handcrafted or is_uncertain:
                    # Without CNN: Gemini=80%, Local=20%
                    lipsync_weight = 0.2
                    fact_check_weight = 0.8
                    print("  → Using weights (no CNN): Gemini=80%, Local=20%")
                else:
                    # With CNN: use standard weights
                    lipsync_weight = self.LIPSYNC_WEIGHT
                    fact_check_weight = self.FACT_CHECK_WEIGHT
                
                # Weighted combination
                combined_fake_prob = (
                    (1 - lipsync_score) * lipsync_weight +
                    (1 - fact_check_score) * fact_check_weight
                )
                is_deepfake = combined_fake_prob > 0.5
                confidence = abs(combined_fake_prob - 0.5) * 2 + 0.5
            
            # Check agreement for logging
            lipsync_says_fake = lipsync_result['is_deepfake']
            fact_says_fake = fact_check_score < 0.5
            
            if lipsync_says_fake == fact_says_fake:
                agreement_status = "agree"
                print("  → Local and Gemini AGREE")
            else:
                agreement_status = "disagree"
                requires_review = True
                print("  → Local and Gemini DISAGREE - flagging for review")
            
            # Hard overrides from confirmed news
            if "CONFIRMED_FAKE" in fact_check_result.news_verdict:
                is_deepfake = True
                confidence = max(confidence, 0.9)
                print("  → NEWS CONFIRMED FAKE - forcing FAKE verdict")
            elif "CONFIRMED_REAL" in fact_check_result.news_verdict:
                is_deepfake = False
                confidence = max(confidence, 0.9)
                print("  → NEWS CONFIRMED REAL - forcing REAL verdict")
        
        # Compute video hash for result
        try:
            content_hash, perceptual_hash, _ = self.cache.compute_video_hash(video_path)
        except Exception:
            content_hash = "unknown"
            perceptual_hash = None
        
        return DetectionResult(
            video_hash=content_hash,
            is_deepfake=is_deepfake,
            confidence=float(confidence),
            lipsync_score=float(lipsync_score),
            fact_check_score=fact_check_score,
            gemini_verdict=gemini_verdict,
            sources_found=sources_found,
            detection_method='full_analysis',
            timestamp=datetime.now().isoformat(),
            perceptual_hash=perceptual_hash,
            celebrity_detected=celebrity_detected,
            celebrity_name=celebrity_name,
            agreement_status=agreement_status,
            requires_review=requires_review,
            metadata={
                'lipsync_method': lipsync_result.get('method', 'unknown'),
                'features': lipsync_result.get('features', {})
            }
        )
    
    def _print_result_summary(self, result: DetectionResult):
        """Print detection result summary."""
        print(f"\n{'='*60}")
        print("DETECTION RESULT")
        print(f"{'='*60}")
        print(result.summary())
        print(f"{'='*60}\n")
    
    # =========================================================================
    # Convenience Methods
    # =========================================================================
    
    def predict(
        self,
        video_path: str,
        use_cache: bool = True,
        use_fact_check: bool = True
    ) -> DetectionResult:
        """Alias for analyze_video."""
        return self.analyze_video(video_path, use_cache, use_fact_check)
    
    def batch_analyze(
        self,
        video_paths: List[str],
        use_cache: bool = True,
        use_fact_check: bool = True,
        show_progress: bool = True
    ) -> List[DetectionResult]:
        """
        Analyze multiple videos.
        
        Args:
            video_paths: List of video paths
            use_cache: Whether to use hash cache
            use_fact_check: Whether to run fact-checking
            show_progress: Whether to show progress
            
        Returns:
            List of DetectionResults
        """
        results = []
        total = len(video_paths)
        
        for i, video_path in enumerate(video_paths):
            if show_progress:
                print(f"\n[{i+1}/{total}] Processing: {Path(video_path).name}")
            
            result = self.analyze_video(
                video_path,
                use_cache=use_cache,
                use_fact_check=use_fact_check
            )
            results.append(result)
        
        return results
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.cache.get_stats()
    
    def print_cache_stats(self):
        """Print cache statistics."""
        self.cache.print_stats()
    
    def clear_cache(self):
        """Clear the video hash cache."""
        self.cache.clear()
    
    def print_result(self, result: DetectionResult):
        """Print detailed detection result."""
        print(result.detailed_report())
