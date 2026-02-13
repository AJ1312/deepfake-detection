// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AccessControl.sol";

/**
 * @title AlertManager
 * @dev Manages threshold-based alerts and notification rules for deepfake tracking
 * @notice Emits events that off-chain listeners use to send notifications
 */
contract AlertManager is AccessControl {
    
    // ============ Structs ============
    
    struct AlertRule {
        uint256 detectionThreshold;     // Alert after N detections
        uint256 spreadThreshold;        // Alert after N spread events
        uint256 countryThreshold;       // Alert after spreading to N countries
        uint256 reuploadThreshold;      // Alert after N re-uploads from same IP
        bool enabled;
    }
    
    struct Alert {
        uint256 id;
        bytes32 videoHash;
        string alertType;               // "FIRST_DETECTION", "REUPLOAD", "GEO_SPREAD", "THRESHOLD", "VIRAL"
        string severity;                // "LOW", "MEDIUM", "HIGH", "CRITICAL"
        string message;
        uint256 timestamp;
        bool acknowledged;
        address acknowledgedBy;
        uint256 acknowledgedAt;
        bytes32 triggerIpHash;          // IP that triggered the alert
        string triggerCountry;          // Country that triggered the alert
    }
    
    // ============ Storage ============
    
    // Global alert rules
    AlertRule public globalRules;
    
    // Video-specific alert rules (optional overrides)
    mapping(bytes32 => AlertRule) public videoRules;
    mapping(bytes32 => bool) public hasVideoRules;
    
    // All alerts stored sequentially
    Alert[] public allAlerts;
    
    // Video hash => alert indices
    mapping(bytes32 => uint256[]) public videoAlertIndices;
    
    // Counters
    uint256 public totalAlerts;
    uint256 public unacknowledgedAlerts;
    
    // Alert suppression: prevent duplicate alerts within cooldown period
    mapping(bytes32 => mapping(bytes32 => uint256)) public lastAlertTime;
    // ^ videoHash => keccak256(alertType) => timestamp
    uint256 public alertCooldownSeconds;
    
    // ============ Events ============
    
    event AlertCreated(
        uint256 indexed alertId,
        bytes32 indexed videoHash,
        string alertType,
        string severity,
        string message,
        uint256 timestamp
    );
    
    event ThresholdCrossed(
        bytes32 indexed videoHash,
        uint256 detectionCount,
        uint256 threshold,
        uint256 timestamp
    );
    
    event ViralSpreadDetected(
        bytes32 indexed videoHash,
        uint256 spreadCount,
        uint256 uniqueCountries,
        uint256 threshold
    );
    
    event FirstDeepfakeAlert(
        bytes32 indexed videoHash,
        uint256 confidence,
        string country,
        bytes32 ipHash
    );
    
    event ReuploadAlert(
        bytes32 indexed videoHash,
        bytes32 indexed ipHash,
        uint256 reuploadCount,
        string country
    );
    
    event GeoSpreadAlert(
        bytes32 indexed videoHash,
        string fromCountry,
        string toCountry,
        uint256 uniqueCountries
    );
    
    event AlertAcknowledged(
        uint256 indexed alertId,
        address indexed acknowledgedBy,
        uint256 timestamp
    );
    
    event AlertRulesUpdated(
        uint256 detectionThreshold,
        uint256 spreadThreshold,
        uint256 countryThreshold,
        uint256 reuploadThreshold,
        bool enabled
    );
    
    // ============ Constructor ============
    
    constructor() {
        // Default thresholds
        globalRules = AlertRule({
            detectionThreshold: 100,
            spreadThreshold: 50,
            countryThreshold: 5,
            reuploadThreshold: 3,
            enabled: true
        });
        
        alertCooldownSeconds = 300; // 5-minute cooldown between identical alerts
    }
    
    // ============ Admin Functions ============
    
    /**
     * @dev Set global alert rules (admin only)
     */
    function setGlobalRules(
        uint256 _detectionThreshold,
        uint256 _spreadThreshold,
        uint256 _countryThreshold,
        uint256 _reuploadThreshold,
        bool _enabled
    ) external onlyOwner {
        globalRules = AlertRule({
            detectionThreshold: _detectionThreshold,
            spreadThreshold: _spreadThreshold,
            countryThreshold: _countryThreshold,
            reuploadThreshold: _reuploadThreshold,
            enabled: _enabled
        });
        
        emit AlertRulesUpdated(
            _detectionThreshold, _spreadThreshold,
            _countryThreshold, _reuploadThreshold, _enabled
        );
    }
    
    /**
     * @dev Set video-specific alert rules
     */
    function setVideoRules(
        bytes32 _videoHash,
        uint256 _detectionThreshold,
        uint256 _spreadThreshold,
        uint256 _countryThreshold,
        uint256 _reuploadThreshold
    ) external onlyOwner {
        videoRules[_videoHash] = AlertRule({
            detectionThreshold: _detectionThreshold,
            spreadThreshold: _spreadThreshold,
            countryThreshold: _countryThreshold,
            reuploadThreshold: _reuploadThreshold,
            enabled: true
        });
        hasVideoRules[_videoHash] = true;
    }
    
    /**
     * @dev Set alert cooldown period
     */
    function setAlertCooldown(uint256 _seconds) external onlyOwner {
        alertCooldownSeconds = _seconds;
    }
    
    // ============ Alert Trigger Functions ============
    
    /**
     * @dev Alert: First deepfake detected
     */
    function triggerFirstDetectionAlert(
        bytes32 _videoHash,
        uint256 _confidence,
        string memory _country,
        bytes32 _ipHash
    ) external onlyAuthorizedNode {
        if (!_shouldAlert(_videoHash, "FIRST_DETECTION")) return;
        
        string memory severity = _confidence >= 8000 ? "CRITICAL" : 
                                  _confidence >= 6000 ? "HIGH" : "MEDIUM";
        
        string memory message = string(abi.encodePacked(
            "New deepfake detected with ", _uint2str(_confidence / 100),
            "% confidence from ", _country
        ));
        
        _createAlert(_videoHash, "FIRST_DETECTION", severity, message, _ipHash, _country);
        emit FirstDeepfakeAlert(_videoHash, _confidence, _country, _ipHash);
    }
    
    /**
     * @dev Alert: Same IP re-uploaded flagged video
     */
    function triggerReuploadAlert(
        bytes32 _videoHash,
        bytes32 _ipHash,
        uint256 _reuploadCount,
        string memory _country
    ) external onlyAuthorizedNode {
        AlertRule memory rules = _getEffectiveRules(_videoHash);
        
        if (_reuploadCount < rules.reuploadThreshold) return;
        if (!_shouldAlert(_videoHash, "REUPLOAD")) return;
        
        string memory message = string(abi.encodePacked(
            "Flagged video re-uploaded ", _uint2str(_reuploadCount),
            " times from same IP in ", _country
        ));
        
        _createAlert(_videoHash, "REUPLOAD", "HIGH", message, _ipHash, _country);
        emit ReuploadAlert(_videoHash, _ipHash, _reuploadCount, _country);
    }
    
    /**
     * @dev Alert: Video spreading to new geographic region
     */
    function triggerGeoSpreadAlert(
        bytes32 _videoHash,
        string memory _fromCountry,
        string memory _toCountry,
        uint256 _uniqueCountries
    ) external onlyAuthorizedNode {
        AlertRule memory rules = _getEffectiveRules(_videoHash);
        
        if (_uniqueCountries < rules.countryThreshold) return;
        if (!_shouldAlert(_videoHash, "GEO_SPREAD")) return;
        
        string memory severity = _uniqueCountries >= 10 ? "CRITICAL" : "HIGH";
        
        string memory message = string(abi.encodePacked(
            "Deepfake spread from ", _fromCountry, " to ", _toCountry,
            " (", _uint2str(_uniqueCountries), " countries total)"
        ));
        
        _createAlert(_videoHash, "GEO_SPREAD", severity, message, bytes32(0), _toCountry);
        emit GeoSpreadAlert(_videoHash, _fromCountry, _toCountry, _uniqueCountries);
    }
    
    /**
     * @dev Alert: Detection or spread threshold crossed
     */
    function checkThresholds(
        bytes32 _videoHash,
        uint256 _detectionCount,
        uint256 _spreadCount,
        uint256 _uniqueCountries
    ) external onlyAuthorizedNode {
        AlertRule memory rules = _getEffectiveRules(_videoHash);
        if (!rules.enabled) return;
        
        // Detection threshold
        if (_detectionCount >= rules.detectionThreshold && _detectionCount % rules.detectionThreshold == 0) {
            if (_shouldAlert(_videoHash, "THRESHOLD")) {
                string memory msg1 = string(abi.encodePacked(
                    "Video detected ", _uint2str(_detectionCount), " times"
                ));
                _createAlert(_videoHash, "THRESHOLD", "HIGH", msg1, bytes32(0), "");
                emit ThresholdCrossed(_videoHash, _detectionCount, rules.detectionThreshold, block.timestamp);
            }
        }
        
        // Spread threshold
        if (_spreadCount >= rules.spreadThreshold && _spreadCount % rules.spreadThreshold == 0) {
            if (_shouldAlert(_videoHash, "VIRAL")) {
                string memory msg2 = string(abi.encodePacked(
                    "Video spread to ", _uint2str(_spreadCount), " locations across ",
                    _uint2str(_uniqueCountries), " countries"
                ));
                _createAlert(_videoHash, "VIRAL", "CRITICAL", msg2, bytes32(0), "");
                emit ViralSpreadDetected(_videoHash, _spreadCount, _uniqueCountries, rules.spreadThreshold);
            }
        }
    }
    
    // ============ Alert Management ============
    
    /**
     * @dev Acknowledge an alert
     */
    function acknowledgeAlert(uint256 _alertId) external onlyAuthorizedNode {
        require(_alertId < allAlerts.length, "AlertManager: invalid alert ID");
        require(!allAlerts[_alertId].acknowledged, "AlertManager: already acknowledged");
        
        allAlerts[_alertId].acknowledged = true;
        allAlerts[_alertId].acknowledgedBy = msg.sender;
        allAlerts[_alertId].acknowledgedAt = block.timestamp;
        
        if (unacknowledgedAlerts > 0) {
            unacknowledgedAlerts--;
        }
        
        emit AlertAcknowledged(_alertId, msg.sender, block.timestamp);
    }
    
    /**
     * @dev Batch acknowledge multiple alerts
     */
    function batchAcknowledgeAlerts(uint256[] memory _alertIds) external onlyAuthorizedNode {
        for (uint256 i = 0; i < _alertIds.length; i++) {
            if (_alertIds[i] < allAlerts.length && !allAlerts[_alertIds[i]].acknowledged) {
                allAlerts[_alertIds[i]].acknowledged = true;
                allAlerts[_alertIds[i]].acknowledgedBy = msg.sender;
                allAlerts[_alertIds[i]].acknowledgedAt = block.timestamp;
                
                if (unacknowledgedAlerts > 0) {
                    unacknowledgedAlerts--;
                }
                
                emit AlertAcknowledged(_alertIds[i], msg.sender, block.timestamp);
            }
        }
    }
    
    // ============ View Functions ============
    
    /**
     * @dev Get all alerts for a video
     */
    function getVideoAlerts(bytes32 _videoHash) external view returns (Alert[] memory) {
        uint256[] memory indices = videoAlertIndices[_videoHash];
        Alert[] memory result = new Alert[](indices.length);
        
        for (uint256 i = 0; i < indices.length; i++) {
            result[i] = allAlerts[indices[i]];
        }
        
        return result;
    }
    
    /**
     * @dev Get total number of alerts
     */
    function getTotalAlerts() external view returns (uint256) {
        return totalAlerts;
    }
    
    /**
     * @dev Get alert by ID
     */
    function getAlert(uint256 _alertId) external view returns (Alert memory) {
        require(_alertId < allAlerts.length, "AlertManager: invalid alert ID");
        return allAlerts[_alertId];
    }
    
    /**
     * @dev Get unacknowledged alerts count
     */
    function getUnacknowledgedCount() external view returns (uint256) {
        return unacknowledgedAlerts;
    }
    
    /**
     * @dev Get paginated alerts
     */
    function getAlertsPaginated(
        uint256 _offset,
        uint256 _limit
    ) external view returns (Alert[] memory) {
        require(_offset < allAlerts.length || allAlerts.length == 0, "AlertManager: offset out of bounds");
        
        if (allAlerts.length == 0) {
            return new Alert[](0);
        }
        
        uint256 end = _offset + _limit;
        if (end > allAlerts.length) {
            end = allAlerts.length;
        }
        
        Alert[] memory result = new Alert[](end - _offset);
        for (uint256 i = _offset; i < end; i++) {
            result[i - _offset] = allAlerts[i];
        }
        
        return result;
    }
    
    // ============ Internal Functions ============
    
    function _createAlert(
        bytes32 _videoHash,
        string memory _alertType,
        string memory _severity,
        string memory _message,
        bytes32 _triggerIpHash,
        string memory _triggerCountry
    ) internal {
        uint256 alertId = allAlerts.length;
        
        Alert memory newAlert = Alert({
            id: alertId,
            videoHash: _videoHash,
            alertType: _alertType,
            severity: _severity,
            message: _message,
            timestamp: block.timestamp,
            acknowledged: false,
            acknowledgedBy: address(0),
            acknowledgedAt: 0,
            triggerIpHash: _triggerIpHash,
            triggerCountry: _triggerCountry
        });
        
        allAlerts.push(newAlert);
        videoAlertIndices[_videoHash].push(alertId);
        
        totalAlerts++;
        unacknowledgedAlerts++;
        
        // Update cooldown timestamp
        bytes32 alertTypeHash = keccak256(abi.encodePacked(_alertType));
        lastAlertTime[_videoHash][alertTypeHash] = block.timestamp;
        
        emit AlertCreated(alertId, _videoHash, _alertType, _severity, _message, block.timestamp);
    }
    
    function _shouldAlert(bytes32 _videoHash, string memory _alertType) internal view returns (bool) {
        AlertRule memory rules = _getEffectiveRules(_videoHash);
        if (!rules.enabled) return false;
        
        // Check cooldown
        bytes32 alertTypeHash = keccak256(abi.encodePacked(_alertType));
        uint256 lastTime = lastAlertTime[_videoHash][alertTypeHash];
        
        if (lastTime != 0 && block.timestamp - lastTime < alertCooldownSeconds) {
            return false; // Still in cooldown
        }
        
        return true;
    }
    
    function _getEffectiveRules(bytes32 _videoHash) internal view returns (AlertRule memory) {
        if (hasVideoRules[_videoHash]) {
            return videoRules[_videoHash];
        }
        return globalRules;
    }
    
    function _uint2str(uint256 _i) internal pure returns (string memory) {
        if (_i == 0) return "0";
        uint256 j = _i;
        uint256 len;
        while (j != 0) {
            len++;
            j /= 10;
        }
        bytes memory bstr = new bytes(len);
        uint256 k = len;
        while (_i != 0) {
            k = k - 1;
            uint8 temp = (48 + uint8(_i - _i / 10 * 10));
            bytes1 b1 = bytes1(temp);
            bstr[k] = b1;
            _i /= 10;
        }
        return string(bstr);
    }
}
