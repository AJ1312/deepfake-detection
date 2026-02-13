"""
Deepfake Origin Finder
======================
Tracks the genealogy and mutation history of deepfake videos.

Core Concept:
- Every deepfake modification leaves a trace (like fingerprints at a crime scene)
- By analyzing these traces, we can reconstruct the "family tree" of a deepfake
- This helps identify the original creator and track how it spread

Key Features:
1. Lineage Tracking - Parent-child relationships between video variants
2. Mutation Detection - What changed between versions (crop, compress, watermark, etc.)
3. Spread Analysis - Timestamps and sources showing propagation
4. Origin Identification - Find the earliest known version
"""

import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Set
from dataclasses import dataclass, field, asdict
import threading
from contextlib import contextmanager
import cv2
import numpy as np


@dataclass
class DeepfakeLineageNode:
    """
    Represents a single node in the deepfake family tree.
    
    Attributes:
        video_hash: Unique content hash (SHA256)
        perceptual_hash: Fuzzy matching hash (DCT-based)
        parent_hash: Hash of the parent video (if known)
        first_seen: Timestamp when first detected
        source_platform: Where this version was found (YouTube, Twitter, etc.)
        source_url: Direct URL to the video (if available)
        mutations: List of detected modifications from parent
        generation: How many "hops" from the original (0 = original)
        children: List of child video hashes
        is_deepfake: Detection result
        confidence: Detection confidence
        metadata: Additional tracking data
        origin_country: Country where video was uploaded
        origin_city: City where video was uploaded
        origin_latitude: Latitude of upload location
        origin_longitude: Longitude of upload location
        ip_hash: Hashed IP for privacy-preserving tracking
    """
    video_hash: str
    perceptual_hash: str
    parent_hash: Optional[str] = None
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    source_platform: Optional[str] = None
    source_url: Optional[str] = None
    mutations: List[str] = field(default_factory=list)
    generation: int = 0
    children: List[str] = field(default_factory=list)
    is_deepfake: bool = False
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Location tracking fields
    origin_country: Optional[str] = None
    origin_city: Optional[str] = None
    origin_latitude: Optional[float] = None
    origin_longitude: Optional[float] = None
    ip_hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeepfakeLineageNode':
        """Create from dictionary."""
        return cls(**data)


class DeepfakeOriginFinder:
    """
    Tracks deepfake video origins and mutations.
    
    This system maintains a database of video "fingerprints" and their relationships,
    allowing us to:
    1. Find if a video is a derivative of a known deepfake
    2. Track how deepfakes spread and mutate
    3. Identify the original source of a deepfake
    
    Database Schema:
    - lineage: Core genealogy data (hashes, relationships, mutations)
    - spread_events: Timeline of when/where videos appeared
    - mutation_signatures: Fingerprints of specific modification types
    """
    
    SCHEMA = """
    -- Core lineage tracking
    CREATE TABLE IF NOT EXISTS lineage (
        video_hash TEXT PRIMARY KEY,
        perceptual_hash TEXT NOT NULL,
        parent_hash TEXT,
        first_seen TEXT NOT NULL,
        source_platform TEXT,
        source_url TEXT,
        mutations TEXT,  -- JSON array of mutation types
        generation INTEGER DEFAULT 0,
        children TEXT,   -- JSON array of child hashes
        is_deepfake INTEGER NOT NULL,
        confidence REAL NOT NULL,
        metadata TEXT,   -- JSON object
        
        -- Location fields for origin tracking
        origin_country TEXT,
        origin_city TEXT,
        origin_latitude REAL,
        origin_longitude REAL,
        ip_hash TEXT,    -- Hashed IP for privacy
        
        FOREIGN KEY (parent_hash) REFERENCES lineage(video_hash)
    );
    
    -- Spread tracking (when/where videos appear)
    CREATE TABLE IF NOT EXISTS spread_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_hash TEXT NOT NULL,
        platform TEXT NOT NULL,
        url TEXT,
        discovered_at TEXT NOT NULL,
        view_count INTEGER,
        share_count INTEGER,
        metadata TEXT,
        
        -- Location fields for spread tracking
        country TEXT,
        city TEXT,
        latitude REAL,
        longitude REAL,
        ip_hash TEXT,    -- Hashed IP for privacy
        
        FOREIGN KEY (video_hash) REFERENCES lineage(video_hash)
    );
    
    -- LSH bands for fast similarity search
    CREATE TABLE IF NOT EXISTS lsh_bands (
        video_hash TEXT NOT NULL,
        band_index INTEGER NOT NULL,
        band_value TEXT NOT NULL,
        
        PRIMARY KEY (video_hash, band_index),
        FOREIGN KEY (video_hash) REFERENCES lineage(video_hash)
    );
    
    -- Indexes for fast lookups
    CREATE INDEX IF NOT EXISTS idx_lineage_perceptual ON lineage(perceptual_hash);
    CREATE INDEX IF NOT EXISTS idx_lineage_parent ON lineage(parent_hash);
    CREATE INDEX IF NOT EXISTS idx_lineage_generation ON lineage(generation);
    CREATE INDEX IF NOT EXISTS idx_spread_platform ON spread_events(platform);
    CREATE INDEX IF NOT EXISTS idx_spread_date ON spread_events(discovered_at);
    CREATE INDEX IF NOT EXISTS idx_lsh_band ON lsh_bands(band_index, band_value);
    """
    
    # Mutation detection thresholds
    MUTATION_THRESHOLDS = {
        'compression': 0.15,      # JPEG artifacts threshold
        'crop': 0.10,             # Aspect ratio change threshold
        'resize': 0.20,           # Resolution change threshold
        'watermark': 0.05,        # Edge overlay detection
        'color_shift': 0.12,      # Color histogram shift
        'temporal_edit': 0.08,    # Frame removal/addition
    }
    
    def __init__(
        self,
        db_path: str = "models/deepfake_lineage.db",
        hamming_threshold: int = 12,
        num_lsh_bands: int = 5
    ):
        """
        Initialize the Origin Finder.
        
        Args:
            db_path: Path to SQLite database
            hamming_threshold: Max Hamming distance for family matching
            num_lsh_bands: Number of LSH bands for similarity search
        """
        self.db_path = Path(db_path)
        self.hamming_threshold = hamming_threshold
        self.num_lsh_bands = num_lsh_bands
        
        # Thread-local storage
        self._local = threading.local()
        
        # Create database directory
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # Create video hash cache for extension API caching
        from ..core.video_hash_cache import VideoHashCache
        cache_db_path = str(self.db_path.parent / "lipsync_cache.db")
        self.video_hash_cache = VideoHashCache(db_path=cache_db_path)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    @contextmanager
    def _cursor(self):
        """Context manager for database cursor."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def _init_database(self):
        """Initialize database schema."""
        with self._cursor() as cursor:
            cursor.executescript(self.SCHEMA)
    
    def _compute_lsh_bands(self, perceptual_hash: str) -> List[str]:
        """
        Split perceptual hash into LSH bands for fast lookup.
        
        Args:
            perceptual_hash: The full perceptual hash string
            
        Returns:
            List of band values (substrings of the hash)
        """
        # Remove separators and convert to continuous string
        clean_hash = perceptual_hash.replace('-', '')
        
        # Split into bands
        band_size = len(clean_hash) // self.num_lsh_bands
        bands = []
        for i in range(self.num_lsh_bands):
            start = i * band_size
            end = start + band_size if i < self.num_lsh_bands - 1 else len(clean_hash)
            bands.append(clean_hash[start:end])
        
        return bands
    
    def _hamming_distance(self, hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two perceptual hashes.
        
        Args:
            hash1: First perceptual hash
            hash2: Second perceptual hash
            
        Returns:
            Number of differing bits
        """
        # Clean and convert hashes
        clean1 = hash1.replace('-', '')
        clean2 = hash2.replace('-', '')
        
        # Convert hex to binary and count differences
        try:
            int1 = int(clean1, 16)
            int2 = int(clean2, 16)
            xor = int1 ^ int2
            return bin(xor).count('1')
        except ValueError:
            # Fallback: character-by-character comparison
            return sum(c1 != c2 for c1, c2 in zip(clean1, clean2))
    
    def _detect_mutations(
        self,
        new_video_path: str,
        parent_video_path: Optional[str] = None,
        new_hash: Optional[str] = None,
        parent_hash: Optional[str] = None
    ) -> List[str]:
        """
        Detect what modifications were made between parent and child video.
        
        Args:
            new_video_path: Path to the new video
            parent_video_path: Path to parent video (optional)
            new_hash: Perceptual hash of new video
            parent_hash: Perceptual hash of parent video
            
        Returns:
            List of detected mutation types
        """
        mutations = []
        
        # If we have hashes, analyze hash differences
        if new_hash and parent_hash:
            hamming = self._hamming_distance(new_hash, parent_hash)
            
            # Different Hamming ranges suggest different mutation types
            if 1 <= hamming <= 5:
                mutations.append("minor_compression")
            elif 6 <= hamming <= 15:
                mutations.append("moderate_edit")
            elif 16 <= hamming <= 30:
                mutations.append("significant_modification")
            elif hamming > 30:
                mutations.append("major_transformation")
        
        # If we have video files, do deeper analysis
        if new_video_path and Path(new_video_path).exists():
            cap = cv2.VideoCapture(str(new_video_path))
            if cap.isOpened():
                # Get video properties
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                
                # Store for comparison
                new_props = {
                    'width': width,
                    'height': height,
                    'fps': fps,
                    'frames': frame_count,
                    'aspect': width / height if height > 0 else 0
                }
                
                # Read a frame for quality analysis
                ret, frame = cap.read()
                if ret:
                    # Check for compression artifacts (Laplacian variance)
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                    
                    if laplacian_var < 100:
                        mutations.append("heavy_compression")
                    elif laplacian_var < 500:
                        mutations.append("light_compression")
                    
                    # Check for watermark regions (edge detection on borders)
                    edges = cv2.Canny(gray, 50, 150)
                    border_edge_density = (
                        np.mean(edges[:20, :]) +    # Top
                        np.mean(edges[-20:, :]) +   # Bottom
                        np.mean(edges[:, :20]) +    # Left
                        np.mean(edges[:, -20:])     # Right
                    ) / 4
                    
                    if border_edge_density > 50:
                        mutations.append("possible_watermark")
                
                cap.release()
        
        return mutations if mutations else ["unknown_modification"]
    
    def find_family(self, perceptual_hash: str) -> Optional[List[DeepfakeLineageNode]]:
        """
        Find all related videos (family members) based on perceptual hash similarity.
        
        Args:
            perceptual_hash: The perceptual hash to search for
            
        Returns:
            List of related lineage nodes, or None if no family found
        """
        # Compute LSH bands for the query hash
        query_bands = self._compute_lsh_bands(perceptual_hash)
        
        # Find candidate matches using LSH
        candidates = set()
        with self._cursor() as cursor:
            for i, band in enumerate(query_bands):
                cursor.execute("""
                    SELECT video_hash FROM lsh_bands
                    WHERE band_index = ? AND band_value = ?
                """, (i, band))
                
                for row in cursor.fetchall():
                    candidates.add(row['video_hash'])
        
        if not candidates:
            return None
        
        # Filter candidates by Hamming distance
        family = []
        with self._cursor() as cursor:
            for video_hash in candidates:
                cursor.execute("""
                    SELECT * FROM lineage WHERE video_hash = ?
                """, (video_hash,))
                
                row = cursor.fetchone()
                if row:
                    candidate_phash = row['perceptual_hash']
                    distance = self._hamming_distance(perceptual_hash, candidate_phash)
                    
                    if distance <= self.hamming_threshold:
                        node = DeepfakeLineageNode(
                            video_hash=row['video_hash'],
                            perceptual_hash=row['perceptual_hash'],
                            parent_hash=row['parent_hash'],
                            first_seen=row['first_seen'],
                            source_platform=row['source_platform'],
                            source_url=row['source_url'],
                            mutations=json.loads(row['mutations']) if row['mutations'] else [],
                            generation=row['generation'],
                            children=json.loads(row['children']) if row['children'] else [],
                            is_deepfake=bool(row['is_deepfake']),
                            confidence=row['confidence'],
                            metadata=json.loads(row['metadata']) if row['metadata'] else {},
                            # Location fields
                            origin_country=row['origin_country'] if 'origin_country' in row.keys() else None,
                            origin_city=row['origin_city'] if 'origin_city' in row.keys() else None,
                            origin_latitude=row['origin_latitude'] if 'origin_latitude' in row.keys() else None,
                            origin_longitude=row['origin_longitude'] if 'origin_longitude' in row.keys() else None,
                            ip_hash=row['ip_hash'] if 'ip_hash' in row.keys() else None
                        )
                        node.metadata['hamming_distance'] = distance
                        family.append(node)
        
        # Sort by generation (oldest first)
        family.sort(key=lambda x: (x.generation, x.first_seen))
        
        return family if family else None
    
    def find_origin(self, perceptual_hash: str) -> Optional[DeepfakeLineageNode]:
        """
        Find the oldest known ancestor (original source) of a video.
        
        Args:
            perceptual_hash: The perceptual hash to trace back
            
        Returns:
            The origin node, or None if not found
        """
        family = self.find_family(perceptual_hash)
        
        if not family:
            return None
        
        # Find the node with generation 0 (or lowest generation)
        origin = min(family, key=lambda x: (x.generation, x.first_seen))
        return origin
    
    def register_video(
        self,
        video_hash: str,
        perceptual_hash: str,
        is_deepfake: bool,
        confidence: float,
        source_platform: Optional[str] = None,
        source_url: Optional[str] = None,
        video_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        # Location tracking parameters
        origin_country: Optional[str] = None,
        origin_city: Optional[str] = None,
        origin_latitude: Optional[float] = None,
        origin_longitude: Optional[float] = None,
        ip_hash: Optional[str] = None
    ) -> DeepfakeLineageNode:
        """
        Register a new video in the lineage database.
        
        This will:
        1. Check if the video already exists
        2. Find potential family members
        3. Determine parent relationship
        4. Detect mutations from parent
        5. Store in database with location data
        
        Args:
            video_hash: SHA256 content hash
            perceptual_hash: DCT-based perceptual hash
            is_deepfake: Detection result
            confidence: Detection confidence
            source_platform: Where video was found
            source_url: Direct URL
            video_path: Local path to video file
            metadata: Additional data
            origin_country: Country of upload origin
            origin_city: City of upload origin
            origin_latitude: Latitude coordinate
            origin_longitude: Longitude coordinate
            ip_hash: Hashed IP address for privacy
            
        Returns:
            The created or existing lineage node
        """
        # Check if already registered
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM lineage WHERE video_hash = ?",
                (video_hash,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update last seen and return existing
                return DeepfakeLineageNode(
                    video_hash=existing['video_hash'],
                    perceptual_hash=existing['perceptual_hash'],
                    parent_hash=existing['parent_hash'],
                    first_seen=existing['first_seen'],
                    source_platform=existing['source_platform'],
                    source_url=existing['source_url'],
                    mutations=json.loads(existing['mutations']) if existing['mutations'] else [],
                    generation=existing['generation'],
                    children=json.loads(existing['children']) if existing['children'] else [],
                    is_deepfake=bool(existing['is_deepfake']),
                    confidence=existing['confidence'],
                    metadata=json.loads(existing['metadata']) if existing['metadata'] else {},
                    # Location fields
                    origin_country=existing['origin_country'] if 'origin_country' in existing.keys() else None,
                    origin_city=existing['origin_city'] if 'origin_city' in existing.keys() else None,
                    origin_latitude=existing['origin_latitude'] if 'origin_latitude' in existing.keys() else None,
                    origin_longitude=existing['origin_longitude'] if 'origin_longitude' in existing.keys() else None,
                    ip_hash=existing['ip_hash'] if 'ip_hash' in existing.keys() else None
                )
        
        # Find potential family members
        family = self.find_family(perceptual_hash)
        
        # Determine parent and generation
        parent_hash = None
        generation = 0
        mutations = []
        
        if family:
            # Find the most likely parent (closest match with older timestamp)
            potential_parents = [
                node for node in family
                if node.first_seen < datetime.now().isoformat()
            ]
            
            if potential_parents:
                # Sort by Hamming distance (closest first)
                potential_parents.sort(
                    key=lambda x: x.metadata.get('hamming_distance', 999)
                )
                
                parent = potential_parents[0]
                parent_hash = parent.video_hash
                generation = parent.generation + 1
                
                # Detect mutations
                mutations = self._detect_mutations(
                    video_path, None, perceptual_hash, parent.perceptual_hash
                )
                
                # Update parent's children list
                self._add_child_to_parent(parent_hash, video_hash)
        
        # Create new node
        node = DeepfakeLineageNode(
            video_hash=video_hash,
            perceptual_hash=perceptual_hash,
            parent_hash=parent_hash,
            first_seen=datetime.now().isoformat(),
            source_platform=source_platform,
            source_url=source_url,
            mutations=mutations,
            generation=generation,
            children=[],
            is_deepfake=is_deepfake,
            confidence=confidence,
            metadata=metadata or {},
            # Location tracking
            origin_country=origin_country,
            origin_city=origin_city,
            origin_latitude=origin_latitude,
            origin_longitude=origin_longitude,
            ip_hash=ip_hash
        )
        
        # Store in database
        self._store_node(node)
        
        return node
    
    def _store_node(self, node: DeepfakeLineageNode):
        """Store a lineage node in the database."""
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO lineage
                (video_hash, perceptual_hash, parent_hash, first_seen,
                 source_platform, source_url, mutations, generation,
                 children, is_deepfake, confidence, metadata,
                 origin_country, origin_city, origin_latitude, origin_longitude, ip_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node.video_hash,
                node.perceptual_hash,
                node.parent_hash,
                node.first_seen,
                node.source_platform,
                node.source_url,
                json.dumps(node.mutations),
                node.generation,
                json.dumps(node.children),
                int(node.is_deepfake),
                node.confidence,
                json.dumps(node.metadata),
                node.origin_country,
                node.origin_city,
                node.origin_latitude,
                node.origin_longitude,
                node.ip_hash
            ))
            
            # Store LSH bands
            bands = self._compute_lsh_bands(node.perceptual_hash)
            for i, band in enumerate(bands):
                cursor.execute("""
                    INSERT OR REPLACE INTO lsh_bands
                    (video_hash, band_index, band_value)
                    VALUES (?, ?, ?)
                """, (node.video_hash, i, band))
    
    def _add_child_to_parent(self, parent_hash: str, child_hash: str):
        """Add a child to a parent's children list."""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT children FROM lineage WHERE video_hash = ?",
                (parent_hash,)
            )
            row = cursor.fetchone()
            
            if row:
                children = json.loads(row['children']) if row['children'] else []
                if child_hash not in children:
                    children.append(child_hash)
                    cursor.execute(
                        "UPDATE lineage SET children = ? WHERE video_hash = ?",
                        (json.dumps(children), parent_hash)
                    )
    
    def record_spread_event(
        self,
        video_hash: str,
        platform: str,
        url: Optional[str] = None,
        view_count: Optional[int] = None,
        share_count: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        # Location tracking parameters
        country: Optional[str] = None,
        city: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        ip_hash: Optional[str] = None
    ):
        """
        Record a sighting of a video on a platform.
        
        Args:
            video_hash: The video's content hash
            platform: Platform name (YouTube, Twitter, etc.)
            url: Direct URL to the video
            view_count: Number of views at time of discovery
            share_count: Number of shares
            metadata: Additional data
            country: Country where sighting occurred
            city: City where sighting occurred
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            ip_hash: Hashed IP for privacy
        """
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT INTO spread_events
                (video_hash, platform, url, discovered_at, view_count, share_count, metadata,
                 country, city, latitude, longitude, ip_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_hash,
                platform,
                url,
                datetime.now().isoformat(),
                view_count,
                share_count,
                json.dumps(metadata) if metadata else None,
                country,
                city,
                latitude,
                longitude,
                ip_hash
            ))
    
    def get_spread_timeline(self, video_hash: str) -> List[Dict[str, Any]]:
        """
        Get the spread timeline for a video and its family.
        
        Args:
            video_hash: Starting video hash
            
        Returns:
            List of spread events sorted by time
        """
        # First, find all family members
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT perceptual_hash FROM lineage WHERE video_hash = ?",
                (video_hash,)
            )
            row = cursor.fetchone()
            
            if not row:
                return []
            
            family = self.find_family(row['perceptual_hash']) or []
            family_hashes = [node.video_hash for node in family]
            
            if video_hash not in family_hashes:
                family_hashes.append(video_hash)
        
        # Get all spread events for the family
        events = []
        with self._cursor() as cursor:
            placeholders = ','.join('?' * len(family_hashes))
            cursor.execute(f"""
                SELECT se.*, l.generation, l.is_deepfake
                FROM spread_events se
                JOIN lineage l ON se.video_hash = l.video_hash
                WHERE se.video_hash IN ({placeholders})
                ORDER BY se.discovered_at ASC
            """, family_hashes)
            
            for row in cursor.fetchall():
                events.append({
                    'video_hash': row['video_hash'],
                    'platform': row['platform'],
                    'url': row['url'],
                    'discovered_at': row['discovered_at'],
                    'view_count': row['view_count'],
                    'share_count': row['share_count'],
                    'generation': row['generation'],
                    'is_deepfake': bool(row['is_deepfake']),
                    'metadata': json.loads(row['metadata']) if row['metadata'] else {},
                    # Location data
                    'country': row['country'] if 'country' in row.keys() else None,
                    'city': row['city'] if 'city' in row.keys() else None,
                    'latitude': row['latitude'] if 'latitude' in row.keys() else None,
                    'longitude': row['longitude'] if 'longitude' in row.keys() else None
                })
        
        return events
    
    def get_spread_locations(self, video_hash: str) -> List[Dict[str, Any]]:
        """
        Get all geographic locations where a video and its family appeared.
        
        Returns data formatted for map visualization (Leaflet markers).
        
        Args:
            video_hash: Starting video hash
            
        Returns:
            List of location markers with coordinates and metadata
        """
        # Get family hashes
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT perceptual_hash FROM lineage WHERE video_hash = ?",
                (video_hash,)
            )
            row = cursor.fetchone()
            
            if not row:
                return []
            
            family = self.find_family(row['perceptual_hash']) or []
            family_hashes = [node.video_hash for node in family]
            
            if video_hash not in family_hashes:
                family_hashes.append(video_hash)
        
        locations = []
        
        # Get origin locations from lineage
        with self._cursor() as cursor:
            placeholders = ','.join('?' * len(family_hashes))
            cursor.execute(f"""
                SELECT video_hash, first_seen, source_platform, is_deepfake,
                       origin_country, origin_city, origin_latitude, origin_longitude, generation
                FROM lineage
                WHERE video_hash IN ({placeholders})
                  AND origin_latitude IS NOT NULL
                  AND origin_longitude IS NOT NULL
            """, family_hashes)
            
            for row in cursor.fetchall():
                locations.append({
                    'type': 'origin',
                    'video_hash': row['video_hash'][:12] + '...',
                    'timestamp': row['first_seen'],
                    'platform': row['source_platform'] or 'Direct Upload',
                    'country': row['origin_country'],
                    'city': row['origin_city'],
                    'latitude': row['origin_latitude'],
                    'longitude': row['origin_longitude'],
                    'is_deepfake': bool(row['is_deepfake']),
                    'generation': row['generation'],
                    'marker_color': 'red' if row['is_deepfake'] else 'green'
                })
        
        # Get spread event locations
        with self._cursor() as cursor:
            cursor.execute(f"""
                SELECT se.video_hash, se.discovered_at, se.platform,
                       se.country, se.city, se.latitude, se.longitude,
                       l.is_deepfake, l.generation
                FROM spread_events se
                JOIN lineage l ON se.video_hash = l.video_hash
                WHERE se.video_hash IN ({placeholders})
                  AND se.latitude IS NOT NULL
                  AND se.longitude IS NOT NULL
            """, family_hashes)
            
            for row in cursor.fetchall():
                locations.append({
                    'type': 'spread',
                    'video_hash': row['video_hash'][:12] + '...',
                    'timestamp': row['discovered_at'],
                    'platform': row['platform'],
                    'country': row['country'],
                    'city': row['city'],
                    'latitude': row['latitude'],
                    'longitude': row['longitude'],
                    'is_deepfake': bool(row['is_deepfake']),
                    'generation': row['generation'],
                    'marker_color': 'orange' if row['is_deepfake'] else 'blue'
                })
        
        # Sort by timestamp
        locations.sort(key=lambda x: x['timestamp'])
        
        return locations

    def get_family_tree(self, video_hash: str) -> Dict[str, Any]:
        """
        Generate a family tree structure for visualization.
        
        Args:
            video_hash: Starting video hash
            
        Returns:
            Dictionary representing the family tree
        """
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT perceptual_hash FROM lineage WHERE video_hash = ?",
                (video_hash,)
            )
            row = cursor.fetchone()
            
            if not row:
                return {}
            
            family = self.find_family(row['perceptual_hash'])
            
            if not family:
                return {}
        
        # Build tree structure
        nodes = {node.video_hash: node for node in family}
        
        # Find root(s) - nodes with no parent in the family
        roots = []
        for node in family:
            if node.parent_hash is None or node.parent_hash not in nodes:
                roots.append(node)
        
        def build_subtree(node: DeepfakeLineageNode) -> Dict[str, Any]:
            """Recursively build subtree from a node."""
            children_trees = []
            for child_hash in node.children:
                if child_hash in nodes:
                    children_trees.append(build_subtree(nodes[child_hash]))
            
            return {
                'video_hash': node.video_hash[:16] + '...',  # Shortened for display
                'full_hash': node.video_hash,
                'generation': node.generation,
                'first_seen': node.first_seen,
                'platform': node.source_platform or 'Unknown',
                'is_deepfake': node.is_deepfake,
                'confidence': node.confidence,
                'mutations': node.mutations,
                # Location data
                'origin_country': node.origin_country,
                'origin_city': node.origin_city,
                'origin_latitude': node.origin_latitude,
                'origin_longitude': node.origin_longitude,
                'children': children_trees
            }
        
        # Build tree from roots
        if len(roots) == 1:
            return build_subtree(roots[0])
        else:
            return {
                'video_hash': 'Multiple Origins',
                'generation': -1,
                'children': [build_subtree(root) for root in roots]
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the lineage database."""
        with self._cursor() as cursor:
            # Total videos tracked
            cursor.execute("SELECT COUNT(*) as count FROM lineage")
            total_videos = cursor.fetchone()['count']
            
            # Deepfakes vs authentic
            cursor.execute("""
                SELECT is_deepfake, COUNT(*) as count
                FROM lineage GROUP BY is_deepfake
            """)
            deepfake_counts = {
                bool(row['is_deepfake']): row['count']
                for row in cursor.fetchall()
            }
            
            # Generation distribution
            cursor.execute("""
                SELECT generation, COUNT(*) as count
                FROM lineage GROUP BY generation
                ORDER BY generation
            """)
            generations = {
                row['generation']: row['count']
                for row in cursor.fetchall()
            }
            
            # Platform distribution
            cursor.execute("""
                SELECT platform, COUNT(*) as count
                FROM spread_events GROUP BY platform
                ORDER BY count DESC
            """)
            platforms = {
                row['platform']: row['count']
                for row in cursor.fetchall()
            }
            
            # Unique families (approximate by counting generation 0)
            cursor.execute("""
                SELECT COUNT(*) as count FROM lineage
                WHERE generation = 0
            """)
            unique_families = cursor.fetchone()['count']
            
            return {
                'total_videos': total_videos,
                'deepfakes': deepfake_counts.get(True, 0),
                'authentic': deepfake_counts.get(False, 0),
                'unique_families': unique_families,
                'generations': generations,
                'platform_spread': platforms,
                'avg_mutations_per_family': (
                    (total_videos - unique_families) / max(unique_families, 1)
                )
            }
    
    def generate_report(self, video_hash: str) -> str:
        """
        Generate a human-readable report about a video's origins and spread.
        
        Args:
            video_hash: The video to report on
            
        Returns:
            Formatted report string
        """
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM lineage WHERE video_hash = ?",
                (video_hash,)
            )
            row = cursor.fetchone()
            
            if not row:
                return f"❌ Video {video_hash[:16]}... not found in database"
        
        # Get family and origin
        family = self.find_family(row['perceptual_hash']) or []
        origin = self.find_origin(row['perceptual_hash'])
        spread = self.get_spread_timeline(video_hash)
        
        # Build report
        lines = [
            "=" * 60,
            "🔍 DEEPFAKE ORIGIN FINDER REPORT",
            "=" * 60,
            "",
            f"📹 Video Hash: {video_hash[:32]}...",
            f"📅 First Seen: {row['first_seen']}",
            f"🌐 Platform: {row['source_platform'] or 'Unknown'}",
            "",
            "─" * 40,
            "🎯 DETECTION RESULT",
            "─" * 40,
            f"  Status: {'🚨 DEEPFAKE DETECTED' if row['is_deepfake'] else '✅ Appears Authentic'}",
            f"  Confidence: {row['confidence']*100:.1f}%",
            "",
        ]
        
        # Origin information
        lines.extend([
            "─" * 40,
            "🌳 LINEAGE INFORMATION",
            "─" * 40,
        ])
        
        if origin:
            lines.extend([
                f"  Origin Hash: {origin.video_hash[:32]}...",
                f"  Origin Date: {origin.first_seen}",
                f"  Origin Platform: {origin.source_platform or 'Unknown'}",
                f"  Current Generation: {row['generation']} (0 = original)",
                f"  Total Family Members: {len(family)}",
            ])
        else:
            lines.append("  This appears to be an original/first-seen video")
        
        # Mutations
        if row['mutations']:
            mutations = json.loads(row['mutations'])
            lines.extend([
                "",
                "─" * 40,
                "🔄 DETECTED MUTATIONS",
                "─" * 40,
            ])
            for mut in mutations:
                lines.append(f"  • {mut.replace('_', ' ').title()}")
        
        # Spread information
        if spread:
            lines.extend([
                "",
                "─" * 40,
                "📊 SPREAD TIMELINE",
                "─" * 40,
            ])
            for event in spread[:5]:  # Show first 5
                lines.append(
                    f"  {event['discovered_at'][:10]} | "
                    f"{event['platform']:12} | "
                    f"Gen {event['generation']}"
                )
            if len(spread) > 5:
                lines.append(f"  ... and {len(spread) - 5} more events")
        
        lines.extend(["", "=" * 60])
        
        return "\n".join(lines)


# Convenience function for quick lookups
def trace_deepfake_origin(
    video_path: str,
    db_path: str = "models/deepfake_lineage.db"
) -> Optional[DeepfakeLineageNode]:
    """
    Quick function to trace the origin of a video.
    
    Args:
        video_path: Path to video file
        db_path: Path to lineage database
        
    Returns:
        Origin node if found, None otherwise
    """
    finder = DeepfakeOriginFinder(db_path)
    
    # Import hash computation from our cache module
    from ..core.video_hash_cache import VideoHashCache
    
    cache = VideoHashCache()
    video_hash, perceptual_hash = cache.compute_video_hash(video_path)
    
    return finder.find_origin(perceptual_hash)
