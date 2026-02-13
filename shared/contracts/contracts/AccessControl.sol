// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AccessControl
 * @dev Manages authorized nodes (Pi/laptop wallets) for write access
 * @notice Provides role-based access for deepfake detection network nodes
 */
contract AccessControl {
    
    address public owner;
    
    // Mapping: address => authorized status
    mapping(address => bool) public authorizedNodes;
    
    // Array of authorized addresses for enumeration
    address[] public authorizedNodeList;
    
    // Node metadata
    struct NodeInfo {
        string name;
        string nodeType;        // "pi" or "laptop"
        uint256 authorizedAt;
        bool active;
    }
    
    mapping(address => NodeInfo) public nodeInfo;
    
    // Events
    event NodeAuthorized(address indexed node, string name, string nodeType, address authorizedBy);
    event NodeDeauthorized(address indexed node, address deauthorizedBy);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    
    modifier onlyOwner() {
        require(msg.sender == owner, "AccessControl: caller is not owner");
        _;
    }
    
    modifier onlyAuthorizedNode() {
        require(
            authorizedNodes[msg.sender] || msg.sender == owner,
            "AccessControl: caller is not authorized"
        );
        _;
    }
    
    constructor() {
        owner = msg.sender;
        authorizedNodes[msg.sender] = true;
        authorizedNodeList.push(msg.sender);
        
        nodeInfo[msg.sender] = NodeInfo({
            name: "Owner Node",
            nodeType: "admin",
            authorizedAt: block.timestamp,
            active: true
        });
    }
    
    /**
     * @dev Authorize a new node (Pi or laptop wallet)
     * @param _node Address of the node to authorize
     * @param _name Human-readable name for the node
     * @param _nodeType Type of node: "pi", "laptop-host", "laptop-client"
     */
    function authorizeNode(
        address _node,
        string memory _name,
        string memory _nodeType
    ) external onlyOwner {
        require(!authorizedNodes[_node], "AccessControl: already authorized");
        require(_node != address(0), "AccessControl: zero address");
        
        authorizedNodes[_node] = true;
        authorizedNodeList.push(_node);
        
        nodeInfo[_node] = NodeInfo({
            name: _name,
            nodeType: _nodeType,
            authorizedAt: block.timestamp,
            active: true
        });
        
        emit NodeAuthorized(_node, _name, _nodeType, msg.sender);
    }
    
    /**
     * @dev Deauthorize a node
     * @param _node Address of the node to deauthorize
     */
    function deauthorizeNode(address _node) external onlyOwner {
        require(authorizedNodes[_node], "AccessControl: not authorized");
        require(_node != owner, "AccessControl: cannot deauthorize owner");
        
        authorizedNodes[_node] = false;
        nodeInfo[_node].active = false;
        
        emit NodeDeauthorized(_node, msg.sender);
    }
    
    /**
     * @dev Transfer contract ownership
     * @param _newOwner Address of the new owner
     */
    function transferOwnership(address _newOwner) external onlyOwner {
        require(_newOwner != address(0), "AccessControl: zero address");
        
        address previousOwner = owner;
        owner = _newOwner;
        
        if (!authorizedNodes[_newOwner]) {
            authorizedNodes[_newOwner] = true;
            authorizedNodeList.push(_newOwner);
            
            nodeInfo[_newOwner] = NodeInfo({
                name: "New Owner",
                nodeType: "admin",
                authorizedAt: block.timestamp,
                active: true
            });
        }
        
        emit OwnershipTransferred(previousOwner, _newOwner);
    }
    
    /**
     * @dev Get all authorized node addresses
     * @return Array of authorized addresses (includes deauthorized ones, check nodeInfo.active)
     */
    function getAuthorizedNodes() external view returns (address[] memory) {
        return authorizedNodeList;
    }
    
    /**
     * @dev Get count of active authorized nodes
     * @return Count of currently active nodes
     */
    function getActiveNodeCount() external view returns (uint256) {
        uint256 count = 0;
        for (uint256 i = 0; i < authorizedNodeList.length; i++) {
            if (authorizedNodes[authorizedNodeList[i]]) {
                count++;
            }
        }
        return count;
    }
    
    /**
     * @dev Check if address is authorized
     * @param _node Address to check
     * @return Whether the address is authorized
     */
    function isAuthorized(address _node) external view returns (bool) {
        return authorizedNodes[_node] || _node == owner;
    }
    
    /**
     * @dev Get node information
     * @param _node Address of the node
     * @return Node information struct
     */
    function getNodeInfo(address _node) external view returns (NodeInfo memory) {
        return nodeInfo[_node];
    }
}
