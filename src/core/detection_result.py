"""
Detection Result Data Structure
===============================
Encapsulates all detection results from the enhanced deepfake detection pipeline.

This dataclass represents the final output of the detection system, containing:
- Core detection verdict and confidence
- Individual component scores (lip-sync, fact-check)
- Metadata about detection method and timing
- External verification results
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime
import json


@dataclass
class DetectionResult:
    """
    Comprehensive detection result from the enhanced deepfake detection pipeline.
    
    Attributes:
        video_hash: SHA256 hash of video content for exact matching
        is_deepfake: Final boolean verdict (True = deepfake detected)
        confidence: Overall confidence score (0.0 to 1.0)
        lipsync_score: Lip-sync model authenticity score (higher = more real)
        fact_check_score: Gemini fact-check authenticity score (optional)
        gemini_verdict: Human-readable verdict from Gemini analysis
        sources_found: List of news sources found during fact-checking
        detection_method: How detection was performed ('cached' or 'full_analysis')
        processing_time: Total processing time in seconds
        timestamp: ISO8601 timestamp of detection
        perceptual_hash: Perceptual hash for fuzzy matching
        celebrity_detected: Whether a celebrity was detected in the video
        celebrity_name: Name of detected celebrity (if any)
        agreement_status: Whether lip-sync and fact-check agreed
        requires_review: Whether manual review is recommended
        metadata: Additional metadata dictionary
    """
    
    # Core detection results
    video_hash: str
    is_deepfake: bool
    confidence: float
    
    # Component scores
    lipsync_score: float = 0.0
    fact_check_score: Optional[float] = None
    
    # Gemini fact-checking results
    gemini_verdict: str = "Not performed"
    sources_found: List[str] = field(default_factory=list)
    
    # Detection metadata
    detection_method: str = "full_analysis"  # 'cached' or 'full_analysis'
    processing_time: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Perceptual hashing
    perceptual_hash: Optional[str] = None
    
    # Celebrity detection
    celebrity_detected: bool = False
    celebrity_name: Optional[str] = None
    
    # Analysis flags
    agreement_status: Optional[str] = None  # 'agree', 'disagree', None
    requires_review: bool = False
    
    # Extended metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate and normalize result fields."""
        # Ensure confidence is in valid range
        self.confidence = max(0.0, min(1.0, self.confidence))
        
        # Normalize lipsync_score
        self.lipsync_score = max(0.0, min(1.0, self.lipsync_score))
        
        # Normalize fact_check_score if present
        if self.fact_check_score is not None:
            self.fact_check_score = max(0.0, min(1.0, self.fact_check_score))
    
    @property
    def verdict(self) -> str:
        """Get human-readable verdict string."""
        if self.is_deepfake:
            if self.confidence >= 0.9:
                return "HIGHLY LIKELY DEEPFAKE"
            elif self.confidence >= 0.7:
                return "LIKELY DEEPFAKE"
            elif self.confidence >= 0.5:
                return "POSSIBLY DEEPFAKE"
            else:
                return "SUSPECTED DEEPFAKE (LOW CONFIDENCE)"
        else:
            if self.confidence >= 0.9:
                return "HIGHLY LIKELY AUTHENTIC"
            elif self.confidence >= 0.7:
                return "LIKELY AUTHENTIC"
            elif self.confidence >= 0.5:
                return "POSSIBLY AUTHENTIC"
            else:
                return "UNCLEAR - MANUAL REVIEW RECOMMENDED"
    
    @property
    def confidence_level(self) -> str:
        """Get confidence level as categorical string."""
        if self.confidence >= 0.9:
            return "VERY HIGH"
        elif self.confidence >= 0.7:
            return "HIGH"
        elif self.confidence >= 0.5:
            return "MEDIUM"
        elif self.confidence >= 0.3:
            return "LOW"
        else:
            return "VERY LOW"
    
    @property
    def risk_level(self) -> str:
        """Get risk level based on celebrity detection and confidence."""
        if self.celebrity_detected and self.is_deepfake:
            return "CRITICAL"
        elif self.celebrity_detected:
            return "HIGH"
        elif self.is_deepfake and self.confidence >= 0.7:
            return "HIGH"
        elif self.is_deepfake:
            return "MEDIUM"
        else:
            return "LOW"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DetectionResult':
        """Create DetectionResult from dictionary."""
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'DetectionResult':
        """Create DetectionResult from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    @classmethod
    def from_cache(cls, cache_row: Dict[str, Any]) -> 'DetectionResult':
        """Create DetectionResult from database cache row."""
        # Parse metadata JSON if present
        metadata = {}
        if cache_row.get('metadata'):
            try:
                metadata = json.loads(cache_row['metadata'])
            except (json.JSONDecodeError, TypeError):
                pass
        
        return cls(
            video_hash=cache_row['video_hash'],
            is_deepfake=bool(cache_row['is_deepfake']),
            confidence=float(cache_row['confidence']),
            lipsync_score=float(cache_row.get('lipsync_score', 0.0)),
            fact_check_score=cache_row.get('fact_check_score'),
            perceptual_hash=cache_row.get('perceptual_hash'),
            detection_method='cached',
            timestamp=cache_row.get('last_seen', datetime.now().isoformat()),
            metadata=metadata
        )
    
    def summary(self) -> str:
        """Generate a concise summary string."""
        emoji = "🚨" if self.is_deepfake else "✅"
        status = "DEEPFAKE DETECTED" if self.is_deepfake else "AUTHENTIC"
        
        summary_lines = [
            f"{emoji} {status}",
            f"   Confidence: {self.confidence*100:.1f}% ({self.confidence_level})",
            f"   Lip-sync Score: {self.lipsync_score:.3f}",
        ]
        
        if self.fact_check_score is not None:
            summary_lines.append(f"   Fact-check Score: {self.fact_check_score:.3f}")
            summary_lines.append(f"   Agreement: {self.agreement_status or 'N/A'}")
        
        if self.celebrity_detected:
            summary_lines.append(f"   ⚠️ Celebrity: {self.celebrity_name or 'Unknown'}")
        
        summary_lines.append(f"   Method: {self.detection_method}")
        summary_lines.append(f"   Time: {self.processing_time:.3f}s")
        
        if self.requires_review:
            summary_lines.append("   📋 Manual review recommended")
        
        return "\n".join(summary_lines)
    
    def detailed_report(self) -> str:
        """Generate a detailed report string."""
        divider = "=" * 60
        
        report = [
            divider,
            "DEEPFAKE DETECTION REPORT",
            divider,
            "",
            f"📋 VIDEO HASH: {self.video_hash[:16]}...",
            f"📅 TIMESTAMP: {self.timestamp}",
            "",
            "─" * 60,
            "VERDICT",
            "─" * 60,
            "",
            f"   {self.verdict}",
            f"   Confidence: {self.confidence*100:.1f}%",
            f"   Risk Level: {self.risk_level}",
            "",
            "─" * 60,
            "COMPONENT ANALYSIS",
            "─" * 60,
            "",
            f"   LIP-SYNC ANALYSIS:",
            f"      Score: {self.lipsync_score:.4f}",
            f"      Verdict: {'SUSPICIOUS' if self.lipsync_score < 0.5 else 'AUTHENTIC'}",
            "",
        ]
        
        if self.fact_check_score is not None:
            report.extend([
                f"   FACT-CHECK ANALYSIS:",
                f"      Score: {self.fact_check_score:.4f}",
                f"      Gemini Verdict: {self.gemini_verdict}",
                f"      Sources Found: {len(self.sources_found)}",
                "",
                f"   CROSS-VALIDATION:",
                f"      Agreement: {self.agreement_status or 'N/A'}",
                "",
            ])
        
        if self.celebrity_detected:
            report.extend([
                "─" * 60,
                "⚠️ CELEBRITY ALERT",
                "─" * 60,
                "",
                f"   Celebrity Detected: {self.celebrity_name or 'Unknown'}",
                f"   High-risk deepfake target flagged",
                "",
            ])
        
        report.extend([
            "─" * 60,
            "METADATA",
            "─" * 60,
            "",
            f"   Detection Method: {self.detection_method}",
            f"   Processing Time: {self.processing_time:.3f} seconds",
            f"   Requires Review: {'Yes' if self.requires_review else 'No'}",
            "",
            divider,
        ])
        
        return "\n".join(report)
    
    def __str__(self) -> str:
        """String representation."""
        return self.summary()
    
    def __repr__(self) -> str:
        """Detailed representation."""
        return (
            f"DetectionResult("
            f"is_deepfake={self.is_deepfake}, "
            f"confidence={self.confidence:.3f}, "
            f"method='{self.detection_method}')"
        )
