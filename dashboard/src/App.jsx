import { useState, useEffect, useMemo, useRef } from 'react'
import axios from 'axios'
import { io } from 'socket.io-client'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, AreaChart, Area } from 'recharts'
import { Lightbulb, Thermometer, Droplets, Bell, Power, Activity, Plus, Settings, Wifi, Shield, Lock, Fingerprint, Database, AlertCircle, Heart, UploadCloud, Download } from 'lucide-react'
import './App.css'

const API_URL = 'http://localhost:5002/api'
const SOCKET_URL = 'http://localhost:5002'

// Initialize socket exactly once
let socket = io(SOCKET_URL, {
  reconnectionDelayMax: 10000,
  autoConnect: false // Connect manually after getting token
});

function App() {
  const [activeTab, setActiveTab] = useState('esp32')
  const [token, setToken] = useState(localStorage.getItem('jwt_token') || null)
  const [logs, setLogs] = useState([])
  const [blockchainLogs, setBlockchainLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [devices, setDevices] = useState([])
  const [securityAlerts, setSecurityAlerts] = useState([])
  const [systemHealth, setSystemHealth] = useState([])
  const [trustScores, setTrustScores] = useState({})
  const [alarmStatus, setAlarmStatus] = useState({ active: false, reason: '' })

  // Device states with advanced telemetry
  const [esp32State, setEsp32State] = useState({
    light: false, deviceOn: true, motionEvents: [],
    power: 0, network: 0, cpu: 0
  })
  const [esp8266State, setEsp8266State] = useState({
    alarm: false, deviceOn: true, temp: 25, humidity: 50,
    vibration: 0, power: 0, network: 0, cpu: 0
  })

  // New device form
  const [newDevice, setNewDevice] = useState({ id: '', type: 'esp32', userId: '' })

  // Ref to track last command time to prevent UI flickering (telemetry vs optimistic state)
  const lastCommandRef = useRef(0);

  // --- WebSocket Real-Time Integration ---
  useEffect(() => {
    socket.on('initial_state', (state) => {
      setAlarmStatus({ active: state.alarm_active, reason: state.alarm_reason });
    });

    socket.on('new_log', (newLog) => {
      setLogs((prevLogs) => {
        // Keep logs sorted and bound to prevent massive memory usage
        const updated = [newLog, ...prevLogs].sort((a, b) => b.timestamp - a.timestamp);
        return updated.slice(0, 500);
      });

      // Update Device States dynamically when new data arrives via WS
      const now = Date.now();
      const COMMAND_LOCKOUT_MS = 10000;

      if (newLog.device_id?.startsWith('esp32') && newLog.sensors && (now - lastCommandRef.current > COMMAND_LOCKOUT_MS)) {
        setEsp32State(prev => {
          let updatedMotion = prev.motionEvents;
          if (newLog.sensors.motion) {
            updatedMotion = [{ time: new Date(newLog.timestamp * 1000).toLocaleTimeString(), timestamp: newLog.timestamp }, ...updatedMotion].slice(0, 20);
          }
          return {
            ...prev,
            light: newLog.sensors.light_state !== undefined ? newLog.sensors.light_state : prev.light,
            motionEvents: updatedMotion,
            power: newLog.system?.power_watts || prev.power,
            network: newLog.system?.network_activity || prev.network,
            cpu: newLog.system?.cpu_usage || prev.cpu,
            deviceOn: true
          }
        });
      }

      if (newLog.device_id?.startsWith('esp8266') && newLog.sensors) {
        setEsp8266State(prev => ({
          ...prev,
          temp: newLog.sensors.temperature || prev.temp,
          humidity: newLog.sensors.humidity || prev.humidity,
          alarm: newLog.sensors.alarm_enabled !== undefined ? newLog.sensors.alarm_enabled : prev.alarm,
          vibration: newLog.sensors.vibration || prev.vibration,
          power: newLog.system?.power_watts || prev.power,
          network: newLog.system?.network_activity || prev.network,
          cpu: newLog.system?.cpu_usage || prev.cpu,
          deviceOn: true
        }));
      }
    });

    socket.on('new_alert', (newAlert) => {
      setLogs(prev => [newAlert, ...prev].sort((a, b) => b.timestamp - a.timestamp).slice(0, 500));
    });

    socket.on('alarm_state_change', (state) => {
      setAlarmStatus({ active: state.active, reason: state.reason });
    });

    return () => {
      socket.off('initial_state');
      socket.off('new_log');
      socket.off('new_alert');
      socket.off('alarm_state_change');
    };
  }, []);

  // Initial Fetch (No more aggressive polling thanks to WebSockets)
  useEffect(() => {
    let cancelled = false;

    const fetchInitialData = async () => {
      try {
        // --- 1. Authenticaton Phase ---
        let currentToken = localStorage.getItem('jwt_token');
        if (!currentToken) {
          const authRes = await axios.post(`${API_URL}/login`, { username: 'admin', password: 'admin123' });
          currentToken = authRes.data.token;
          localStorage.setItem('jwt_token', currentToken);
          setToken(currentToken);
        }

        // Configure global Axios token
        axios.defaults.headers.common['Authorization'] = `Bearer ${currentToken}`;

        // Configure socket token and connect
        socket.auth = { token: currentToken };
        if (!socket.connected) socket.connect();

        // --- 2. Data Fetch Phase ---
        const results = await Promise.allSettled([
          axios.get(`${API_URL}/logs`),
          axios.get(`${API_URL}/devices`),
          axios.get(`${API_URL}/blockchain/logs`),
          axios.get(`${API_URL}/health`),
          axios.get(`${API_URL}/alarm/status`)
        ])

        const [logsRes, devRes, bcRes, healthRes, alarmRes] = results;

        const data = logsRes.status === 'fulfilled' && Array.isArray(logsRes.value.data) ? logsRes.value.data : [];
        const sortedData = data.sort((a, b) => b.timestamp - a.timestamp);
        if (!cancelled) setLogs(sortedData);

        if (!cancelled) setBlockchainLogs(bcRes.status === 'fulfilled' && Array.isArray(bcRes.value.data) ? bcRes.value.data : []);
        if (!cancelled) setSystemHealth(healthRes.status === 'fulfilled' && Array.isArray(healthRes.value.data) ? healthRes.value.data : []);
        if (alarmRes.status === 'fulfilled' && !cancelled) setAlarmStatus(alarmRes.value.data);

        let deviceList = [];
        if (devRes.status === 'fulfilled' && Array.isArray(devRes.value.data) && devRes.value.data.length > 0) {
          deviceList = devRes.value.data;
        } else {
          const uniqueIds = [...new Set(sortedData.map(l => l.device_id).filter(id => id))];
          deviceList = uniqueIds.map(id => ({
            id, type: id.includes('esp8266') ? 'esp8266' : 'esp32', status: 'discovered'
          }));
        }

        const coreDevices = [
          { id: 'esp32_sec_01', type: 'esp32', status: 'active', location: 'entrance' },
          { id: 'esp8266_env_01', type: 'esp8266', status: 'active', location: 'balcony' }
        ];

        coreDevices.forEach(coreDev => {
          if (!deviceList.find(d => d.id === coreDev.id)) {
            deviceList.push(coreDev);
          }
        });

        if (!cancelled) setDevices(deviceList);
        if (!cancelled) setLoading(false);
      } catch (e) {
        console.error('Initial fetch error:', e);
        // If 403/401, token might be expired. Clear it.
        if (e.response && (e.response.status === 401 || e.response.status === 403)) {
          localStorage.removeItem('jwt_token');
          setToken(null);
        }
        if (!cancelled) setLoading(false);
      }
    }

    fetchInitialData()
    return () => { cancelled = true; }
  }, [])

  // Secondary Slow Polling for Health/Blockchain (which doesn't stream yet)
  useEffect(() => {
    const fetchSecondary = async () => {
      try {
        const hRes = await axios.get(`${API_URL}/health`);
        setSystemHealth(hRes.data);
        const bRes = await axios.get(`${API_URL}/blockchain/logs`);
        setBlockchainLogs(bRes.data);
        const dRes = await axios.get(`${API_URL}/devices`);
        setDevices(prev => {
          // Merge arrays prioritizing new fetch
          const fetchedIds = dRes.data.map(d => d.id);
          const preserved = prev.filter(d => !fetchedIds.includes(d.id));
          return [...preserved, ...dRes.data];
        });
      } catch (e) { }
    }
    const secInterval = setInterval(fetchSecondary, 10000);
    return () => clearInterval(secInterval);
  }, []);

  // Fetch trust scores on a separate, slower interval (every 30s — scores rarely change)
  useEffect(() => {
    const fetchTrustScores = async () => {
      if (devices.length === 0) return;
      const scores = {};
      for (const dev of devices) {
        try {
          const trustRes = await axios.get(`${API_URL}/blockchain/trust/${dev.id}`, { timeout: 3000 });
          scores[dev.id] = trustRes.data.trust_score;
        } catch (e) {
          scores[dev.id] = 'N/A';
        }
      }
      setTrustScores(prev => ({ ...prev, ...scores }));
    };

    fetchTrustScores();
    const trustInterval = setInterval(fetchTrustScores, 30000);
    return () => clearInterval(trustInterval);
  }, [devices.length])

  // Send control command
  const sendCommand = async (deviceId, command) => {
    // Phase 7: Guard against commanding quarantined devices
    const target = devices.find(d => d.id === deviceId);
    if (target && target.quarantined) {
      alert(`⚠️ ERROR: Device ${deviceId} is currently QUARANTINED due to suspected compromise. Revive it via the Device Manager first.`);
      return;
    }

    try {
      console.log(`[DASHBOARD] Sending ${command} to ${deviceId}...`);
      const response = await axios.post(`${API_URL}/control`, { device_id: deviceId, command })
      console.log(`[DASHBOARD] SUCCESS:`, response.data);
      alert(`Command ${command} sent successfully!`);
    } catch (e) {
      console.error('[DASHBOARD] Control error:', e.response?.data || e.message);
      alert(`Failed to send ${command}: ${e.response?.data?.reason || e.message}`);
    }
  }

  // ESP32 controls
  const toggleLight = () => {
    // Priority: specifically find 'esp32_sec_01', then any other esp32
    const esp32Devices = devices.filter(d => d.type === 'esp32' || d.id.startsWith('esp32'));
    const targeted = esp32Devices.find(d => d.id === 'esp32_sec_01') || esp32Devices[0];
    const targetId = targeted ? targeted.id : '';

    if (!targetId) {
      alert(`No active ESP32 device found. Devices found: ${devices.map(d => d.id).join(', ')}`);
      return;
    }

    const cmd = esp32State.light ? 'LIGHT_OFF' : 'LIGHT_ON'
    console.log(`[DASHBOARD] Toggling Light for ${targetId}: current state ${esp32State.light}`);

    // Set lock to prevent telemetry from overwriting our optimistic update for a few seconds
    lastCommandRef.current = Date.now();

    sendCommand(targetId, cmd)
    setEsp32State(prev => ({ ...prev, light: !prev.light }))
  }

  const toggleEsp32Power = () => {
    const esp32Devices = devices.filter(d => d.type === 'esp32' || d.id.startsWith('esp32'));
    const targeted = esp32Devices.find(d => d.id === 'esp32_sec_01') || esp32Devices[0];
    const targetId = targeted ? targeted.id : '';

    if (!targetId) {
      alert("No active ESP32 device found to control.");
      return;
    }

    const cmd = esp32State.deviceOn ? 'DEVICE_OFF' : 'DEVICE_ON'
    sendCommand(targetId, cmd)
    setEsp32State(prev => ({ ...prev, deviceOn: !prev.deviceOn }))
  }

  // ESP8266 controls
  const toggleAlarm = () => {
    const esp8266Devices = devices.filter(d => d.type === 'esp8266' || d.id.startsWith('esp8266'));
    const targeted = esp8266Devices.find(d => d.id === 'esp8266_env_01') || esp8266Devices[0];
    const targetId = targeted ? targeted.id : '';

    if (!targetId) {
      alert("No active ESP8266 device found to control.");
      return;
    }

    const cmd = esp8266State.alarm ? 'ALARM_OFF' : 'ALARM_ON'
    sendCommand(targetId, cmd)
    setEsp8266State(prev => ({ ...prev, alarm: !prev.alarm }))
  }

  const toggleEsp8266Power = () => {
    const esp8266Devices = devices.filter(d => d.type === 'esp8266' || d.id.startsWith('esp8266'));
    const targeted = esp8266Devices.find(d => d.id === 'esp8266_env_01') || esp8266Devices[0];
    const targetId = targeted ? targeted.id : '';

    if (!targetId) {
      alert("No active ESP8266 device found to control.");
      return;
    }

    const cmd = esp8266State.deviceOn ? 'DEVICE_OFF' : 'DEVICE_ON'
    sendCommand(targetId, cmd)
    setEsp8266State(prev => ({ ...prev, deviceOn: !prev.deviceOn }))
  }

  // Temperature history for chart
  const tempHistory = useMemo(() => {
    return logs
      .filter(l => l.device_id?.startsWith('esp8266'))
      .slice(0, 20)
      .reverse()
      .map(l => ({
        time: new Date(l.timestamp * 1000).toLocaleTimeString().slice(0, 5),
        temp: l.sensors?.temperature || 0,
        humidity: l.sensors?.humidity || 0
      }))
  }, [logs])

  // Motion timeline for chart
  const motionTimeline = useMemo(() => {
    const counts = {}
    logs
      .filter(l => l.device_id?.startsWith('esp32') && l.sensors?.motion)
      .forEach(l => {
        const minute = new Date(l.timestamp * 1000).toLocaleTimeString().slice(0, 5)
        counts[minute] = (counts[minute] || 0) + 1
      })
    return Object.entries(counts).map(([time, count]) => ({ time, count })).slice(-10)
  }, [logs])

  // --- Historical Analytics Aggregation ---
  const historicalMetrics = useMemo(() => {
    if (!logs.length) return [];

    // Group logs by Day (or hour if not enough days) to show trends
    const grouped = {};

    logs.forEach(log => {
      if (!log.timestamp) return;
      const date = new Date(log.timestamp * 1000);
      // Grouping by Date string (e.g., "Feb 23")
      const dayKey = `${date.toLocaleString('default', { month: 'short' })} ${date.getDate()}`;

      if (!grouped[dayKey]) {
        grouped[dayKey] = { day: dayKey, avgTemp: 0, avgHum: 0, avgPower: 0, count: 0, anomalies: 0 };
      }

      grouped[dayKey].count += 1;

      if (log.sensors) {
        if (log.sensors.temperature) grouped[dayKey].avgTemp += log.sensors.temperature;
        if (log.sensors.humidity) grouped[dayKey].avgHum += log.sensors.humidity;
      }
      if (log.system?.power_watts) grouped[dayKey].avgPower += log.system.power_watts;

      if (log.anomaly_score < -0.1 || log.event_type === "SECURITY_ALERT") {
        grouped[dayKey].anomalies += 1;
      }
    });

    // Calculate Averages and convert to array
    return Object.values(grouped).map(group => ({
      day: group.day,
      temp: group.count > 0 ? (group.avgTemp / group.count).toFixed(1) : 0,
      humidity: group.count > 0 ? (group.avgHum / group.count).toFixed(1) : 0,
      power: group.count > 0 ? (group.avgPower / group.count).toFixed(1) : 0,
      anomalies: group.anomalies
    })).reverse(); // Latest data last for chart progression
  }, [logs]);

  // Security Events Feed
  const securityEvents = useMemo(() => {
    return logs
      .filter(l => l.event_type === 'SECURITY_ALERT' || l.reason?.includes('Anomaly'))
      .slice(0, 5);
  }, [logs])

  // Add new device
  const addDevice = async () => {
    if (!newDevice.id || !newDevice.userId) return
    try {
      await axios.post(`${API_URL}/devices`, newDevice)
      setDevices([...devices, newDevice])
      setNewDevice({ id: '', type: 'esp32', userId: '' })
      alert('Device added successfully!')
    } catch (e) {
      alert('Failed to add device')
    }
  }

  const resetAlarm = async () => {
    try {
      await axios.post(`${API_URL}/alarm/reset`)
      setAlarmStatus({ active: false, reason: '' })
    } catch (e) {
      console.error('Alarm reset error:', e)
    }
  }

  // Phase 6: Trigger OTA Update
  const triggerOtaUpdate = async (deviceId, version = 'v2.0.0') => {
    if (!window.confirm(`Are you sure you want to push Firmware ${version} to ${deviceId}? This will reboot the module.`)) return;

    try {
      console.log(`[OTA] Requesting Update to ${version} for ${deviceId}`);
      await axios.post(`${API_URL}/devices/${deviceId}/update`, { version });
      alert(`OTA Update Initiated! Device ${deviceId} is downloading ${version}...`);
    } catch (e) {
      alert(`OTA Request Failed: ${e.response?.data?.error || e.message}`);
    }
  };

  // Phase 7: Un-Quarantine Device
  const unquarantineDevice = async (deviceId) => {
    if (!window.confirm(`SECURITY WARNING: Are you sure you want to revive ${deviceId}? This will reset its ML trust score to 100% and restore network access.`)) return;

    try {
      await axios.post(`${API_URL}/devices/${deviceId}/unquarantine`);
      alert(`✅ Device ${deviceId} trust restored. Re-joining network...`);
      // It will auto-refresh via fetchSecondary loop
    } catch (e) {
      alert(`Failed to un-quarantine: ${e.response?.data?.error || e.message}`);
    }
  };

  // Phase 8: Export Data functionality
  const downloadAsJSON = () => {
    const dataStr = JSON.stringify(logs, null, 2);
    const blob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `iot_security_logs_${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadAsCSV = () => {
    if (logs.length === 0) return;

    // Flatten the objects for CSV
    const flattenedLogs = logs.map(log => {
      return {
        timestamp: new Date(log.timestamp * 1000).toISOString(),
        device_id: log.device_id,
        user_id: log.user_id || 'system',
        anomaly_score: log.anomaly_score !== undefined ? log.anomaly_score : 'N/A',
        event_type: log.event_type || 'TELEMETRY',

        // Sensors (handling varying fields)
        s_temperature: log.sensors?.temperature !== undefined ? log.sensors.temperature : '',
        s_humidity: log.sensors?.humidity !== undefined ? log.sensors.humidity : '',
        s_motion: log.sensors?.motion !== undefined ? log.sensors.motion : '',
        s_light: log.sensors?.light_state !== undefined ? log.sensors.light_state : '',
        s_vibration: log.sensors?.vibration !== undefined ? log.sensors.vibration : '',

        // System
        sys_power: log.system?.power_watts !== undefined ? log.system.power_watts : '',
        sys_cpu: log.system?.cpu_usage !== undefined ? log.system.cpu_usage : '',
        sys_network: log.system?.network_activity !== undefined ? log.system.network_activity : ''
      };
    });

    const headers = Object.keys(flattenedLogs[0]);
    const csvContent = [
      headers.join(','),
      ...flattenedLogs.map(row => headers.map(fieldName => JSON.stringify(row[fieldName] ?? '')).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `iot_telemetry_export_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return <div className="loading">Loading IoT Dashboard...</div>
  }

  return (
    <div className="app">
      <header className="header">
        <div className="title-area">
          <h1>🏠 IoT Smart Home Dashboard</h1>
          <p className="subtitle">Secure Device Ecosystem v2.0</p>
        </div>
        <div className="status-bar">
          <div className="blockchain-badge">
            <Lock size={14} className="icon-gold" />
            <span>On-Chain Verified</span>
          </div>
          <span className="status-item"><Wifi size={16} color="#22c55e" /> Connected</span>
        </div>
      </header>

      {alarmStatus.active && (
        <div className="alarm-banner">
          <AlertCircle size={24} className="siren-icon" />
          <div className="alarm-text">
            <strong>🚨 SECURITY BREACH DETECTED: {alarmStatus.reason} 🚨</strong>
            <p>Physical Alarm Active at Base Station</p>
          </div>
          <button className="btn btn-danger btn-small" onClick={resetAlarm}>Silence Alarm</button>
        </div>
      )}

      {/* Security Alerts Feed */}
      {securityEvents.length > 0 && (
        <div className="card security-feed">
          <h3><Shield size={20} className="icon-red" /> Active Threats</h3>
          <div className="alert-list">
            {securityEvents.map((alert, idx) => (
              <div key={idx} className="alert-item critical">
                <AlertCircle size={16} />
                <div>
                  <strong>{alert.reason || "Unknown Anomaly"}</strong>
                  <div className="text-small">
                    {alert.device_id} • {new Date(alert.timestamp * 1000).toLocaleTimeString()}
                    {alert.confidence && ` • Conf: ${(alert.confidence * 100).toFixed(0)}%`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <nav className="tabs">
        <button className={`tab ${activeTab === 'esp32' ? 'active' : ''}`} onClick={() => setActiveTab('esp32')}>
          <Lightbulb size={18} /> ESP32 Light & Motion
        </button>
        <button className={`tab ${activeTab === 'esp8266' ? 'active' : ''}`} onClick={() => setActiveTab('esp8266')}>
          <Thermometer size={18} /> ESP8266 Temp & Humidity
        </button>
        <button className={`tab ${activeTab === 'analytics' ? 'active' : ''}`} onClick={() => setActiveTab('analytics')}>
          <Activity size={18} /> Historical Analytics
        </button>
        <button className={`tab ${activeTab === 'security' ? 'active' : ''}`} onClick={() => setActiveTab('security')}>
          <Shield size={18} /> Security & Blockchain
        </button>
        <button className={`tab ${activeTab === 'devices' ? 'active' : ''}`} onClick={() => setActiveTab('devices')}>
          <Settings size={18} /> Device Manager
        </button>
      </nav>

      {/* Tab Content */}
      <main className="content">
        {/* ESP32 Tab */}
        {activeTab === 'esp32' && (
          <div className="tab-content">
            <div className="device-header">
              <h2>ESP32 - Intelligent Lighting Control</h2>
              <div className={`power-badge ${esp32State.deviceOn ? 'on' : 'off'}`}>
                {esp32State.deviceOn ? 'ONLINE' : 'OFFLINE'}
              </div>
            </div>

            <div className="grid-2col">
              <div className="card light-card main-feature">
                <div className={`light-bulb ${esp32State.light ? 'on' : 'off'}`}>
                  <Lightbulb size={100} strokeWidth={1} />
                </div>
                <h3>Manual Override: {esp32State.light ? 'Active' : 'Standby'}</h3>
                <div className="control-buttons">
                  <button className={`btn ${esp32State.light ? 'btn-danger' : 'btn-success'} btn-large`} onClick={toggleLight} disabled={!esp32State.deviceOn}>
                    {esp32State.light ? 'Turn Lamp OFF' : 'Turn Lamp ON'}
                  </button>
                  <button className={`btn ${esp32State.deviceOn ? 'btn-warning' : 'btn-primary'}`} onClick={toggleEsp32Power}>
                    <Power size={18} />
                  </button>
                </div>
              </div>

              <div className="grid-1col-gap">
                <div className="card motion-card">
                  <h3><Activity size={20} className="icon-orange" /> Real-time Motion Profile</h3>
                  <div className="chart-container">
                    <ResponsiveContainer width="100%" height={150}>
                      <BarChart data={motionTimeline}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                        <XAxis dataKey="time" stroke="#777" fontSize={10} />
                        <YAxis stroke="#777" fontSize={10} />
                        <Tooltip contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #646cff' }} />
                        <Bar dataKey="count" fill="#f59e0b" radius={[4, 4, 0, 0]}>
                          {motionTimeline.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.count > 2 ? '#ef4444' : '#f59e0b'} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="card metrics-card accent-border">
                  <div className="metric-row">
                    <div className="metric">
                      <span className="m-label">System Power</span>
                      <span className="m-value">{esp32State.power.toFixed(1)}W</span>
                    </div>
                    <div className="metric">
                      <span className="m-label">Network Load</span>
                      <span className="m-value">{esp32State.network.toFixed(0)}KB/s</span>
                    </div>
                    <div className="metric">
                      <span className="m-label">CPU Load</span>
                      <span className="m-value">{esp32State.cpu}%</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ESP8266 Tab */}
        {activeTab === 'esp8266' && (
          <div className="tab-content">
            <div className="device-header">
              <h2>ESP8266 - Environmental Monitor</h2>
              <div className={`power-badge ${esp8266State.deviceOn ? 'on' : 'off'}`}>
                {esp8266State.deviceOn ? 'ONLINE' : 'OFFLINE'}
              </div>
            </div>

            <div className="grid-4col">
              <div className="card gauge-card premium">
                <div className="gauge-icon-bg temp"><Thermometer size={32} /></div>
                <div className="gauge-value">{esp8266State.temp.toFixed(1)}°C</div>
                <div className="gauge-label">Temperature</div>
              </div>

              <div className="card gauge-card premium">
                <div className="gauge-icon-bg humid"><Droplets size={32} /></div>
                <div className="gauge-value">{esp8266State.humidity.toFixed(1)}%</div>
                <div className="gauge-label">Humidity</div>
              </div>

              <div className="card gauge-card premium">
                <div className="gauge-icon-bg vibration"><Activity size={32} /></div>
                <div className="gauge-value">{esp8266State.vibration.toFixed(2)}</div>
                <div className="gauge-label">Vibration Index</div>
              </div>

              <div className="card gauge-card premium">
                <div className="gauge-icon-bg power"><Activity size={32} /></div>
                <div className="gauge-value">{esp8266State.power.toFixed(1)}W</div>
                <div className="gauge-label">Power Consumption</div>
              </div>

              <div className="card gauge-card premium">
                <div className={`gauge-icon-bg ${esp8266State.alarm ? 'alarm-active' : 'alarm-idle'}`}><Bell size={32} /></div>
                <div className="gauge-value">{esp8266State.alarm ? 'ARMED' : 'OFF'}</div>
                <div className="gauge-label">Security Alarm</div>
                <button className={`btn ${esp8266State.alarm ? 'btn-danger' : 'btn-success'} btn-small`} onClick={toggleAlarm} disabled={!esp8266State.deviceOn}>
                  {esp8266State.alarm ? 'Disarm' : 'Arm'}
                </button>
              </div>
            </div>

            <div className="card full-width">
              <h3><Activity size={20} className="icon-blue" /> Atmospheric Vector Trends</h3>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={tempHistory}>
                    <defs>
                      <linearGradient id="colorTemp" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="colorHumid" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="time" stroke="#777" fontSize={12} />
                    <YAxis stroke="#777" fontSize={12} />
                    <Tooltip contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #646cff' }} />
                    <Legend />
                    <Area type="monotone" dataKey="temp" stroke="#ef4444" fillOpacity={1} fill="url(#colorTemp)" name="Temp (°C)" />
                    <Area type="monotone" dataKey="humidity" stroke="#3b82f6" fillOpacity={1} fill="url(#colorHumid)" name="Humidity (%)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        {/* Security & Blockchain Tab */}
        {activeTab === 'security' && (
          <div className="tab-content">
            <div className="section-header">
              <h2><Shield size={24} className="icon-gold" /> Security & Immutable Audit</h2>
              <p>Blockchain-backed verification of all system events and device interactions.</p>
            </div>

            <div className="grid-2col">
              <div className="card security-feed">
                <h3><AlertCircle size={20} className="icon-red" /> Live Security Alerts</h3>
                <div className="alert-list">
                  {securityAlerts.length > 0 ? securityAlerts.map((alert, i) => (
                    <div key={i} className="alert-item threat">
                      <div className="alert-icon"><Shield size={16} /></div>
                      <div className="alert-details">
                        <p className="alert-msg">{alert.reason || (alert.threat_type ? alert.threat_type.replace('_', ' ') : 'Security Anomaly')}</p>
                        <p className="alert-meta">Device: {alert.device_id} • {new Date(alert.timestamp * 1000).toLocaleTimeString()}</p>
                      </div>
                      <span className="severity-high">{alert.threat_type ? 'THREAT' : 'ANOMALY'}</span>
                    </div>
                  )) : <div className="no-alerts">No threats detected. System secure.</div>}
                </div>
              </div>

              <div className="card health-center">
                <h3><Heart size={20} className="icon-blue" /> System Health Status</h3>
                <div className="health-list">
                  {systemHealth.length > 0 ? systemHealth.map((h, i) => (
                    <div key={i} className={`health-item ${h.status}`}>
                      <div className="health-icon"><Activity size={16} /></div>
                      <div className="health-info">
                        <span className="health-name">{h.device_id}</span>
                        <span className="health-meta">Last seen: {h.seconds_ago}s ago</span>
                      </div>
                      <span className={`health-status-badge ${h.status}`}>{h.status.toUpperCase()}</span>
                    </div>
                  )) : <div className="no-data">Initializing health monitor...</div>}
                </div>
              </div>
            </div>

            {/* Blockchain Bottom Section */}
            <div className="card blockchain-auditor full-width mt-1">
              <h3><Lock size={20} className="icon-gold" /> Blockchain Audit Log</h3>
              <div className="audit-list">
                {blockchainLogs.map((log, i) => (
                  <div key={i} className="audit-entry">
                    <div className="audit-icon"><Database size={16} /></div>
                    <div className="audit-info">
                      <span className="audit-type">{log.event_type}</span>
                      <span className="audit-hash">{log.batch_hash.substring(0, 16)}...</span>
                    </div>
                    <span className="audit-time">{new Date(log.timestamp * 1000).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Device Manager Tab */}
        {activeTab === 'devices' && (
          <div className="tab-content">
            <div className="section-header">
              <h2><Plus size={24} /> Device Inventory</h2>
              <p>Register and configure new hardware modules for the sensor network.</p>
            </div>

            <div className="grid-2col">
              <div className="card">
                <h3>Register New Module</h3>
                <div className="form-column">
                  <div className="form-group">
                    <label>Module Identifier (Global Unique)</label>
                    <input type="text" placeholder="e.g. gateway_north_01" value={newDevice.id} onChange={e => setNewDevice({ ...newDevice, id: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label>Hardware Architecture</label>
                    <select value={newDevice.type} onChange={e => setNewDevice({ ...newDevice, type: e.target.value })}>
                      <option value="esp32">ESP32 (Light + Motion Cluster)</option>
                      <option value="esp8266">ESP8266 (Env Cluster)</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Authorized Admin ID</label>
                    <input type="text" placeholder="user_xyz" value={newDevice.userId} onChange={e => setNewDevice({ ...newDevice, userId: e.target.value })} />
                  </div>
                  <button className="btn btn-primary btn-full" onClick={addDevice}>
                    <Plus size={18} /> Deploy Module
                  </button>
                </div>
              </div>

              <div className="card">
                <h3>Active Hardware Inventory</h3>
                <div className="inventory-list">
                  {devices.map((d, i) => {
                    const health = systemHealth.find(h => h.device_id === d.id);
                    return (
                      <div key={i} className={`inventory-item ${d.quarantined ? 'quarantined-item' : ''}`}>
                        <div className="inv-icon">
                          {d.quarantined ? <Shield size={18} color="#ef4444" /> : <Wifi size={18} />}
                        </div>
                        <div className="inv-info-box">
                          <div className="inv-name">
                            {d.id} {d.quarantined && <span className="quarantine-badge">QUARANTINED</span>}
                          </div>
                          <div className="inv-meta">
                            {d.type.toUpperCase()} • {d.location || 'unassigned'}
                          </div>
                        </div>
                        <div className="inv-trust-box">
                          <div className="trust-label">Trust Score</div>
                          <div className={`trust-value ${trustScores[d.id] < 50 || d.quarantined ? 'low' : 'high'}`}>
                            {d.quarantined ? 'BLOCKED' : (trustScores[d.id] || 100)}
                          </div>
                        </div>
                        <div className={`inv-status ${health?.status || 'offline'}`}>
                          {health?.status ? health.status.toUpperCase() : 'OFFLINE'}
                        </div>
                        <div className="inv-actions">
                          {d.quarantined ? (
                            <button className="btn btn-small btn-danger" onClick={() => unquarantineDevice(d.id)}>
                              <Shield size={14} style={{ marginRight: '5px' }} /> Un-Quarantine (Revive)
                            </button>
                          ) : (
                            <button className="btn btn-small btn-primary ota-btn" onClick={() => triggerOtaUpdate(d.id, "v2.0.0")}>
                              <UploadCloud size={14} style={{ marginRight: '5px' }} /> Update (v2.0)
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Analytics Tab */}
        {activeTab === 'analytics' && (
          <div className="tab-content">
            <div className="section-header">
              <h2><Activity size={24} className="icon-blue" /> Network-Wide Historical Analytics</h2>
              <p>Aggregated daily telemetry mapping environmental factors against system power usage and anomalies.</p>
            </div>

            <div className="card full-width premium-chart">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3>Macro-Ecosystem Trends</h3>
                <div className="export-controls">
                  <button className="btn btn-secondary btn-small" onClick={downloadAsCSV} style={{ marginRight: '10px' }}>
                    <Download size={14} style={{ marginRight: '5px' }} /> Export CSV
                  </button>
                  <button className="btn btn-secondary btn-small" onClick={downloadAsJSON}>
                    <Database size={14} style={{ marginRight: '5px' }} /> Export JSON
                  </button>
                </div>
              </div>
              <div className="chart-container" style={{ height: '400px', marginTop: '20px' }}>
                {historicalMetrics.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={historicalMetrics} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#2a2a35" />
                      <XAxis dataKey="day" stroke="#8892b0" />
                      <YAxis yAxisId="left" stroke="#3b82f6" label={{ value: 'Temp/Humidity', angle: -90, position: 'insideLeft', fill: '#8892b0' }} />
                      <YAxis yAxisId="right" orientation="right" stroke="#f59e0b" label={{ value: 'System Power (W)', angle: 90, position: 'insideRight', fill: '#8892b0' }} />

                      <Tooltip
                        contentStyle={{ backgroundColor: '#112240', border: '1px solid #233554', borderRadius: '8px', color: '#ccd6f6' }}
                        itemStyle={{ color: '#e6f1ff' }}
                      />
                      <Legend verticalAlign="top" height={36} />

                      <Line yAxisId="left" type="monotone" dataKey="temp" name="Avg Temperature (°C)" stroke="#ef4444" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                      <Line yAxisId="left" type="monotone" dataKey="humidity" name="Avg Humidity (%)" stroke="#3b82f6" strokeWidth={3} />
                      <Line yAxisId="right" type="monotone" dataKey="power" name="Avg Node Power (W)" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 5" />

                      {/* Plot Anomalies as a bar graph underneath the lines */}
                      <Bar yAxisId="right" dataKey="anomalies" name="Detected Threats" fill="#8b5cf6" opacity={0.6} radius={[4, 4, 0, 0]} barSize={20} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="no-data-display" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', color: '#8892b0' }}>
                    Accumulating historical data from blockchain logs...
                  </div>
                )}
              </div>
            </div>

            <div className="grid-3col">
              <div className="card stat-card">
                <div className="stat-value">{logs.length}</div>
                <div className="stat-label">Total Logs Analyzed</div>
              </div>
              <div className="card stat-card">
                <div className="stat-value">{historicalMetrics.reduce((acc, curr) => acc + curr.anomalies, 0)}</div>
                <div className="stat-label">Total Threats Detected</div>
              </div>
              <div className="card stat-card">
                <div className="stat-value">{devices.length}</div>
                <div className="stat-label">Active Endpoints</div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
