// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DeviceLog {
    
    struct Log {
        uint256 timestamp;
        string deviceId;
        uint256 anomalyScore; // Scaled by 100
        string dataHash;      // Hash of specific log data
        string batchHash;     // NEW: Hash of the entire batch from Gateway
        string eventType;     // "ANOMALY", etc.
    }

    mapping(string => uint256) public deviceTrustScores;
    Log[] public logs;

    event LogAdded(string indexed deviceId, uint256 timestamp, string eventType, string batchHash);

    constructor() {}

    function addLog(
        string memory _deviceId, 
        uint256 _anomalyScore, 
        string memory _dataHash, 
        string memory _batchHash,
        string memory _eventType
    ) public {
        logs.push(Log({
            timestamp: block.timestamp,
            deviceId: _deviceId,
            anomalyScore: _anomalyScore,
            dataHash: _dataHash,
            batchHash: _batchHash,
            eventType: _eventType
        }));

        // Simple Trust Score Logic
        if (deviceTrustScores[_deviceId] == 0) {
            deviceTrustScores[_deviceId] = 100;
        }

        // Decrease trust if anomaly or suspicious activity
        if (keccak256(bytes(_eventType)) != keccak256(bytes("HEARTBEAT"))) {
             if (deviceTrustScores[_deviceId] > 5) {
                deviceTrustScores[_deviceId] -= 5;
            }
        } else {
             if (deviceTrustScores[_deviceId] < 100) {
                deviceTrustScores[_deviceId] += 1;
            }
        }

        emit LogAdded(_deviceId, block.timestamp, _eventType, _batchHash);
    }

    function getLogCount() public view returns (uint256) {
        return logs.length;
    }

    function getLog(uint256 index) public view returns (
        uint256, string memory, uint256, string memory, string memory, string memory
    ) {
        Log memory l = logs[index];
        return (l.timestamp, l.deviceId, l.anomalyScore, l.dataHash, l.batchHash, l.eventType);
    }
}
