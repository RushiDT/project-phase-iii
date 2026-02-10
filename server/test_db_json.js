const axios = require('axios');

const testLogs = {
    gateway_id: "test_gateway",
    batch_id: "test_batch_123",
    batch_size: 2,
    batch_hash: "ABC123DEF456",
    logs: [
        {
            device_id: "device_test_001",
            sensors: { temperature: 22.5, humidity: 45 },
            system: { cpu_usage: 12, battery_level: 98 },
            anomaly_score: 0.99
        },
        {
            device_id: "device_test_002",
            sensors: { temperature: 24.1, humidity: 48 },
            system: { cpu_usage: 15, battery_level: 95 },
            anomaly_score: 0.98
        }
    ]
};

async function runTest() {
    try {
        console.log("Sending test logs to server...");
        const response = await axios.post("http://localhost:5002/api/logs", testLogs);
        console.log("Response:", response.data);
        console.log("Check server/logs_per_device/ for device_test_001.json and device_test_002.json");
    } catch (error) {
        console.error("Test failed:", error.message);
    }
}

runTest();
