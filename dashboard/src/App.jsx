import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, AreaChart, Area } from 'recharts'
import { Lightbulb, Thermometer, Droplets, Bell, Power, Activity, Plus, Settings, Wifi, Shield, Lock, Fingerprint, Database, AlertCircle, Heart } from 'lucide-react'
import './App.css'

const API_URL = 'http://localhost:5002/api'

function App() {
  const [activeTab, setActiveTab] = useState('esp32')
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

  // Fetch data periodically
  useEffect(() => {
    const fetchData = async () => {
      try {
        const config = { timeout: 4000 };

        // Use Promise.allSettled so one failure doesn't break everything
        const results = await Promise.allSettled([
          axios.get(`${API_URL}/logs?limit=50`, config),
          axios.get(`${API_URL}/blockchain/logs?limit=20`, config),
          axios.get(`${API_URL}/health`, config),
          axios.get(`${API_URL}/devices`, config),
          axios.get(`${API_URL}/alarm/status`, config)
        ]);

        const [logsRes, bcRes, healthRes, devRes, alarmRes] = results;

        // Logs (Critical)
        const data = logsRes.status === 'fulfilled' && Array.isArray(logsRes.value.data) ? logsRes.value.data : [];
        const sortedData = data.sort((a, b) => b.timestamp - a.timestamp);
        setLogs(sortedData);

        // Blockchain Logs (Non-critical)
        setBlockchainLogs(bcRes.status === 'fulfilled' && Array.isArray(bcRes.value.data) ? bcRes.value.data : []);

        // Health (Non-critical)
        setSystemHealth(healthRes.status === 'fulfilled' && Array.isArray(healthRes.value.data) ? healthRes.value.data : []);

        // Alarm Status (Critical)
        if (alarmRes.status === 'fulfilled') {
          setAlarmStatus(alarmRes.value.data);
        }

        // Devices (Critical - Fallback to logs if registry fails or is empty)
        let deviceList = [];
        if (devRes.status === 'fulfilled' && Array.isArray(devRes.value.data) && devRes.value.data.length > 0) {
          deviceList = devRes.value.data;
        } else {
          // Auto-discovery from logs if registry is unreachable
          const uniqueIds = [...new Set(sortedData.map(l => l.device_id).filter(id => id))];
          deviceList = uniqueIds.map(id => ({
            id,
            type: id.includes('esp8266') ? 'esp8266' : 'esp32',
            status: 'discovered'
          }));
          if (deviceList.length > 0) console.log("⚠️ Registry failed, auto-discovered devices:", deviceList);
        }
        setDevices(deviceList);

        // Success - release loading screen immediately
        setLoading(false);

        // Update device states from latest logs
        const esp32Log = sortedData.find(l => l.device_id === 'esp32_sec_01' || l.device_id?.startsWith('esp32'));
        const esp8266Log = sortedData.find(l => l.device_id === 'esp8266_env_01' || l.device_id?.startsWith('esp8266'));

        if (esp32Log?.sensors) {
          const motionLogs = sortedData
            .filter(l => (l.device_id === 'esp32_sec_01' || l.device_id?.startsWith('esp32')) && l.sensors?.motion)
            .slice(0, 20)
            .map(l => ({
              time: new Date(l.timestamp * 1000).toLocaleTimeString(),
              timestamp: l.timestamp
            }));

          setEsp32State(prev => ({
            ...prev,
            light: esp32Log.sensors.light_state || false,
            motionEvents: motionLogs,
            power: esp32Log.system?.power_watts || 0,
            network: esp32Log.system?.network_activity || 0,
            cpu: esp32Log.system?.cpu_usage || 0,
            deviceOn: true
          }));
        }

        if (esp8266Log?.sensors) {
          setEsp8266State(prev => ({
            ...prev,
            temp: esp8266Log.sensors.temperature || 25,
            humidity: esp8266Log.sensors.humidity || 50,
            alarm: esp8266Log.sensors.alarm_enabled || false,
            vibration: esp8266Log.sensors.vibration || 0,
            power: esp8266Log.system?.power_watts || 0,
            network: esp8266Log.system?.network_activity || 0,
            cpu: esp8266Log.system?.cpu_usage || 0,
            deviceOn: true
          }));
        }

        // Fetch Trust Scores (non-blocking)
        const scores = {};
        for (const dev of deviceList) {
          try {
            const trustRes = await axios.get(`${API_URL}/blockchain/trust/${dev.id}`, { timeout: 2000 });
            scores[dev.id] = trustRes.data.trust_score;
          } catch (e) {
            scores[dev.id] = 'N/A';
          }
        }
        setTrustScores(prev => ({ ...prev, ...scores }));

      } catch (e) {
        console.error('Fetch error:', e);
        setLoading(false); // Ensure we don't hang on error
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 1000)
    return () => clearInterval(interval)
  }, [])

  // Send control command
  const sendCommand = async (deviceId, command) => {
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
      alert("No active ESP32 device found in registry. Please ensure it's registered in Device Manager.");
      return;
    }

    const cmd = esp32State.light ? 'LIGHT_OFF' : 'LIGHT_ON'
    console.log(`[DASHBOARD] Toggling Light for ${targetId}: current state ${esp32State.light}`);
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
                      <div key={i} className="inventory-item">
                        <div className="inv-icon"><Wifi size={18} /></div>
                        <div className="inv-info-box">
                          <div className="inv-name">{d.id}</div>
                          <div className="inv-meta">
                            {d.type.toUpperCase()} • {d.location}
                          </div>
                        </div>
                        <div className="inv-trust-box">
                          <div className="trust-label">Trust Score</div>
                          <div className={`trust-value ${trustScores[d.id] < 50 ? 'low' : 'high'}`}>
                            {trustScores[d.id] || 100}
                          </div>
                        </div>
                        <div className={`inv-status ${health?.status || 'offline'}`}>
                          {health?.status ? health.status.toUpperCase() : 'OFFLINE'}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
