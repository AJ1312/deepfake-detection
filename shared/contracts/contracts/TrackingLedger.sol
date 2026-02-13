// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AccessControl.sol";

/**
 * @title TrackingLedger
 * @dev Records spread events, lineage tracking, and geographic movement for videos
 * @notice Provides immutable tracking of deepfake video propagation
 */
contract TrackingLedger is AccessControl {
    
    // ============ Structs ============
    
    struct SpreadEvent {
        bytes32 videoHash;          // Reference to VideoRegistry
        uint256 timestamp;          // Block timestamp
        bytes32 ipHash;             // Privacy-preserving IP hash
        string country;
        string city;
        int256 latitude;            // Scaled by 1,000,000
        int256 longitude;           // Scaled by 1,000,000
        string platform;            // e.g., "Direct Upload", "YouTube", "Twitter"
        string sourceUrl;           // Where the video was found
        address reporterNode;       // Node that reported this event
    }
    
    struct LineageRecord {
        bytes32 videoHash;
        bytes32 parentHash;         // Parent video hash (bytes32(0) if original)
        uint256 generation;         // Distance from original (0 = original)
        string[] mutations;         // Detected mutations: "compression", "crop", etc.
        bytes32[] childHashes;      // Child variant hashes
        uint256 registeredAt;
    }
    
    struct LocationSummary {
        string country;
        string city;
        uint256 eventCount;
        uint256 firstSeen;
        uint256 lastSeen;
    }
    
    // ============ Storage ============
    
    // Video hash => SpreadEvent[]
    mapping(bytes32 => SpreadEvent[]) public spreadEvents;
    
    // Video hash => LineageRecord
    mapping(bytes32 => LineageRecord) public lineage;
    
    // Video hash => IP hash => upload count (same-IP re-upload tracking)
    mapping(bytes32 => mapping(bytes32 => uint256)) public ipUploadCount;
    
    // Video hash => IP hash => first upload timestamp
    mapping(bytes32 => mapping(bytes32 => uint256)) public ipFirstUpload;
    
    // Video hash => country hash => event count (geographic spread tracking)
    mapping(bytes32 => mapping(bytes32 => uint256)) public countrySpreadCount;
    
    // Video hash => unique country count
    mapping(bytes32 => uint256) public uniqueCountryCount;
    
    // Global spread event counter
    uint256 public totalSpreadEvents;
    
    // ============ Events ============
    
    event SpreadEventRecorded(
        bytes32 indexed videoHash,
        string country,
        string city,
        bytes32 indexed ipHash,
        string platform,
        uint256 timestamp
    );
    
    event SameIPReupload(
        bytes32 indexed videoHash,
        bytes32 indexed ipHash,
        uint256 uploadCount,
        uint256 timeSinceFirst
    );
    
    event NewLocationSpread(
        bytes32 indexed videoHash,
        string previousCountry,
        string newCountry,
        uint256 uniqueCountries,
        uint256 timestamp
    );
    
    event LineageEstablished(
        bytes32 indexed childHash,
        bytes32 indexed parentHash,
        uint256 generation,
        string[] mutations
    );
    
    event ViralSpreadWarning(
        bytes32 indexed videoHash,
        uint256 spreadCount,
        uint256 uniqueCountries
    );
    
    // ============ Functions ============
    
    /**
     * @dev Record a spread event for a video
     * @param _videoHash Content hash of the video
     * @param _ipHash Privacy-preserving hash of reporter's IP
     * @param _country Country where event occurred
     * @param _city City where event occurred
     * @param _latitude Latitude scaled by 1,000,000
     * @param _longitude Longitude scaled by 1,000,000
     * @param _platform Platform where video was found
     * @param _sourceUrl URL of the video on the platform
     */
    function recordSpreadEvent(
        bytes32 _videoHash,
        bytes32 _ipHash,
        string memory _country,
        string memory _city,
        int256 _latitude,
        int256 _longitude,
        string memory _platform,
        string memory _sourceUrl
    ) external onlyAuthorizedNode {
        require(_videoHash != bytes32(0), "TrackingLedger: invalid video hash");
        
        // Create spread event
        SpreadEvent memory newEvent = SpreadEvent({
            videoHash: _videoHash,
            timestamp: block.timestamp,
            ipHash: _ipHash,
            country: _country,
            city: _city,
            latitude: _latitude,
            longitude: _longitude,
            platform: _platform,
            sourceUrl: _sourceUrl,
            reporterNode: msg.sender
        });
        
        spreadEvents[_videoHash].push(newEvent);
        totalSpreadEvents++;
        
        emit SpreadEventRecorded(_videoHash, _country, _city, _ipHash, _platform, block.timestamp);
        
        // ---- Same-IP re-upload detection ----
        ipUploadCount[_videoHash][_ipHash]++;
        
        if (ipUploadCount[_videoHash][_ipHash] == 1) {
            // First upload from this IP
            ipFirstUpload[_videoHash][_ipHash] = block.timestamp;
        } else {
            // Re-upload detected!
            uint256 timeSinceFirst = block.timestamp - ipFirstUpload[_videoHash][_ipHash];
            emit SameIPReupload(
                _videoHash,
                _ipHash,
                ipUploadCount[_videoHash][_ipHash],
                timeSinceFirst
            );
        }
        
        // ---- Geographic spread detection ----
        bytes32 countryHash = keccak256(abi.encodePacked(_country));
        
        if (countrySpreadCount[_videoHash][countryHash] == 0) {
            // First appearance in this country
            uniqueCountryCount[_videoHash]++;
            
            // Check if there were previous events in other countries
            if (spreadEvents[_videoHash].length > 1) {
                // Find last event's country
                SpreadEvent memory prevEvent = spreadEvents[_videoHash][spreadEvents[_videoHash].length - 2];
                
                if (keccak256(abi.encodePacked(prevEvent.country)) != countryHash) {
                    emit NewLocationSpread(
                        _videoHash,
                        prevEvent.country,
                        _country,
                        uniqueCountryCount[_videoHash],
                        block.timestamp
                    );
                }
            }
        }
        
        countrySpreadCount[_videoHash][countryHash]++;
        
        // ---- Viral spread warning ----
        uint256 spreadCount = spreadEvents[_videoHash].length;
        if (spreadCount == 10 || spreadCount == 50 || spreadCount == 100 || spreadCount % 500 == 0) {
            emit ViralSpreadWarning(_videoHash, spreadCount, uniqueCountryCount[_videoHash]);
        }
    }
    
    /**
     * @dev Register lineage relationship between parent and child video
     * @param _childHash Content hash of the child/variant video
     * @param _parentHash Content hash of the parent video
     * @param _generation Distance from original (parent.generation + 1)
     * @param _mutations Array of detected mutations
     */
    function registerLineage(
        bytes32 _childHash,
        bytes32 _parentHash,
        uint256 _generation,
        string[] memory _mutations
    ) external onlyAuthorizedNode {
        require(_childHash != bytes32(0), "TrackingLedger: invalid child hash");
        require(
            lineage[_childHash].registeredAt == 0,
            "TrackingLedger: lineage already registered"
        );
        
        // Create lineage record
        lineage[_childHash] = LineageRecord({
            videoHash: _childHash,
            parentHash: _parentHash,
            generation: _generation,
            mutations: _mutations,
            childHashes: new bytes32[](0),
            registeredAt: block.timestamp
        });
        
        // Update parent's children array if parent exists
        if (_parentHash != bytes32(0) && lineage[_parentHash].registeredAt != 0) {
            lineage[_parentHash].childHashes.push(_childHash);
        }
        
        emit LineageEstablished(_childHash, _parentHash, _generation, _mutations);
    }
    
    // ============ View Functions ============
    
    /**
     * @dev Get all spread events for a video
     */
    function getSpreadEvents(bytes32 _videoHash) external view returns (SpreadEvent[] memory) {
        return spreadEvents[_videoHash];
    }
    
    /**
     * @dev Get spread event count for a video
     */
    function getSpreadCount(bytes32 _videoHash) external view returns (uint256) {
        return spreadEvents[_videoHash].length;
    }
    
    /**
     * @dev Get lineage information for a video
     */
    function getLineage(bytes32 _videoHash) external view returns (LineageRecord memory) {
        return lineage[_videoHash];
    }
    
    /**
     * @dev Get number of times a specific IP uploaded a specific video
     */
    function getIPUploadCount(bytes32 _videoHash, bytes32 _ipHash) external view returns (uint256) {
        return ipUploadCount[_videoHash][_ipHash];
    }
    
    /**
     * @dev Get number of unique countries a video has spread to
     */
    function getUniqueCountryCount(bytes32 _videoHash) external view returns (uint256) {
        return uniqueCountryCount[_videoHash];
    }
    
    /**
     * @dev Get paginated spread events
     */
    function getSpreadEventsPaginated(
        bytes32 _videoHash,
        uint256 _offset,
        uint256 _limit
    ) external view returns (SpreadEvent[] memory) {
        SpreadEvent[] storage events = spreadEvents[_videoHash];
        require(_offset < events.length, "TrackingLedger: offset out of bounds");
        
        uint256 end = _offset + _limit;
        if (end > events.length) {
            end = events.length;
        }
        
        SpreadEvent[] memory result = new SpreadEvent[](end - _offset);
        for (uint256 i = _offset; i < end; i++) {
            result[i - _offset] = events[i];
        }
        
        return result;
    }
    
    /**
     * @dev Trace lineage back to original (generation 0)
     * @param _videoHash Starting video hash
     * @param _maxDepth Maximum generations to trace back (prevent infinite loop)
     * @return ancestors Array of ancestor hashes from immediate parent to origin
     */
    function traceToOrigin(
        bytes32 _videoHash,
        uint256 _maxDepth
    ) external view returns (bytes32[] memory) {
        bytes32[] memory ancestors = new bytes32[](_maxDepth);
        uint256 count = 0;
        bytes32 current = _videoHash;
        
        for (uint256 i = 0; i < _maxDepth; i++) {
            bytes32 parent = lineage[current].parentHash;
            if (parent == bytes32(0) || lineage[parent].registeredAt == 0) {
                break;
            }
            ancestors[count] = parent;
            count++;
            current = parent;
        }
        
        // Trim array to actual size
        bytes32[] memory result = new bytes32[](count);
        for (uint256 i = 0; i < count; i++) {
            result[i] = ancestors[i];
        }
        
        return result;
    }
}
