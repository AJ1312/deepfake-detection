"""
Gemini Fact-Checker Module
==========================
External verification system using Google's Gemini multimodal AI.

Provides three-stage fact-checking:
1. Visual Artifact Analysis - Detect manipulation markers
2. Celebrity Detection - Identify high-risk targets
3. News Verification - Cross-reference with news sources

This adds external verification layer with 30% weight in final decision,
complementing the lip-sync analysis (70% weight).
"""

import os
import re
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
import base64
import time


@dataclass
class FactCheckResult:
    """Results from Gemini fact-checking analysis."""
    
    # Visual artifact analysis
    artifact_score: float = 0.5  # 0=definitely fake, 1=definitely real
    artifact_confidence: str = "MEDIUM"
    artifact_reasoning: str = ""
    
    # Celebrity detection
    celebrity_detected: bool = False
    celebrity_name: Optional[str] = None
    celebrity_context: str = ""
    risk_level: str = "LOW"
    
    # News verification
    news_verdict: str = "UNKNOWN"  # CONFIRMED_REAL, CONFIRMED_FAKE, UNKNOWN
    news_matches: int = 0
    sources_found: List[str] = None
    news_reasoning: str = ""
    
    # Combined
    authenticity_score: float = 0.5  # Final combined score
    final_verdict: str = "UNKNOWN"
    
    def __post_init__(self):
        if self.sources_found is None:
            self.sources_found = []


class GeminiFactChecker:
    """
    External fact-checking system using Google's Gemini API.
    
    Performs multi-stage analysis:
    1. Visual artifact detection
    2. Celebrity/public figure identification
    3. News source verification
    
    Attributes:
        api_key: Google Gemini API key
        model: Gemini model to use (default: gemini-1.5-flash)
        max_retries: Maximum retry attempts for API calls
        timeout: Request timeout in seconds
    """
    
    # Prompts for different analysis stages
    ARTIFACT_PROMPT = """You are a forensic expert specializing in detecting AI-generated and manipulated media (deepfakes).

TASK: Analyze this image frame for signs of AI generation or manipulation.

CRITICAL INDICATORS OF DEEPFAKES/AI-GENERATED CONTENT:
1. FACE BOUNDARIES: Blurring, flickering, color bleeding where face meets background
2. EYES: Unnatural reflections, asymmetry, "dead" or unfocused look, wrong direction
3. LIPS/TEETH: Blurry teeth, unnatural lip textures, movement artifacts
4. SKIN: Overly smooth or plastic-like texture, inconsistent pores/wrinkles
5. HAIR: Blob-like masses instead of strands, unnatural boundaries
6. LIGHTING: Shadows inconsistent with light sources, impossible reflections
7. EDGES: Soft/blurred edges around facial features
8. SYMMETRY: Face TOO symmetrical (real faces have asymmetry)

IMPORTANT CONTEXT:
- This appears to be a video frame that may have been altered
- Modern AI can create very convincing fakes
- When analyzing public figures, be EXTRA SUSPICIOUS
- Political content is frequently faked
- If you see ANY suspicious indicators, score LOW

Respond in EXACTLY this format:
SCORE: [0-10 where 0=DEFINITELY FAKE, 5=UNCERTAIN/SUSPICIOUS, 10=DEFINITELY REAL]
REASONING: [2-3 sentences about specific artifacts you found OR why you believe it's authentic]
CONFIDENCE: [LOW/MEDIUM/HIGH]
ARTIFACTS_FOUND: [List any artifacts: blurry_edges, unnatural_skin, eye_anomalies, lighting_issues, etc. or "None"]

DEFAULT TO SUSPICIOUS (score 4-6) unless you have strong evidence either way.
For celebrity/political content, apply a -2 penalty to your score."""

    CELEBRITY_PROMPT = """Analyze this image to identify any recognizable public figure.

TASK: Determine if this shows a celebrity, politician, business leader, or other public figure.

HIGH-RISK TARGETS FOR DEEPFAKES (set RISK_LEVEL=HIGH):
- Politicians (presidents, prime ministers, ministers, senators, MPs)
- World leaders and government officials
- Major celebrities with political influence
- CEOs of major tech/financial companies
- Controversial public figures

Respond in EXACTLY this format:
CELEBRITY_DETECTED: [YES/NO]
LIKELY_PERSON: [Full name if identifiable, or "Unknown"]
NEWS_CONTEXT: [Any relevant context about deepfakes targeting this person, or "None"]
RISK_LEVEL: [HIGH for politicians/world leaders, MEDIUM for celebrities, LOW for others]

IMPORTANT: Politicians like Modi, Trump, Biden, Zelensky, Putin etc. are ALWAYS HIGH risk.
Be conservative - only say YES if you're reasonably confident you recognize someone."""

    NEWS_VERIFICATION_PROMPT = """You are a fact-checking expert with knowledge of manipulated media databases and news archives.

TASK: Based on this image, search your knowledge for information about this content.

🔍 CHECK THESE SOURCES FROM YOUR TRAINING DATA:

FACT-CHECKING DATABASES:
- Snopes.com (general fact-checking)
- FactCheck.org (political claims)
- PolitiFact (US politics)
- Alt News (Indian fact-checking)
- Boom Live (India)
- The Quint WebQoof (India)
- AFP Fact Check
- Reuters Fact Check
- Associated Press Fact Check

DEEPFAKE DETECTION DATABASES:
- Deepfake Detection Challenge (DFDC)
- FaceForensics++ database
- Known deepfake repositories
- Academic deepfake datasets

NEWS SOURCES TO CONSIDER:
- Has this image/video been reported in mainstream news?
- Has it been debunked or verified by journalists?
- Is this from a known misinformation campaign?
- Are there similar fake videos targeting this person?

VIRAL MISINFORMATION:
- Have you seen this image in your training data as fake/manipulated?
- Is this similar to known viral deepfakes?
- Does this match patterns of political disinformation?

ANALYSIS STEPS:
1. If you recognize this specific image/video from fact-checking reports → mark CONFIRMED
2. If this looks like content that was debunked → mark CONFIRMED_FAKE
3. If this looks like verified authentic content → mark CONFIRMED_REAL
4. If unsure or no knowledge → mark UNKNOWN

Respond in EXACTLY this format:
NEWS_MATCHES: [Number of relevant matches you're aware of from your training data, or 0 if none]
SOURCES: [List specific sources (e.g., "Snopes debunked on March 2023", "Alt News verified", "Reuters fact-checked") or "None"]
VERDICT: [CONFIRMED_REAL if known authentic, CONFIRMED_FAKE if known manipulated, UNKNOWN if uncertain]
REASONING: [2-3 sentences explaining what you found in your knowledge base, or why you're uncertain]
CONFIDENCE: [LOW/MEDIUM/HIGH - how confident you are in this verdict]

IMPORTANT: Only mark as CONFIRMED if you have specific recollection from your training data. Be conservative - it's better to say UNKNOWN than to guess."""

    # NEW: Personality-first deepfake detection prompt
    PERSONALITY_DETECTION_PROMPT = """You are an expert at identifying famous personalities and public figures from around the world.

TASK: Look carefully at this image and determine if you can identify ANY recognizable person.

RECOGNITION CHECKLIST - CHECK ALL CATEGORIES:

🌍 WORLD POLITICIANS (Priority - most targeted for deepfakes):
- India: Narendra Modi, Rahul Gandhi, Arvind Kejriwal, Mamata Banerjee, Amit Shah, etc.
- USA: Joe Biden, Donald Trump, Kamala Harris, Barack Obama, Hillary Clinton, etc.
- Europe: Rishi Sunak, Emmanuel Macron, Olaf Scholz, Vladimir Putin, etc.
- Other regions: Xi Jinping, Volodymyr Zelensky, Justin Trudeau, etc.

🎬 BOLLYWOOD & INDIAN CELEBRITIES:
- Actors: Shah Rukh Khan, Amitabh Bachchan, Salman Khan, Aamir Khan, Akshay Kumar
- Actresses: Deepika Padukone, Priyanka Chopra, Katrina Kaif, Alia Bhatt
- Cricket: Virat Kohli, MS Dhoni, Sachin Tendulkar, Rohit Sharma

🎭 HOLLYWOOD & INTERNATIONAL:
- Actors: Tom Cruise, Leonardo DiCaprio, Brad Pitt, Will Smith, Robert Downey Jr.
- Actresses: Scarlett Johansson, Margot Robbie, Emma Watson, Jennifer Lawrence
- Musicians: Taylor Swift, Beyoncé, Ariana Grande, Drake, The Weeknd
- Tech: Elon Musk, Mark Zuckerberg, Bill Gates, Sundar Pichai, Satya Nadella

🏆 SPORTS FIGURES:
- Cricket: Virat Kohli, MS Dhoni, Sachin Tendulkar
- Football/Soccer: Cristiano Ronaldo, Lionel Messi, Neymar
- Basketball: LeBron James, Stephen Curry
- Other: Serena Williams, Roger Federer

📺 NEWS & MEDIA:
- News anchors: Rajat Sharma, Arnab Goswami, Ravish Kumar (India)
- International: Anderson Cooper, Rachel Maddow, Tucker Carlson
- Influencers: PewDiePie, Mr. Beast, Bhuvan Bam, CarryMinati

ANALYSIS TIPS:
- Look at FACIAL FEATURES: distinctive eyes, nose, smile, facial structure
- Check for CHARACTERISTIC EXPRESSIONS or mannerisms you recognize
- Consider the CONTEXT: clothing style, setting, likely age
- Even if you're NOT 100% certain, if the person looks FAMILIAR, identify them with LOW confidence
- Better to say YES with LOW confidence than miss a famous person

Respond in EXACTLY this format:
PERSON_IDENTIFIED: [YES/NO]
IDENTITY: [Full name and brief description (e.g., "Narendra Modi, Prime Minister of India") or "Unknown person"]
CONFIDENCE: [LOW/MEDIUM/HIGH - how certain you are of the identification]
CATEGORY: [POLITICIAN/CELEBRITY/BUSINESS/SPORTS/MEDIA/RELIGIOUS/OTHER/UNKNOWN]
REASONING: [1-2 sentences explaining what features helped you identify them or why you couldn't identify]

Be THOROUGH and SPECIFIC. Even partial recognition counts - say YES with LOW confidence rather than missing a celebrity."""

    PERSONALITY_DEEPFAKE_PROMPT = """You are an expert forensic analyst specializing in detecting AI-generated deepfakes of famous people.

CONTEXT: This image allegedly shows **{person_name}** ({person_category}).

TASK: Determine if this is a REAL image/video of this person, or a DEEPFAKE/AI-GENERATED fake.

🔬 FORENSIC ANALYSIS FRAMEWORK:

1. FACIAL IDENTITY VERIFICATION (Most Important):
   Does this LOOK like the actual {person_name} you know?
   - Compare facial structure to your knowledge of this person
   - Check distinctive features: eyes, nose, mouth, jawline, ears
   - Verify characteristic expressions and mannerisms
   - Look for any "uncanny valley" feeling - something subtly "off"
   - Age appropriateness: Does the person look the right age?

2. DEEPFAKE TECHNICAL ARTIFACTS:
   Visual glitches that indicate AI generation:
   ✓ Face boundary issues (blurring where face meets hair/background)
   ✓ Overly smooth or plastic-like skin texture
   ✓ Eyes that don't focus properly or have unnatural reflections
   ✓ Mouth/teeth anomalies (blurry, fused teeth, weird lip movements)
   ✓ Lighting inconsistencies (face lit differently than background)
   ✓ Temporal inconsistencies (if video: flickering, jittering)
   ✓ Audio-visual desynchronization (lip sync issues)

3. CONTEXTUAL RED FLAGS:
   Does this scenario make sense?
   - Is {person_name} likely to be in this setting/situation?
   - Does the clothing/styling match this person's known style?
   - Any anachronisms? (wrong time period, impossible locations)
   - Background authenticity: Does it look real or AI-generated?
   - Would this content be politically/financially advantageous to fake?

4. BEHAVIORAL CONSISTENCY:
   - Are the expressions natural for this person?
   - Does the body language match known patterns?
   - If speaking: Does it sound like their voice? (if you can assess)
   - Any out-of-character statements or actions?

5. RISK ASSESSMENT:
   ⚠️ HIGH RISK SCENARIOS (be extra suspicious):
   - Political content (especially controversial statements)
   - Content that could damage reputation
   - Financial scams (investment advice, endorsements)
   - Explicit or compromising content
   - Content from unknown/unverified sources

🎯 DECISION MATRIX:
- If you see MULTIPLE technical artifacts → Likely DEEPFAKE
- If the face looks "wrong" for this person → Likely DEEPFAKE
- If context is suspicious + some artifacts → DEEPFAKE
- If everything looks natural and correct → Likely REAL
- If uncertain → Default to UNCERTAIN and recommend verification

Respond in EXACTLY this format:
IS_DEEPFAKE: [YES/NO/UNCERTAIN]
CONFIDENCE: [0-100 percentage - be honest about uncertainty]
AUTHENTICITY_SCORE: [0-10 where 0=DEFINITELY FAKE, 5=UNCERTAIN, 10=DEFINITELY REAL]
REASONING: [3-5 sentences explaining your analysis across all categories above]
RED_FLAGS: [List specific concerns found, or "None detected"]
TECHNICAL_ARTIFACTS: [List technical deepfake indicators, or "None found"]
CONTEXTUAL_ISSUES: [List contextual red flags, or "None found"]
RECOMMENDATION: [TRUST if high confidence real, VERIFY if uncertain, REJECT if high confidence fake]

CRITICAL: For famous people, especially politicians, DEFAULT TO SUSPICIOUS. Better to false alarm than miss a dangerous deepfake."""

    UNKNOWN_PERSON_DEEPFAKE_PROMPT = """You are an expert forensic analyst detecting AI-generated images and deepfakes.

TASK: Analyze this image for signs of AI generation or manipulation. The person is NOT a recognized public figure, so focus purely on technical artifacts.

TECHNICAL INDICATORS TO CHECK:
1. FACIAL ARTIFACTS:
   - Asymmetric or misaligned features
   - Overly smooth, plastic-like skin
   - Unnatural eye reflections or "dead" eyes
   - Teeth that look blurry, fused, or wrong
   - Hair that looks like a blob rather than strands

2. BOUNDARY ISSUES:
   - Blurry edges where face meets hair/background
   - Color bleeding or halo effects
   - Inconsistent resolution across the image

3. LIGHTING ANOMALIES:
   - Shadows inconsistent with light source
   - Face lighting doesn't match background
   - Impossible reflections

4. GENERAL AI TELLS:
   - Too perfect symmetry (real faces are asymmetric)
   - Generic, "stock photo" feeling
   - Subtle warping or distortion

5. COMPRESSION & QUALITY:
   - Unusual compression artifacts
   - Inconsistent image quality in different areas

Respond in EXACTLY this format:
IS_DEEPFAKE: [YES/NO/UNCERTAIN]
CONFIDENCE: [0-100 percentage]
AUTHENTICITY_SCORE: [0-10 where 0=DEFINITELY FAKE, 5=UNCERTAIN, 10=DEFINITELY REAL]
REASONING: [2-4 sentences explaining technical findings]
ARTIFACTS_FOUND: [List specific artifacts, or "None detected"]
QUALITY_ASSESSMENT: [POOR/MEDIUM/HIGH - overall image quality]

Default to UNCERTAIN (score 4-6) if no clear indicators either way."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        Initialize the Gemini fact-checker.
        
        Args:
            api_key: Google Gemini API key. If None, will try GEMINI_API_KEY env var
            model: Gemini model to use
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        
        # Check if we have a valid API key
        self._client = None
        self._genai = None
        
        if self.api_key:
            self._init_client()
    
    def _init_client(self):
        """Initialize the Gemini client."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._genai = genai
            self._client = genai.GenerativeModel(self.model)
            print(f"✓ Gemini API initialized with model: {self.model}")
        except ImportError:
            print("Warning: google-generativeai package not installed.")
            print("Install with: pip install google-generativeai")
            self._client = None
        except Exception as e:
            print(f"Warning: Could not initialize Gemini API: {e}")
            self._client = None
    
    @property
    def is_available(self) -> bool:
        """Check if Gemini API is available and configured."""
        return self._client is not None
    
    def _extract_frames(
        self, 
        video_path: str, 
        num_frames: int = 3
    ) -> List[np.ndarray]:
        """Extract key frames from video for analysis."""
        cap = cv2.VideoCapture(str(video_path))
        frames = []
        
        if not cap.isOpened():
            return frames
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames < num_frames:
            indices = list(range(total_frames))
        else:
            indices = np.linspace(0, total_frames - 1, num_frames, dtype=int)
        
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        
        cap.release()
        return frames
    
    def _frame_to_pil(self, frame: np.ndarray):
        """Convert OpenCV frame to PIL Image."""
        from PIL import Image
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_frame)
    
    def _call_gemini(
        self, 
        prompt: str, 
        image: np.ndarray,
        timeout: int = 15
    ) -> Optional[str]:
        """
        Make API call to Gemini with retry logic and optimized timeout.
        
        Args:
            prompt: Text prompt
            image: Image as numpy array
            timeout: Request timeout in seconds (default: 15s)
            
        Returns:
            Response text or None if failed
        """
        if not self.is_available:
            return None
        
        pil_image = self._frame_to_pil(image)
        
        for attempt in range(self.max_retries):
            try:
                response = self._client.generate_content(
                    [prompt, pil_image],
                    generation_config={
                        "max_output_tokens": 500,
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "top_k": 40
                    },
                    request_options={"timeout": timeout}
                )
                return response.text
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"Gemini API error, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    print(f"Gemini API failed after {self.max_retries} attempts: {e}")
                    return None
        
        return None
    
    def _parse_artifact_response(self, response: str) -> Dict[str, Any]:
        """Parse artifact analysis response."""
        result = {
            'score': 5.0,
            'reasoning': '',
            'confidence': 'MEDIUM'
        }
        
        if not response:
            return result
        
        # Parse SCORE
        score_match = re.search(r'SCORE:\s*(\d+(?:\.\d+)?)', response, re.IGNORECASE)
        if score_match:
            result['score'] = float(score_match.group(1))
        
        # Parse REASONING
        reasoning_match = re.search(
            r'REASONING:\s*(.+?)(?=CONFIDENCE:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            result['reasoning'] = reasoning_match.group(1).strip()
        
        # Parse CONFIDENCE
        confidence_match = re.search(
            r'CONFIDENCE:\s*(LOW|MEDIUM|HIGH)', 
            response, 
            re.IGNORECASE
        )
        if confidence_match:
            result['confidence'] = confidence_match.group(1).upper()
        
        return result
    
    def _parse_celebrity_response(self, response: str) -> Dict[str, Any]:
        """Parse celebrity detection response."""
        result = {
            'detected': False,
            'person': None,
            'context': '',
            'risk_level': 'LOW'
        }
        
        if not response:
            return result
        
        # Parse CELEBRITY_DETECTED
        detected_match = re.search(
            r'CELEBRITY_DETECTED:\s*(YES|NO)', 
            response, 
            re.IGNORECASE
        )
        if detected_match:
            result['detected'] = detected_match.group(1).upper() == 'YES'
        
        # Parse LIKELY_PERSON
        person_match = re.search(
            r'LIKELY_PERSON:\s*(.+?)(?=NEWS_CONTEXT:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if person_match:
            person = person_match.group(1).strip()
            if person.lower() != 'unknown':
                result['person'] = person
        
        # Parse NEWS_CONTEXT
        context_match = re.search(
            r'NEWS_CONTEXT:\s*(.+?)(?=RISK_LEVEL:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if context_match:
            result['context'] = context_match.group(1).strip()
        
        # Parse RISK_LEVEL
        risk_match = re.search(
            r'RISK_LEVEL:\s*(LOW|MEDIUM|HIGH)', 
            response, 
            re.IGNORECASE
        )
        if risk_match:
            result['risk_level'] = risk_match.group(1).upper()
        
        return result
    
    def _parse_news_response(self, response: str) -> Dict[str, Any]:
        """Parse news verification response."""
        result = {
            'matches': 0,
            'sources': [],
            'verdict': 'UNKNOWN',
            'reasoning': '',
            'confidence': 'LOW'
        }
        
        if not response:
            return result
        
        # Parse NEWS_MATCHES
        matches_match = re.search(
            r'NEWS_MATCHES:\s*(\d+)', 
            response, 
            re.IGNORECASE
        )
        if matches_match:
            result['matches'] = int(matches_match.group(1))
        
        # Parse SOURCES
        sources_match = re.search(
            r'SOURCES:\s*(.+?)(?=VERDICT:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if sources_match:
            sources_text = sources_match.group(1).strip()
            if sources_text.lower() not in ['none', '']:
                result['sources'] = [s.strip() for s in sources_text.split(',') if s.strip()]
        
        # Parse VERDICT
        verdict_match = re.search(
            r'VERDICT:\s*(CONFIRMED_REAL|CONFIRMED_FAKE|UNKNOWN)', 
            response, 
            re.IGNORECASE
        )
        if verdict_match:
            result['verdict'] = verdict_match.group(1).upper()
        
        # Parse REASONING
        reasoning_match = re.search(
            r'REASONING:\s*(.+?)(?=CONFIDENCE:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            result['reasoning'] = reasoning_match.group(1).strip()
        
        # Parse CONFIDENCE
        confidence_match = re.search(
            r'CONFIDENCE:\s*(LOW|MEDIUM|HIGH)', 
            response, 
            re.IGNORECASE
        )
        if confidence_match:
            result['confidence'] = confidence_match.group(1).upper()
        
        return result
        if matches_match:
            result['matches'] = int(matches_match.group(1))
        
        # Parse SOURCES
        sources_match = re.search(
            r'SOURCES:\s*(.+?)(?=VERDICT:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if sources_match:
            sources_text = sources_match.group(1).strip()
            if sources_text.lower() != 'none':
                result['sources'] = [
                    s.strip() for s in sources_text.split(',') 
                    if s.strip()
                ]
        
        # Parse VERDICT
        verdict_match = re.search(
            r'VERDICT:\s*(CONFIRMED_REAL|CONFIRMED_FAKE|UNKNOWN)', 
            response, 
            re.IGNORECASE
        )
        if verdict_match:
            result['verdict'] = verdict_match.group(1).upper()
        
        # Parse REASONING
        reasoning_match = re.search(
            r'REASONING:\s*(.+?)$', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            result['reasoning'] = reasoning_match.group(1).strip()
        
        return result
    
    def fact_check_video(self, video_path: str) -> FactCheckResult:
        """
        Perform comprehensive fact-checking on a video.
        
        Executes three-stage analysis:
        1. Visual artifact detection
        2. Celebrity identification
        3. News verification
        
        Args:
            video_path: Path to video file
            
        Returns:
            FactCheckResult with all analysis results
        """
        result = FactCheckResult()
        
        if not self.is_available:
            print("Gemini API not available, skipping fact-check")
            return result
        
        # Extract frames
        frames = self._extract_frames(video_path, num_frames=3)
        
        if len(frames) == 0:
            print(f"Warning: Could not extract frames from {video_path}")
            return result
        
        # Use middle frame for analysis
        middle_frame = frames[len(frames) // 2]
        
        # Stage 1: Visual Artifact Analysis
        print("  [Fact-Check] Analyzing visual artifacts...")
        artifact_response = self._call_gemini(self.ARTIFACT_PROMPT, middle_frame)
        artifact_parsed = self._parse_artifact_response(artifact_response)
        
        result.artifact_score = artifact_parsed['score'] / 10.0
        result.artifact_confidence = artifact_parsed['confidence']
        result.artifact_reasoning = artifact_parsed['reasoning']
        
        # Stage 2: Celebrity Detection
        print("  [Fact-Check] Checking for public figures...")
        celebrity_response = self._call_gemini(self.CELEBRITY_PROMPT, middle_frame)
        celebrity_parsed = self._parse_celebrity_response(celebrity_response)
        
        result.celebrity_detected = celebrity_parsed['detected']
        result.celebrity_name = celebrity_parsed['person']
        result.celebrity_context = celebrity_parsed['context']
        result.risk_level = celebrity_parsed['risk_level']
        
        # Stage 3: News Verification
        print("  [Fact-Check] Searching news sources...")
        news_response = self._call_gemini(self.NEWS_VERIFICATION_PROMPT, middle_frame)
        news_parsed = self._parse_news_response(news_response)
        
        result.news_verdict = news_parsed['verdict']
        result.news_matches = news_parsed['matches']
        result.sources_found = news_parsed['sources']
        result.news_reasoning = news_parsed['reasoning']
        
        # Combine results
        result.authenticity_score = self._compute_authenticity_score(result)
        result.final_verdict = self._compute_verdict(result)
        
        return result
    
    def _compute_authenticity_score(self, result: FactCheckResult) -> float:
        """Compute final authenticity score from all analyses.
        
        IMPORTANT: For celebrity/political content, be MORE conservative.
        Deepfakes targeting public figures are common and dangerous.
        """
        score = result.artifact_score
        
        # Adjust based on news verdict (hard overrides)
        if result.news_verdict == "CONFIRMED_FAKE":
            score = min(score, 0.3)
        elif result.news_verdict == "CONFIRMED_REAL":
            score = max(score, 0.7)
        
        # Celebrity detection - BE MORE SUSPICIOUS
        # High-profile figures are common deepfake targets
        if result.celebrity_detected:
            if result.risk_level == "HIGH":
                # Politicians, major celebrities - VERY suspicious
                score *= 0.6  # Significant penalty
            elif result.risk_level == "MEDIUM":
                score *= 0.75  # Moderate penalty
            else:
                score *= 0.85  # Slight penalty
        
        return max(0.0, min(1.0, score))
    
    def _compute_verdict(self, result: FactCheckResult) -> str:
        """Compute final verdict string."""
        if result.news_verdict == "CONFIRMED_FAKE":
            return "CONFIRMED_FAKE - Known manipulated media"
        elif result.news_verdict == "CONFIRMED_REAL":
            return "CONFIRMED_REAL - Verified authentic"
        elif result.authenticity_score >= 0.7:
            return "LIKELY_AUTHENTIC - No manipulation detected"
        elif result.authenticity_score >= 0.4:
            return "UNCERTAIN - Manual review recommended"
        else:
            return "LIKELY_FAKE - Manipulation indicators detected"
    
    def fact_check_frame(self, frame: np.ndarray) -> FactCheckResult:
        """
        Perform fact-checking on a single frame.
        
        Args:
            frame: Frame as numpy array (BGR format)
            
        Returns:
            FactCheckResult with analysis results
        """
        result = FactCheckResult()
        
        if not self.is_available:
            return result
        
        # Stage 1: Visual Artifact Analysis
        artifact_response = self._call_gemini(self.ARTIFACT_PROMPT, frame)
        artifact_parsed = self._parse_artifact_response(artifact_response)
        
        result.artifact_score = artifact_parsed['score'] / 10.0
        result.artifact_confidence = artifact_parsed['confidence']
        result.artifact_reasoning = artifact_parsed['reasoning']
        
        # Stage 2: Celebrity Detection
        celebrity_response = self._call_gemini(self.CELEBRITY_PROMPT, frame)
        celebrity_parsed = self._parse_celebrity_response(celebrity_response)
        
        result.celebrity_detected = celebrity_parsed['detected']
        result.celebrity_name = celebrity_parsed['person']
        result.risk_level = celebrity_parsed['risk_level']
        
        # Combine results
        result.authenticity_score = self._compute_authenticity_score(result)
        result.final_verdict = self._compute_verdict(result)
        
        return result
    
    def analyze_artifact_only(
        self, 
        video_path: str
    ) -> Tuple[float, str, str]:
        """
        Quick artifact-only analysis (faster, cheaper).
        
        Args:
            video_path: Path to video
            
        Returns:
            Tuple of (score, reasoning, confidence)
        """
        if not self.is_available:
            return 0.5, "Gemini not available", "LOW"
        
        frames = self._extract_frames(video_path, num_frames=1)
        
        if len(frames) == 0:
            return 0.5, "Could not extract frames", "LOW"
        
        response = self._call_gemini(self.ARTIFACT_PROMPT, frames[0])
        parsed = self._parse_artifact_response(response)
        
        return (
            parsed['score'] / 10.0,
            parsed['reasoning'],
            parsed['confidence']
        )
    
    def print_result(self, result: FactCheckResult):
        """Print fact-check results to console."""
        print("\n" + "=" * 50)
        print("GEMINI FACT-CHECK RESULTS")
        print("=" * 50)
        print(f"\n📊 ARTIFACT ANALYSIS:")
        print(f"   Score: {result.artifact_score:.2f} (0=fake, 1=real)")
        print(f"   Confidence: {result.artifact_confidence}")
        print(f"   Reasoning: {result.artifact_reasoning[:100]}...")
        
        print(f"\n👤 CELEBRITY DETECTION:")
        if result.celebrity_detected:
            print(f"   ⚠️ Celebrity Detected: {result.celebrity_name or 'Unknown'}")
            print(f"   Risk Level: {result.risk_level}")
        else:
            print(f"   No celebrity detected")
        
        print(f"\n📰 NEWS VERIFICATION:")
        print(f"   Verdict: {result.news_verdict}")
        print(f"   Matches: {result.news_matches}")
        if result.sources_found:
            print(f"   Sources: {', '.join(result.sources_found[:3])}")
        
        print(f"\n🎯 FINAL ASSESSMENT:")
        print(f"   Authenticity: {result.authenticity_score*100:.1f}%")
        print(f"   Verdict: {result.final_verdict}")
        print("=" * 50)

    # =========================================================================
    # NEW: Personality-First Detection Pipeline
    # =========================================================================
    
    def personality_first_detection(
        self, 
        video_path: str,
        frames: Optional[List[np.ndarray]] = None
    ) -> Dict[str, Any]:
        """
        NEW ENHANCED PIPELINE: Personality-first deepfake detection.
        
        Flow:
        1. First, identify if there's a famous personality in the video
        2. If YES: Ask Gemini specifically about deepfakes of that person
        3. If NO: Run standard technical artifact detection
        4. Return combined assessment for pipeline fusion
        
        This approach is more effective because:
        - Famous people have known appearances Gemini can verify against
        - Unknown people require purely technical analysis
        - Different prompts optimized for each scenario
        
        Args:
            video_path: Path to video file
            frames: Optional pre-extracted frames (for efficiency)
            
        Returns:
            Dict with detection results and analysis metadata
        """
        result = {
            'personality_detected': False,
            'personality_name': None,
            'personality_category': None,
            'personality_confidence': 'LOW',
            'is_deepfake': None,  # None = uncertain
            'deepfake_confidence': 0.5,
            'authenticity_score': 0.5,
            'analysis_method': 'unknown',
            'reasoning': '',
            'red_flags': [],
            'recommendation': 'VERIFY',
            'gemini_available': self.is_available
        }
        
        if not self.is_available:
            result['reasoning'] = "Gemini API not available"
            result['analysis_method'] = 'skipped'
            return result
        
        # Extract frames if not provided
        if frames is None:
            frames = self._extract_frames(video_path, num_frames=3)
        
        if len(frames) == 0:
            result['reasoning'] = "Could not extract frames from video"
            result['analysis_method'] = 'failed'
            return result
        
        # Use middle frame for analysis
        analysis_frame = frames[len(frames) // 2]
        
        # STEP 1: Identify personality
        print("  [Gemini] Step 1: Identifying personality...")
        personality_response = self._call_gemini(
            self.PERSONALITY_DETECTION_PROMPT, 
            analysis_frame
        )
        personality_info = self._parse_personality_response(personality_response)
        
        result['personality_detected'] = personality_info['detected']
        result['personality_name'] = personality_info['identity']
        result['personality_category'] = personality_info['category']
        result['personality_confidence'] = personality_info['confidence']
        
        # STEP 2: Choose analysis path based on personality detection
        if personality_info['detected'] and personality_info['identity']:
            # KNOWN PERSONALITY: Use personality-specific deepfake detection
            print(f"  [Gemini] ✓ Personality identified: {personality_info['identity']}")
            print(f"  [Gemini] Step 2: Running personality-specific deepfake analysis...")
            
            result['analysis_method'] = 'personality_specific'
            
            # Format the prompt with the identified person
            personalized_prompt = self.PERSONALITY_DEEPFAKE_PROMPT.format(
                person_name=personality_info['identity'],
                person_category=personality_info['category']
            )
            
            deepfake_response = self._call_gemini(personalized_prompt, analysis_frame)
            deepfake_info = self._parse_deepfake_response(deepfake_response)
            
            result['is_deepfake'] = deepfake_info['is_deepfake']
            result['deepfake_confidence'] = deepfake_info['confidence'] / 100.0
            result['authenticity_score'] = deepfake_info['authenticity_score'] / 10.0
            result['reasoning'] = deepfake_info['reasoning']
            result['red_flags'] = deepfake_info['red_flags']
            result['recommendation'] = deepfake_info['recommendation']
            
            print(f"  [Gemini] ✓ Personality deepfake analysis complete")
            print(f"  [Gemini]   - Is Deepfake: {result['is_deepfake']}")
            print(f"  [Gemini]   - Confidence: {result['deepfake_confidence']*100:.1f}%")
            
        else:
            # UNKNOWN PERSON: Use technical artifact analysis
            print("  [Gemini] → No known personality detected")
            print("  [Gemini] Step 2: Running technical artifact analysis...")
            
            result['analysis_method'] = 'technical_artifacts'
            
            deepfake_response = self._call_gemini(
                self.UNKNOWN_PERSON_DEEPFAKE_PROMPT, 
                analysis_frame
            )
            deepfake_info = self._parse_deepfake_response(deepfake_response)
            
            result['is_deepfake'] = deepfake_info['is_deepfake']
            result['deepfake_confidence'] = deepfake_info['confidence'] / 100.0
            result['authenticity_score'] = deepfake_info['authenticity_score'] / 10.0
            result['reasoning'] = deepfake_info['reasoning']
            result['red_flags'] = deepfake_info.get('artifacts', [])
            result['recommendation'] = 'VERIFY'  # Always verify unknown people
            
            print(f"  [Gemini] ✓ Technical analysis complete")
            print(f"  [Gemini]   - Is Deepfake: {result['is_deepfake']}")
            print(f"  [Gemini]   - Authenticity: {result['authenticity_score']*100:.1f}%")
        
        return result
    
    def _parse_personality_response(self, response: str) -> Dict[str, Any]:
        """Parse personality detection response."""
        result = {
            'detected': False,
            'identity': None,
            'confidence': 'LOW',
            'category': 'UNKNOWN',
            'reasoning': ''
        }
        
        if not response:
            return result
        
        # Parse PERSON_IDENTIFIED
        identified_match = re.search(
            r'PERSON_IDENTIFIED:\s*(YES|NO)', 
            response, 
            re.IGNORECASE
        )
        if identified_match:
            result['detected'] = identified_match.group(1).upper() == 'YES'
        
        # Parse IDENTITY
        identity_match = re.search(
            r'IDENTITY:\s*(.+?)(?=CONFIDENCE:|CATEGORY:|REASONING:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if identity_match:
            identity = identity_match.group(1).strip()
            if identity.lower() not in ['unknown', 'unknown person', 'none']:
                result['identity'] = identity
        
        # Parse CONFIDENCE
        confidence_match = re.search(
            r'CONFIDENCE:\s*(LOW|MEDIUM|HIGH)', 
            response, 
            re.IGNORECASE
        )
        if confidence_match:
            result['confidence'] = confidence_match.group(1).upper()
        
        # Parse CATEGORY
        category_match = re.search(
            r'CATEGORY:\s*(POLITICIAN|CELEBRITY|BUSINESS|SPORTS|MEDIA|RELIGIOUS|OTHER|UNKNOWN)', 
            response, 
            re.IGNORECASE
        )
        if category_match:
            result['category'] = category_match.group(1).upper()
        
        # Parse REASONING
        reasoning_match = re.search(
            r'REASONING:\s*(.+?)(?=$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            result['reasoning'] = reasoning_match.group(1).strip()
        
        return result
    
    def _parse_deepfake_response(self, response: str) -> Dict[str, Any]:
        """Parse deepfake detection response."""
        result = {
            'is_deepfake': None,  # None means uncertain
            'confidence': 50,
            'authenticity_score': 5.0,
            'reasoning': '',
            'red_flags': [],
            'artifacts': [],
            'technical_artifacts': [],
            'contextual_issues': [],
            'recommendation': 'VERIFY'
        }
        
        if not response:
            return result
        
        # Parse IS_DEEPFAKE
        deepfake_match = re.search(
            r'IS_DEEPFAKE:\s*(YES|NO|UNCERTAIN)', 
            response, 
            re.IGNORECASE
        )
        if deepfake_match:
            value = deepfake_match.group(1).upper()
            if value == 'YES':
                result['is_deepfake'] = True
            elif value == 'NO':
                result['is_deepfake'] = False
            else:
                result['is_deepfake'] = None
        
        # Parse CONFIDENCE
        confidence_match = re.search(
            r'CONFIDENCE:\s*(\d+)', 
            response, 
            re.IGNORECASE
        )
        if confidence_match:
            result['confidence'] = min(100, max(0, int(confidence_match.group(1))))
        
        # Parse AUTHENTICITY_SCORE
        score_match = re.search(
            r'AUTHENTICITY_SCORE:\s*(\d+(?:\.\d+)?)', 
            response, 
            re.IGNORECASE
        )
        if score_match:
            result['authenticity_score'] = min(10.0, max(0.0, float(score_match.group(1))))
        
        # Parse REASONING
        reasoning_match = re.search(
            r'REASONING:\s*(.+?)(?=RED_FLAGS:|TECHNICAL_ARTIFACTS:|ARTIFACTS_FOUND:|CONTEXTUAL_ISSUES:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            result['reasoning'] = reasoning_match.group(1).strip()
        
        # Parse RED_FLAGS
        flags_match = re.search(
            r'RED_FLAGS:\s*(.+?)(?=TECHNICAL_ARTIFACTS:|CONTEXTUAL_ISSUES:|RECOMMENDATION:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if flags_match:
            flags_text = flags_match.group(1).strip()
            if flags_text.lower() not in ['none', 'none detected', '']:
                result['red_flags'] = [f.strip() for f in flags_text.split(',') if f.strip()]
        
        # Parse TECHNICAL_ARTIFACTS
        tech_match = re.search(
            r'TECHNICAL_ARTIFACTS:\s*(.+?)(?=CONTEXTUAL_ISSUES:|RECOMMENDATION:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if tech_match:
            tech_text = tech_match.group(1).strip()
            if tech_text.lower() not in ['none', 'none found', '']:
                result['technical_artifacts'] = [t.strip() for t in tech_text.split(',') if t.strip()]
        
        # Parse CONTEXTUAL_ISSUES
        context_match = re.search(
            r'CONTEXTUAL_ISSUES:\s*(.+?)(?=RECOMMENDATION:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if context_match:
            context_text = context_match.group(1).strip()
            if context_text.lower() not in ['none', 'none found', '']:
                result['contextual_issues'] = [c.strip() for c in context_text.split(',') if c.strip()]
        
        # Parse ARTIFACTS_FOUND (for backward compatibility with UNKNOWN_PERSON prompt)
        artifacts_match = re.search(
            r'ARTIFACTS_FOUND:\s*(.+?)(?=QUALITY_ASSESSMENT:|RECOMMENDATION:|$)', 
            response, 
            re.IGNORECASE | re.DOTALL
        )
        if artifacts_match:
            artifacts_text = artifacts_match.group(1).strip()
            if artifacts_text.lower() not in ['none', 'none detected', '']:
                result['artifacts'] = [a.strip() for a in artifacts_text.split(',') if a.strip()]
        
        # Parse RECOMMENDATION
        rec_match = re.search(
            r'RECOMMENDATION:\s*(TRUST|VERIFY|REJECT)', 
            response, 
            re.IGNORECASE
        )
        if rec_match:
            result['recommendation'] = rec_match.group(1).upper()
        
        return result
