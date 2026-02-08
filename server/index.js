const express = require('express');
const fs = require('fs');
const path = require('path');
const cors = require('cors');
const bodyParser = require('body-parser');
const axios = require('axios');

const app = express();
const PORT = 5002;
const LOG_FILE = path.join(__dirname, 'server_logs.json');

// Middleware
app.use(cors());
app.use(bodyParser.json());

// Helper to read logs
const readLogs = () => {
    if (!fs.existsSync(LOG_FILE)) {
        return [];
    }
    const data = fs.readFileSync(LOG_FILE, 'utf8');
    try {
        return JSON.parse(data);
    } catch (err) {
        return [];
    }
};

// Helper to write logs
const writeLogs = (logs) => {
    fs.writeFileSync(LOG_FILE, JSON.stringify(logs, null, 2));
};

// API: Receive Batch from Gateway
app.post('/api/logs', (req, res) => {
    const batch = req.body;

    if (!batch || !batch.logs) {
        return res.status(400).json({ error: "Invalid batch format" });
    }

    console.log(`[SERVER] Received batch of ${batch.batch_size} logs from ${batch.gateway_id}`);

    // Store in JSON file
    const currentLogs = readLogs();

    // Add processed timestamp to each log
    const processedLogs = batch.logs.map(log => ({
        ...log,
        server_received_at: Date.now()
    }));

    const updatedLogs = [...currentLogs, ...processedLogs];

    // Limit history to last 1000 logs to prevent huge file for this demo
    const prunedLogs = updatedLogs.slice(-1000);

    writeLogs(prunedLogs);

    // Forward to ML Engine for real-time threat detection
    const ML_URL = "http://localhost:5001/predict";
    const batchHash = batch.batch_hash || "NONE";

    processedLogs.forEach(log => {
        // Include the batch_hash in the prediction request for blockchain traceability
        axios.post(ML_URL, { ...log, batch_hash: batchHash }).catch(err => {
            console.error(`[SERVER] Failed to forward to ML Engine: ${err.message}`);
        });
    });

    res.json({ status: "success", count: batch.batch_size });
});

// API: Get Logs (for Frontend/ML)
app.get('/api/logs', (req, res) => {
    const logs = readLogs();
    // Support limit parameter to reduce payload for dashboard
    const limit = parseInt(req.query.limit) || logs.length;
    const limitedLogs = logs.slice(-limit); // Return most recent logs
    res.json(limitedLogs);
});

// API: Device Control - Forward to Gateway
app.post('/api/control', async (req, res) => {
    const { device_id, command } = req.body;
    console.log(`[CONTROL] Forwarding command '${command}' to ${device_id} via Gateway`);

    try {
        // Forward to Gateway
        const axios = require('axios');
        const response = await axios.post('http://localhost:8080/control', {
            device_id,
            command
        });
        res.json({ status: "command_forwarded", device_id, command, gateway_response: response.data });
    } catch (error) {
        console.error(`[CONTROL] Failed to forward command: ${error.message}`);
        res.status(500).json({ status: "failed", error: error.message });
    }
});

// Initialize empty log file if not exists
if (!fs.existsSync(LOG_FILE)) {
    writeLogs([]);
}

// ==================== BLOCKCHAIN API ENDPOINTS ====================

const { spawn } = require('child_process');

let isBlockchainActive = false;

// Helper to call Python blockchain functions
const callBlockchainPython = (functionName, args = []) => {
    if (isBlockchainActive) {
        console.warn(`[SERVER] Blockchain operation '${functionName}' rejected - dynamic process already running`);
        return Promise.reject(new Error('Blockchain busy'));
    }

    isBlockchainActive = true;
    return new Promise((resolve, reject) => {
        const pythonScript = `
import sys
import os
sys.path.insert(0, r'${path.join(__dirname, '..', 'blockchain').replace(/\\/g, '\\\\')}')
import json
from deploy_and_interact import ${functionName}
try:
    result = ${functionName}(${args.map(a => typeof a === 'string' ? `"${a}"` : a).join(', ')})
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({"error": str(e)}))
`;
        const python = spawn('python', ['-c', pythonScript]);
        let output = '';
        let error = '';

        // Added 10-second timeout to prevent zombie processes
        const timeout = setTimeout(() => {
            python.kill();
            isBlockchainActive = false;
            reject(new Error(`Python process timed out after 10s (${functionName})`));
        }, 10000);

        python.stdout.on('data', (data) => {
            output += data.toString();
        });

        python.stderr.on('data', (data) => {
            error += data.toString();
        });

        python.on('close', (code) => {
            clearTimeout(timeout);
            isBlockchainActive = false;
            if (code === 0) {
                try {
                    const parsed = JSON.parse(output.trim());
                    if (parsed && parsed.error) {
                        reject(new Error(parsed.error));
                    } else {
                        resolve(parsed);
                    }
                } catch (e) {
                    resolve(output.trim());
                }
            } else {
                reject(new Error(error || 'Python script failed'));
            }
        });
    });
};

// API: Get all blockchain logs
app.get('/api/blockchain/logs', async (req, res) => {
    try {
        const limit = parseInt(req.query.limit) || 100;
        const logs = await callBlockchainPython('get_all_logs', [limit]);
        res.json(logs);
    } catch (error) {
        console.error('[BLOCKCHAIN] Error getting logs:', error.message);
        res.status(500).json({ error: error.message });
    }
});

// API: Get blockchain log count
app.get('/api/blockchain/count', async (req, res) => {
    try {
        const count = await callBlockchainPython('get_log_count');
        res.json({ count: count });
    } catch (error) {
        console.error('[BLOCKCHAIN] Error getting count:', error.message);
        res.status(500).json({ error: error.message });
    }
});

// API: Get trust score for a device
app.get('/api/blockchain/trust/:deviceId', async (req, res) => {
    try {
        const deviceId = req.params.deviceId;
        const score = await callBlockchainPython('get_trust_score', [deviceId]);
        res.json({ device_id: deviceId, trust_score: score });
    } catch (error) {
        console.error('[BLOCKCHAIN] Error getting trust score:', error.message);
        res.status(500).json({ error: error.message });
    }
});

app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log('Blockchain API endpoints:');
    console.log('  GET /api/blockchain/logs - Get all anomaly logs');
    console.log('  GET /api/blockchain/count - Get log count');
    console.log('  GET /api/blockchain/trust/:deviceId - Get device trust score');
});
