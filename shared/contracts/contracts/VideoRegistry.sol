// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AccessControl.sol";

/**
 * @title VideoRegistry
 * @dev Stores video detection results on-chain with perceptual hashing
 * @notice Immutable record of all deepfake detection analyses
 */
contract VideoRegistry is AccessControl {
    
    struct VideoRecord {
        bytes32 contentHash;        // SHA-256 of video content
        string perceptualHash;      // DCT-based perceptual hash (5 frames concatenated)
        bool isDeepfake;            // Detection result
        uint256 confidence;         // Confidence score (0-10000, basis points)
        uint256 lipsyncScore;       // Lip-sync analysis score (0-10000)
        uint256 factCheckScore;     // Fact-check score (0-10000)
        uint256 firstSeen;          // First detection timestamp
        uint256 lastSeen;           // Most recent detection timestamp
        uint256 detectionCount;     // Number of times detected
        bytes32 ipHash;             // Privacy-preserving hashed IP of first uploader
        string country;             // Origin country
        string city;                // Origin city
        int256 latitude;            // Latitude * 1000000 (6 decimal places)
        int256 longitude;           // Longitude * 1000000
        address uploaderNode;       // Node wallet that first uploaded
        string metadata;            // JSON metadata string
    }
    
    // ============ Storage ============
    
    // Primary storage: contentHash => VideoRecord
    mapping(bytes32 => VideoRecord) public videos;
    
    // Perceptual hash index: keccak256(perceptualHash) => contentHash[]
    mapping(bytes32 => bytes32[]) public perceptualHashIndex;
    
    // All video content hashes for enumeration
    bytes32[] public allVideoHashes;
    
    // Deepfake-only hashes for quick filtering
    bytes32[] public deepfakeHashes;
    
    // Stats counters
    uint256 public totalDeepfakes;
    uint256 public totalAuthentic;
    
    // ============ Events ============
    
    event VideoRegistered(
        bytes32 indexed contentHash,
        bool isDeepfake,
        uint256 confidence,
        address indexed uploaderNode,
        uint256 timestamp
    );
    
    event DeepfakeDetected(
        bytes32 indexed contentHash,
        uint256 confidence,
        string country,
        string city,
        bytes32 ipHash
    );
    
    event VideoRedetected(
        bytes32 indexed contentHash,
        uint256 detectionCount,
        bytes32 newIpHash,
        uint256 timestamp
    );
    
    event AuthenticVideoConfirmed(
        bytes32 indexed contentHash,
        uint256 confidence,
        address indexed uploaderNode
    );
    
    // ============ Functions ============
    
    /**
     * @dev Register a new video analysis result or record re-detection
     * @param _contentHash SHA-256 hash of video content
     * @param _perceptualHash DCT-based perceptual hash string
     * @param _isDeepfake Whether the video is a deepfake
     * @param _confidence Confidence score in basis points (0-10000)
     * @param _lipsyncScore Lip-sync analysis score (0-10000)
     * @param _factCheckScore Fact-check score (0-10000)
     * @param _ipHash Privacy-preserving hash of uploader IP
     * @param _country Country of origin
     * @param _city City of origin
     * @param _latitude Latitude scaled by 1,000,000
     * @param _longitude Longitude scaled by 1,000,000
     * @param _metadata JSON metadata string
     */
    function registerVideo(
        bytes32 _contentHash,
        string memory _perceptualHash,
        bool _isDeepfake,
        uint256 _confidence,
        uint256 _lipsyncScore,
        uint256 _factCheckScore,
        bytes32 _ipHash,
        string memory _country,
        string memory _city,
        int256 _latitude,
        int256 _longitude,
        string memory _metadata
    ) external onlyAuthorizedNode {
        require(_contentHash != bytes32(0), "VideoRegistry: invalid content hash");
        require(_confidence <= 10000, "VideoRegistry: confidence exceeds 10000");
        require(_lipsyncScore <= 10000, "VideoRegistry: lipsync score exceeds 10000");
        require(_factCheckScore <= 10000, "VideoRegistry: fact-check score exceeds 10000");
        
        VideoRecord storage record = videos[_contentHash];
        
        if (record.firstSeen == 0) {
            // ---- NEW VIDEO ----
            record.contentHash = _contentHash;
            record.perceptualHash = _perceptualHash;
            record.isDeepfake = _isDeepfake;
            record.confidence = _confidence;
            record.lipsyncScore = _lipsyncScore;
            record.factCheckScore = _factCheckScore;
            record.firstSeen = block.timestamp;
            record.lastSeen = block.timestamp;
            record.detectionCount = 1;
            record.ipHash = _ipHash;
            record.country = _country;
            record.city = _city;
            record.latitude = _latitude;
            record.longitude = _longitude;
            record.uploaderNode = msg.sender;
            record.metadata = _metadata;
            
            // Add to global index
            allVideoHashes.push(_contentHash);
            
            // Index by perceptual hash for similarity search
            bytes32 pHashKey = keccak256(abi.encodePacked(_perceptualHash));
            perceptualHashIndex[pHashKey].push(_contentHash);
            
            // Update counters
            if (_isDeepfake) {
                totalDeepfakes++;
                deepfakeHashes.push(_contentHash);
            } else {
                totalAuthentic++;
            }
            
            // Emit events
            emit VideoRegistered(_contentHash, _isDeepfake, _confidence, msg.sender, block.timestamp);
            
            if (_isDeepfake) {
                emit DeepfakeDetected(_contentHash, _confidence, _country, _city, _ipHash);
            } else {
                emit AuthenticVideoConfirmed(_contentHash, _confidence, msg.sender);
            }
        } else {
            // ---- RE-DETECTION ----
            record.lastSeen = block.timestamp;
            record.detectionCount++;
            
            emit VideoRedetected(_contentHash, record.detectionCount, _ipHash, block.timestamp);
        }
    }
    
    /**
     * @dev Batch register multiple videos in one transaction (gas efficient)
     * @param _contentHashes Array of content hashes
     * @param _perceptualHashes Array of perceptual hashes
     * @param _isDeepfakes Array of detection results
     * @param _confidences Array of confidence scores
     * @param _ipHashes Array of IP hashes
     * @param _countries Array of countries
     * @param _cities Array of cities
     */
    function batchRegisterVideos(
        bytes32[] memory _contentHashes,
        string[] memory _perceptualHashes,
        bool[] memory _isDeepfakes,
        uint256[] memory _confidences,
        bytes32[] memory _ipHashes,
        string[] memory _countries,
        string[] memory _cities
    ) external onlyAuthorizedNode {
        require(
            _contentHashes.length == _perceptualHashes.length &&
            _contentHashes.length == _isDeepfakes.length &&
            _contentHashes.length == _confidences.length,
            "VideoRegistry: array length mismatch"
        );
        require(_contentHashes.length <= 50, "VideoRegistry: batch too large (max 50)");
        
        for (uint256 i = 0; i < _contentHashes.length; i++) {
            if (_contentHashes[i] == bytes32(0)) continue;
            
            VideoRecord storage record = videos[_contentHashes[i]];
            
            if (record.firstSeen == 0) {
                record.contentHash = _contentHashes[i];
                record.perceptualHash = _perceptualHashes[i];
                record.isDeepfake = _isDeepfakes[i];
                record.confidence = _confidences[i];
                record.firstSeen = block.timestamp;
                record.lastSeen = block.timestamp;
                record.detectionCount = 1;
                record.ipHash = _ipHashes[i];
                record.country = _countries[i];
                record.city = _cities[i];
                record.uploaderNode = msg.sender;
                
                allVideoHashes.push(_contentHashes[i]);
                
                bytes32 pHashKey = keccak256(abi.encodePacked(_perceptualHashes[i]));
                perceptualHashIndex[pHashKey].push(_contentHashes[i]);
                
                if (_isDeepfakes[i]) {
                    totalDeepfakes++;
                    deepfakeHashes.push(_contentHashes[i]);
                    emit DeepfakeDetected(
                        _contentHashes[i], _confidences[i],
                        _countries[i], _cities[i], _ipHashes[i]
                    );
                } else {
                    totalAuthentic++;
                }
                
                emit VideoRegistered(
                    _contentHashes[i], _isDeepfakes[i],
                    _confidences[i], msg.sender, block.timestamp
                );
            } else {
                record.lastSeen = block.timestamp;
                record.detectionCount++;
                emit VideoRedetected(
                    _contentHashes[i], record.detectionCount,
                    _ipHashes[i], block.timestamp
                );
            }
        }
    }
    
    // ============ View Functions ============
    
    /**
     * @dev Get video record by content hash
     */
    function getVideo(bytes32 _contentHash) external view returns (VideoRecord memory) {
        require(videos[_contentHash].firstSeen != 0, "VideoRegistry: video not found");
        return videos[_contentHash];
    }
    
    /**
     * @dev Find videos with the same perceptual hash
     */
    function findSimilarVideos(string memory _perceptualHash) external view returns (bytes32[] memory) {
        bytes32 pHashKey = keccak256(abi.encodePacked(_perceptualHash));
        return perceptualHashIndex[pHashKey];
    }
    
    /**
     * @dev Check if a video exists in the registry
     */
    function videoExists(bytes32 _contentHash) external view returns (bool) {
        return videos[_contentHash].firstSeen != 0;
    }
    
    /**
     * @dev Get total number of registered videos
     */
    function getTotalVideos() external view returns (uint256) {
        return allVideoHashes.length;
    }
    
    /**
     * @dev Get all deepfake video hashes
     */
    function getDeepfakeHashes() external view returns (bytes32[] memory) {
        return deepfakeHashes;
    }
    
    /**
     * @dev Get network statistics
     */
    function getStats() external view returns (
        uint256 total,
        uint256 deepfakes,
        uint256 authentic
    ) {
        return (allVideoHashes.length, totalDeepfakes, totalAuthentic);
    }
    
    /**
     * @dev Get paginated video hashes
     * @param _offset Starting index
     * @param _limit Maximum results
     */
    function getVideoHashesPaginated(
        uint256 _offset,
        uint256 _limit
    ) external view returns (bytes32[] memory) {
        require(_offset < allVideoHashes.length, "VideoRegistry: offset out of bounds");
        
        uint256 end = _offset + _limit;
        if (end > allVideoHashes.length) {
            end = allVideoHashes.length;
        }
        
        bytes32[] memory result = new bytes32[](end - _offset);
        for (uint256 i = _offset; i < end; i++) {
            result[i - _offset] = allVideoHashes[i];
        }
        
        return result;
    }
}
