const express = require('express');
const fs = require('fs');
const path = require('path');
const cors = require('cors');
const bodyParser = require('body-parser');
const axios = require('axios');

const app = express();
const PORT = 5002;
const LOG_FILE = path.join(__dirname, 'server_logs.json');      // Legacy JSON
const JSONL_FILE = path.join(__dirname, 'server_logs.jsonl');   // New JSONL format
const DEVICES_FILE = path.join(__dirname, 'devices.json');      // Device registry
const DEVICE_LOGS_DIR = path.join(__dirname, 'logs_per_device'); // Individual device logs

// Ensure logs directory exists
if (!fs.existsSync(DEVICE_LOGS_DIR)) {
    fs.mkdirSync(DEVICE_LOGS_DIR, { recursive: true });
}

// Heartbeat tracking
let deviceHeartbeats = {};
const HEARTBEAT_TIMEOUT = 45000; // 45 seconds

// Alarm State
let isAlarmActive = false;
let alarmReason = "";

// In-Memory Log Cache (for low-latency dashboard polling)
let recentLogs = [];
const MAX_CACHE_SIZE = 200;

// Trust Score Cache (for instant control)
let trustScoreCache = {};
const TRUST_CACHE_TTL = 300000; // 5 minutes (in ms)

// Middleware
app.use(cors());
app.use(bodyParser.json());

// Helper to read logs (from JSONL)
const readLogs = () => {
    // Try JSONL first (new format)
    if (fs.existsSync(JSONL_FILE)) {
        try {
            const data = fs.readFileSync(JSONL_FILE, 'utf8');
            const lines = data.trim().split('\n').filter(line => line.trim());
            return lines.map(line => {
                try {
                    return JSON.parse(line);
                } catch (e) {
                    return null;
                }
            }).filter(item => item !== null);
        } catch (err) {
            console.error('[SERVER] Error reading JSONL:', err.message);
        }
    }
    // Fallback to legacy JSON
    if (fs.existsSync(LOG_FILE)) {
        try {
            const data = fs.readFileSync(LOG_FILE, 'utf8');
            return JSON.parse(data);
        } catch (err) {
            return [];
        }
    }
    return [];
};

// Helper to append logs (Per-device JSON files + General JSONL)
const appendLogs = (logs, gatewayId, batchId, batchHash) => {
    const now = new Date();
    const dateStr = now.toISOString().split('T')[0];
    const timeStr = now.toTimeString().split(' ')[0];

    // 1. Original JSONL Append (General Audit) & Cache Update
    const lines = logs.map(log => {
        const enrichedLog = {
            ...log,
            gateway_id: gatewayId,
            batch_id: batchId,
            batch_hash: batchHash,
            server_received_at: Date.now()
        };

        // Update in-memory cache
        recentLogs.push(enrichedLog);
        if (recentLogs.length > MAX_CACHE_SIZE) {
            recentLogs.shift();
        }

        return JSON.stringify(enrichedLog);
    }).join('\n') + '\n';
    fs.appendFileSync(JSONL_FILE, lines);

    // 2. Per-Device JSON Array Storage (User's database request)
    logs.forEach(log => {
        if (!log.device_id) return;

        const deviceId = log.device_id;
        const filePath = path.join(DEVICE_LOGS_DIR, `${deviceId}.json`);

        const logEntry = {
            date: dateStr,
            time: timeStr,
            device_id: deviceId,
            score: log.anomaly_score || 1.0, // Use score from log if present
            values: {
                ...(log.sensors || {}),
                ...(log.system || {})
            },
            gateway_id: gatewayId,
            batch_hash: batchHash
        };

        try {
            let deviceLogs = [];
            if (fs.existsSync(filePath)) {
                const content = fs.readFileSync(filePath, 'utf8');
                deviceLogs = JSON.parse(content);
            }
            deviceLogs.push(logEntry);

            // Keep last 500 entries to prevent files growing too large
            if (deviceLogs.length > 500) {
                deviceLogs = deviceLogs.slice(-500);
            }

            fs.writeFileSync(filePath, JSON.stringify(deviceLogs, null, 2));
        } catch (err) {
            console.error(`[SERVER] Error writing device log for ${deviceId}:`, err.message);
        }
    });
};

// Helper to prune old logs (keep last N lines)
const pruneLogs = (maxLines = 1000) => {
    if (!fs.existsSync(JSONL_FILE)) return;

    try {
        const data = fs.readFileSync(JSONL_FILE, 'utf8');
        const lines = data.trim().split('\n').filter(line => line.trim());
        if (lines.length > maxLines) {
            const prunedLines = lines.slice(-maxLines);
            fs.writeFileSync(JSONL_FILE, prunedLines.join('\n') + '\n');
            console.log(`[SERVER] Pruned logs to ${maxLines} entries`);
        }
    } catch (err) {
        console.error('[SERVER] Error pruning logs:', err.message);
    }
};

// API: Receive Batch from Gateway
app.post('/api/logs', (req, res) => {
    const batch = req.body;

    if (!batch || !batch.logs) {
        return res.status(400).json({ error: "Invalid batch format" });
    }

    const gatewayId = batch.gateway_id || "unknown";
    const batchId = batch.batch_id || `batch_${Date.now()}`;
    const batchHash = batch.batch_hash || "NONE";

    console.log(`[SERVER] Received batch ${batchId} (${batch.batch_size} logs) from ${gatewayId}`);
    console.log(`[SERVER] Batch hash: ${batchHash.substring(0, 16)}...`);

    // Append to JSONL file (append-only, corruption-resistant)
    appendLogs(batch.logs, gatewayId, batchId, batchHash);

    // Prune if needed (every 10th batch)
    if (Math.random() < 0.1) {
        pruneLogs(1000);
    }

    // Track heartbeats for each device in the batch
    batch.logs.forEach(log => {
        if (log.device_id) {
            deviceHeartbeats[log.device_id] = Date.now();
        }
    });

    // Forward to ML Engine for real-time threat detection
    const ML_URL = "http://localhost:5001/predict/comprehensive";

    batch.logs.forEach(log => {
        axios.post(ML_URL, {
            ...log,
            batch_hash: batchHash,
            gateway_id: gatewayId
        }).catch(err => {
            console.error(`[SERVER] Failed to forward to ML Engine: ${err.message}`);
        });
    });

    // Phase 4: Log to Blockchain (Audit Trail)
    // We log the batch metadata to blockchain to create a permanent record of the transmission
    const firstLog = batch.logs[0] || {};
    const deviceId = firstLog.device_id || "unknown";

    callBlockchainPython('log_event', [
        deviceId,
        1.0,  // Normal score
        crypto_hash(JSON.stringify(batch.logs)), // Data hash
        batchHash,
        "BATCH_RECEIPT",
        gatewayId
    ]).then(result => {
        console.log(`[BLOCKCHAIN] Batch ${batchId} audit logged: ${result.tx_hash}`);
    }).catch(err => {
        console.error(`[BLOCKCHAIN] Failed to log batch audit: ${err.message}`);
    });

    res.json({ status: "success", count: batch.batch_size, batch_id: batchId });
});

// Helper for simple hashing
const crypto = require('crypto');
const crypto_hash = (data) => crypto.createHash('sha256').update(data).digest('hex');

// API: Security Alerts (from Gateway reject)
app.post('/api/alerts', (req, res) => {
    const alert = req.body;
    console.log(`[SECURITY] ALERT: ${alert.reason || 'Anomaly'} for device ${alert.device_id}`);

    // Also save to standard logs so dashboard picks it up
    const enrichedAlert = {
        ...alert,
        event_type: 'SECURITY_ALERT',
        server_received_at: Date.now()
    };
    fs.appendFileSync(JSONL_FILE, JSON.stringify(enrichedAlert) + '\n');

    // Update in-memory cache so Dashboard sees it immediately
    recentLogs.push(enrichedAlert);
    if (recentLogs.length > MAX_CACHE_SIZE) {
        recentLogs.shift();
    }

    // Log to blockchain as a security threat
    callBlockchainPython('log_event', [
        alert.device_id,
        0.0, // Zero trust for security threats
        crypto_hash(JSON.stringify(alert)),
        "GW_REJECTION",
        "SECURITY_ALERT",
        alert.gateway_id || "gateway_edge"
    ]).then(result => {
        console.log(`[BLOCKCHAIN] Security alert logged: ${result.tx_hash}`);
    }).catch(err => {
        console.error(`[BLOCKCHAIN] Failed to log security alert: ${err.message}`);
    });

    res.json({ status: "alert_received" });
});

// API: Base Station Alarm Control
app.post('/api/alarm/trigger', (req, res) => {
    const { reason } = req.body;
    isAlarmActive = true;
    alarmReason = reason || "Unspecified Anomaly";
    console.log('\n🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨');
    console.log(`🚨 BASE STATION ALARM ACTIVE: ${alarmReason} 🚨`);
    console.log('🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨\n');
    res.json({ status: "alarm_triggered", reason: alarmReason });
});

app.post('/api/alarm/reset', (req, res) => {
    isAlarmActive = false;
    alarmReason = "";
    console.log('✅ Base Station Alarm Reset.');
    res.json({ status: "alarm_reset" });
});

app.get('/api/alarm/status', (req, res) => {
    res.json({ active: isAlarmActive, reason: alarmReason });
});

// API: Get Logs (for Frontend/ML)
// API: Get Logs (for Frontend/ML)
app.get('/api/logs', (req, res) => {
    // FAST PATH: Serve from memory
    const limit = parseInt(req.query.limit) || 50;

    // If cache is empty (fresh start), try to populate it once
    if (recentLogs.length === 0) {
        recentLogs = readLogs().slice(-MAX_CACHE_SIZE);
    }

    const limitedLogs = recentLogs.slice(-limit);
    res.json(limitedLogs);
});

// API: Device Control - Blockchain-Secured (Optimized)
app.post('/api/control', async (req, res) => {
    const { device_id, command, user_id = "dashboard_user" } = req.body;

    // 1. Check Trust Cache (Instant Path)
    const now = Date.now();
    const cached = trustScoreCache[device_id];
    let isTrusted = false;
    let trustScore = 0;

    if (cached && (now - cached.timestamp < TRUST_CACHE_TTL)) {
        trustScore = cached.score;
        if (trustScore >= 30) {
            isTrusted = true;
            console.log(`[CONTROL] ⚡ Instant Cache Hit for ${device_id} (Score: ${trustScore})`);
        }
    }

    // 2. Logic Flow
    if (isTrusted) {
        // --- OPTIMISTIC FAST PATH ---

        // A. Send to Gateway Immediately
        try {
            await axios.post('http://localhost:8090/control', {
                device_id,
                command,
                command_id: `cmd_${now}_fast`
            });

            // B. Respond to Dashboard Immediately
            res.json({
                status: "command_forwarded_optimistic",
                device_id,
                command,
                note: "Executed instantly using cached trust score"
            });

            // C. Log to Blockchain Asynchronously (Background)
            callBlockchainPython('request_control', [device_id, user_id, command])
                .then(result => {
                    if (!result.approved) {
                        console.warn(`[CONTROL] ⚠ Async verification failed! Trust dropped to ${result.trust_score}`);
                        // In a real system, we might trigger an alarm or revoke cache here
                        delete trustScoreCache[device_id];
                    } else {
                        // Refresh cache with latest score
                        trustScoreCache[device_id] = { score: result.trust_score, timestamp: Date.now() };
                        console.log(`[BLOCKCHAIN] Async log confirmed. New Score: ${result.trust_score}`);
                    }
                })
                .catch(err => console.error(`[BLOCKCHAIN] Async logging failed: ${err.message}`));

        } catch (e) {
            console.error(`[CONTROL] Gateway unreachable: ${e.message}`);
            res.status(500).json({ error: "Gateway unreachable" });
        }

    } else {
        // --- SLOW VERIFICATION PATH (Cache Miss or Untrusted) ---
        console.log(`[CONTROL] 🐢 Cache miss/low score for ${device_id}, performing full blockchain verification...`);

        try {
            const blockchainResult = await callBlockchainPython('request_control', [device_id, user_id, command]);

            if (!blockchainResult.approved) {
                console.log(`[CONTROL] ⚠ Command REJECTED - Trust score too low: ${blockchainResult.trust_score}`);
                return res.status(403).json({
                    status: "rejected",
                    reason: "Trust score too low",
                    trust_score: blockchainResult.trust_score
                });
            }

            // Update Cache
            trustScoreCache[device_id] = { score: blockchainResult.trust_score, timestamp: Date.now() };
            console.log(`[CONTROL] ✓ Approved & Cached. Score: ${blockchainResult.trust_score}`);

            // Forward to Gateway
            await axios.post('http://localhost:8090/control', {
                device_id,
                command,
                command_id: blockchainResult.command_id
            });

            res.json({
                status: "command_forwarded_verified",
                device_id,
                command,
                blockchain: blockchainResult
            });

        } catch (e) {
            console.error(`[CONTROL] Verification failed: ${e.message}`);
            res.status(500).json({ error: "Verification process failed" });
        }
    }
});

// Initialize empty JSONL file if not exists
if (!fs.existsSync(JSONL_FILE) && !fs.existsSync(LOG_FILE)) {
    fs.writeFileSync(JSONL_FILE, '');
}

// ==================== BLOCKCHAIN API ENDPOINTS ====================

const { spawn } = require('child_process');

const blockchainQueue = [];
let isBlockchainActive = false;

const processBlockchainQueue = async () => {
    if (isBlockchainActive || blockchainQueue.length === 0) return;

    isBlockchainActive = true;
    const { functionName, args, resolve, reject } = blockchainQueue.shift();

    try {
        const result = await executeBlockchainPython(functionName, args);
        resolve(result);
    } catch (err) {
        reject(err);
    } finally {
        isBlockchainActive = false;
        // Process next in queue
        processBlockchainQueue();
    }
};

const callBlockchainPython = (functionName, args = []) => {
    return new Promise((resolve, reject) => {
        blockchainQueue.push({ functionName, args, resolve, reject });
        processBlockchainQueue();
    });
};

// Helper to call Python blockchain functions (using the CLI handler in the script)
const executeBlockchainPython = (functionName, args = []) => {
    return new Promise((resolve, reject) => {
        const baseDir = path.join(__dirname, '..');
        const blockchainDir = path.join(baseDir, 'blockchain');
        const scriptPath = path.join(blockchainDir, 'deploy_and_interact.py');

        // Robust Python Detection: Prefer local .venv if it exists
        const venvPython = process.platform === 'win32'
            ? path.join(baseDir, '.venv', 'Scripts', 'python.exe')
            : path.join(baseDir, '.venv', 'bin', 'python');

        const pythonExe = fs.existsSync(venvPython) ? venvPython : 'python';

        // Prepare arguments: [scriptPath, functionName, ...args]
        // Note: args need to be converted to strings for CLI
        const pythonArgs = [scriptPath, functionName, ...args.map(a => String(a))];

        const python = spawn(pythonExe, pythonArgs, {
            cwd: blockchainDir,
            env: { ...process.env }
        });

        let output = '';
        let error = '';

        // Added 15-second timeout to prevent zombie processes
        const timeout = setTimeout(() => {
            python.kill();
            reject(new Error(`Python process timed out after 15s (${functionName})`));
        }, 15000);

        python.stdout.on('data', (data) => {
            output += data.toString();
        });

        python.stderr.on('data', (data) => {
            error += data.toString();
        });

        python.on('close', (code) => {
            clearTimeout(timeout);
            // isBlockchainActive handled by processBlockchainQueue wrap
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

// API: Get command history for a device
app.get('/api/control/history/:deviceId', async (req, res) => {
    try {
        const deviceId = req.params.deviceId;
        const limit = parseInt(req.query.limit) || 50;
        const history = await callBlockchainPython('get_command_history', [deviceId, limit]);
        res.json(history);
    } catch (error) {
        console.error('[BLOCKCHAIN] Error getting command history:', error.message);
        res.status(500).json({ error: error.message });
    }
});

// API: Get all command history (no device filter)
app.get('/api/control/history', async (req, res) => {
    try {
        const limit = parseInt(req.query.limit) || 50;
        const history = await callBlockchainPython('get_command_history', [null, limit]);
        res.json(history);
    } catch (error) {
        console.error('[BLOCKCHAIN] Error getting command history:', error.message);
        res.status(500).json({ error: error.message });
    }
});

// ==================== DEVICE REGISTRY API ====================

app.get('/api/devices', (req, res) => {
    if (fs.existsSync(DEVICES_FILE)) {
        res.json(JSON.parse(fs.readFileSync(DEVICES_FILE, 'utf8')));
    } else {
        res.json([]);
    }
});

// Real-time device verification for gateway hybrid auth
app.get('/api/devices/verify/:deviceId/:userId', (req, res) => {
    const { deviceId, userId } = req.params;

    if (!fs.existsSync(DEVICES_FILE)) {
        return res.json({ authorized: false, reason: "No device registry" });
    }

    const devices = JSON.parse(fs.readFileSync(DEVICES_FILE, 'utf8'));

    // Check exact match first
    let device = devices.find(d => d.id === deviceId);

    // Check base ID match (e.g., esp8266_env_01 for esp8266_env_01_d969)
    if (!device) {
        const baseId = deviceId.split("_").slice(0, 3).join("_");
        device = devices.find(d => d.id === baseId);
    }

    if (!device) {
        return res.json({ authorized: false, reason: "Device not registered" });
    }

    if (device.user_id !== userId) {
        return res.json({ authorized: false, reason: "User not authorized for device" });
    }

    res.json({ authorized: true, device: device });
});

app.post('/api/devices', async (req, res) => {
    const newDevice = req.body;
    let devices = [];
    if (fs.existsSync(DEVICES_FILE)) {
        devices = JSON.parse(fs.readFileSync(DEVICES_FILE, 'utf8'));
    }

    // Check if device already exists
    if (devices.find(d => d.id === newDevice.id)) {
        return res.status(400).json({ error: "Device ID already exists" });
    }

    devices.push(newDevice);
    fs.writeFileSync(DEVICES_FILE, JSON.stringify(devices, null, 2));

    // Log to blockchain as a security event (Registration)
    callBlockchainPython('register_device', [
        newDevice.id,
        "IOT_SENSOR",
        "server_admin"
    ]).then(result => {
        console.log(`[BLOCKCHAIN] Device ${newDevice.id} registered on-chain: ${result.tx_hash}`);

        // Also log the initial registration event
        callBlockchainPython('log_event', [
            newDevice.id,
            1.0,
            crypto_hash(JSON.stringify(newDevice)),
            "NEW_DEVICE_REG",
            "REGISTRATION",
            "server_admin"
        ]);
    });

    // Notify Gateway to sync immediately
    try {
        await axios.post('http://localhost:8090/api/sync', { reason: "NEW_DEVICE", device_id: newDevice.id });
        console.log('[GATEWAY] Notified to sync registry');
    } catch (e) {
        console.warn('[GATEWAY] Notification failed (unreachable?):', e.message);
    }

    res.json({ status: "success", device: newDevice });
});

// ==================== SYSTEM HEALTH MONITOR ====================

app.get('/api/health', (req, res) => {
    const now = Date.now();
    const health = Object.entries(deviceHeartbeats).map(([id, lastSeen]) => ({
        device_id: id,
        last_seen: lastSeen,
        status: (now - lastSeen < HEARTBEAT_TIMEOUT) ? "online" : "stale",
        seconds_ago: Math.floor((now - lastSeen) / 1000)
    }));
    res.json(health);
});

// Periodic check for dead devices
setInterval(() => {
    const now = Date.now();
    Object.entries(deviceHeartbeats).forEach(([id, lastSeen]) => {
        if (now - lastSeen > HEARTBEAT_TIMEOUT && now - lastSeen < HEARTBEAT_TIMEOUT + 5000) {
            console.log(`[HEALTH] ALERT: Device ${id} has gone STALE!`);
            // Log this to blockchain!
            callBlockchainPython('log_event', [
                id, 0.5, crypto_hash(id + now), "HEARTBEAT_LOST", "HEALTH_ALERT", "server_monitor"
            ]).catch(() => { });
        }
    });
}, 5000);

app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log('Blockchain API endpoints:');
    console.log('  GET /api/blockchain/logs - Get all anomaly logs');
    console.log('  GET /api/blockchain/count - Get log count');
    console.log('  GET /api/blockchain/trust/:deviceId - Get device trust score');
    console.log('  POST /api/control - Blockchain-secured device control');
    console.log('  GET /api/control/history/:deviceId - Get command history');
    console.log('Device Registry endpoints:');
    console.log('  GET /api/devices - List devices');
    console.log('  POST /api/devices - Add device');
});
