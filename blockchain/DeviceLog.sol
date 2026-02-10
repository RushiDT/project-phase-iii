// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DeviceLog {
    
    // ==================== DEVICE REGISTRY ====================
    struct Device {
        string id;
        string deviceType;
        string gatewayId;
        uint256 registeredAt;
        bool isRegistered;
    }

    mapping(string => Device) public registeredDevices;
    mapping(string => uint256) public deviceTrustScores;

    // ==================== ANOMALY LOGGING ====================
    struct Log {
        uint256 timestamp;
        string deviceId;
        string gatewayId;     // Identifying which gateway forwarded this
        uint256 anomalyScore; // Scaled by 100
        string dataHash;      // Hash of specific log data
        string batchHash;     // Hash of the entire batch from Gateway
        string eventType;     // "ANOMALY", "SECURITY_ALERT", etc.
    }
    Log[] public logs;

    event LogAdded(string indexed deviceId, string gatewayId, uint256 timestamp, string eventType);
    event DeviceRegistered(string indexed deviceId, string deviceType, string gatewayId);

    // ==================== CONTROL COMMANDS ====================
    struct ControlCommand {
        uint256 timestamp;
        string deviceId;
        string userId;
        string command;       // "ON", "OFF", "DIM:50", etc.
        bool approved;        // Whether trust check passed
        bool executed;        // Whether device confirmed execution
        uint256 trustAtTime;  // Trust score at time of request
    }

    ControlCommand[] public commands;
    uint256 public constant MIN_TRUST_SCORE = 30;

    event ControlRequested(uint256 indexed commandId, string deviceId, string command, bool approved);
    event ControlExecuted(uint256 indexed commandId, bool success);

    constructor() {}

    // ==================== REGISTRATION FUNCTIONS ====================
    function registerDevice(
        string memory _deviceId,
        string memory _deviceType,
        string memory _gatewayId
    ) public {
        require(!registeredDevices[_deviceId].isRegistered, "Device already registered");
        
        registeredDevices[_deviceId] = Device({
            id: _deviceId,
            deviceType: _deviceType,
            gatewayId: _gatewayId,
            registeredAt: block.timestamp,
            isRegistered: true
        });
        
        deviceTrustScores[_deviceId] = 100; // Initialize trust at registration
        
        emit DeviceRegistered(_deviceId, _deviceType, _gatewayId);
    }

    // ==================== ANOMALY FUNCTIONS ====================
    function addLog(
        string memory _deviceId,
        string memory _gatewayId,
        uint256 _anomalyScore,
        string memory _dataHash,
        string memory _batchHash,
        string memory _eventType
    ) public {
        require(registeredDevices[_deviceId].isRegistered, "Unauthorized: Device not registered on Blockchain");
        logs.push(Log({
            timestamp: block.timestamp,
            deviceId: _deviceId,
            gatewayId: _gatewayId,
            anomalyScore: _anomalyScore,
            dataHash: _dataHash,
            batchHash: _batchHash,
            eventType: _eventType
        }));

        // Initialize trust score for new devices
        if (deviceTrustScores[_deviceId] == 0) {
            deviceTrustScores[_deviceId] = 100;
        }

        // --- Granular Trust Score Management ---
        bytes32 typeHash = keccak256(bytes(_eventType));
        
        if (typeHash == keccak256(bytes("SECURITY_ALERT"))) {
            // Critical security alert: Major penalty
            if (deviceTrustScores[_deviceId] > 20) deviceTrustScores[_deviceId] -= 20;
            else deviceTrustScores[_deviceId] = 0;
        } 
        else if (typeHash == keccak256(bytes("ANOMALY"))) {
            // Machine Learning detected anomaly: Moderate penalty
            if (deviceTrustScores[_deviceId] > 10) deviceTrustScores[_deviceId] -= 10;
            else deviceTrustScores[_deviceId] = 0;
        }
        else if (typeHash == keccak256(bytes("HEARTBEAT_LOST"))) {
            // Device went offline unexpectedly: Small penalty
            if (deviceTrustScores[_deviceId] > 5) deviceTrustScores[_deviceId] -= 5;
        }
        else if (typeHash == keccak256(bytes("BATCH_RECEIPT"))) {
            // Normal operation: Slight trust recovery
            if (deviceTrustScores[_deviceId] < 100) deviceTrustScores[_deviceId] += 1;
        }

        emit LogAdded(_deviceId, _gatewayId, block.timestamp, _eventType);
    }

    function getLogCount() public view returns (uint256) {
        return logs.length;
    }

    function getLog(uint256 index) public view returns (
        uint256, string memory, string memory, uint256, string memory, string memory, string memory
    ) {
        Log memory l = logs[index];
        return (l.timestamp, l.deviceId, l.gatewayId, l.anomalyScore, l.dataHash, l.batchHash, l.eventType);
    }

    // ==================== CONTROL FUNCTIONS ====================
    
    /**
     * @dev Request control of a device. Checks trust score before approval.
     * @param _deviceId The device to control
     * @param _userId The user requesting control
     * @param _command The command to execute (e.g., "ON", "OFF")
     * @return commandId The ID of this command request
     * @return approved Whether the command was approved based on trust score
     * @return currentTrust The device's current trust score
     */
    function requestControl(
        string memory _deviceId,
        string memory _userId,
        string memory _command
    ) public returns (uint256 commandId, bool approved, uint256 currentTrust) {
        // Get current trust score (default to 100 for new devices)
        currentTrust = deviceTrustScores[_deviceId];
        if (currentTrust == 0) {
            currentTrust = 100;
            deviceTrustScores[_deviceId] = 100;
        }
        
        // Check if trust score is sufficient
        approved = currentTrust >= MIN_TRUST_SCORE;
        
        // Store the command regardless of approval (for audit)
        commands.push(ControlCommand({
            timestamp: block.timestamp,
            deviceId: _deviceId,
            userId: _userId,
            command: _command,
            approved: approved,
            executed: false,
            trustAtTime: currentTrust
        }));
        
        commandId = commands.length - 1;
        
        emit ControlRequested(commandId, _deviceId, _command, approved);
        
        return (commandId, approved, currentTrust);
    }

    /**
     * @dev Confirm that a command was executed by the device
     * @param _commandId The command ID to confirm
     * @param _success Whether the execution was successful
     */
    function confirmExecution(uint256 _commandId, bool _success) public {
        require(_commandId < commands.length, "Invalid command ID");
        require(commands[_commandId].approved, "Command was not approved");
        
        commands[_commandId].executed = _success;
        
        emit ControlExecuted(_commandId, _success);
    }

    function getCommandCount() public view returns (uint256) {
        return commands.length;
    }

    function getCommand(uint256 index) public view returns (
        uint256 timestamp,
        string memory deviceId,
        string memory userId,
        string memory command,
        bool approved,
        bool executed,
        uint256 trustAtTime
    ) {
        require(index < commands.length, "Invalid command index");
        ControlCommand memory c = commands[index];
        return (c.timestamp, c.deviceId, c.userId, c.command, c.approved, c.executed, c.trustAtTime);
    }
}
