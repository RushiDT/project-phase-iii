import { useState, useEffect } from 'react'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Activity, Thermometer, Cpu, Zap, AlertTriangle, ShieldCheck, Server } from 'lucide-react'
import './App.css'

const API_URL = 'http://localhost:5002/api'

function App() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(Date.now())
  const [deviceStatus, setDeviceStatus] = useState("Unknown")
  const [trustScore, setTrustScore] = useState(100)
  const [blockchainLogs, setBlockchainLogs] = useState([])
  const [contractAddress, setContractAddress] = useState("Loading...")

  // Fetch data periodically
  useEffect(() => {
    let timeoutId;
    let pollCount = 0;

    const fetchData = async () => {
      try {
        // Fetch sensor logs - limit to 100 to prevent memory issues
        const response = await axios.get(`${API_URL}/logs?limit=100`)
        const data = Array.isArray(response.data) ? response.data : []
        const sortedLogs = data.sort((a, b) => b.timestamp - a.timestamp).slice(0, 100)
        setLogs(sortedLogs)
        setError(null)

        // Fetch blockchain data only every 4th poll (approx every 12s) to reduce overhead
        if (pollCount % 4 === 0) {
          // Fetch blockchain trust score
          try {
            const trustResponse = await axios.get(`${API_URL}/blockchain/trust/esp32_sim_01`)
            setTrustScore(trustResponse.data.trust_score || 100)
          } catch (e) {
            console.log("Could not fetch trust score:", e.message)
          }

          // Fetch blockchain logs
          try {
            const bcLogsResponse = await axios.get(`${API_URL}/blockchain/logs?limit=10`)
            const bcData = Array.isArray(bcLogsResponse.data) ? bcLogsResponse.data : []
            setBlockchainLogs(bcData)
          } catch (e) {
            console.log("Could not fetch blockchain logs:", e.message)
          }
        }

        pollCount++;
      } catch (err) {
        console.error("Failed to fetch logs:", err)
        setError("Failed to connect to server")
      } finally {
        setLoading(false)
        setLastUpdate(Date.now())
        // Schedule next poll ONLY after this one finishes
        timeoutId = setTimeout(fetchData, 3000)
      }
    }

    fetchData()
    return () => clearTimeout(timeoutId)
  }, [])

  // Calculate metrics
  const totalLogs = logs.length
  const recentLogs = logs.slice(0, 50)
  const chartData = [...recentLogs].reverse().map(l => ({
    time: new Date(l.timestamp * 1000).toLocaleTimeString(),
    temp: l.sensors?.temperature || 0,
    humidity: l.sensors?.humidity || 0,
    motion: l.sensors?.motion ? 1 : 0,
    light: l.sensors?.light_level || 0,
    anomaly: (l.sensors?.temperature || 0) > 40 || l.sensors?.vibration > 1.5
  }))

  const handleDeviceControl = async (command) => {
    try {
      if (command === "STOP") {
        setDeviceStatus("Stopping...")
        // In real app, call API
        await axios.post(`${API_URL}/control`, { device_id: "esp32_sim_01", command: "STOP" })
        setTimeout(() => setDeviceStatus("Offline"), 2000)
      } else {
        setDeviceStatus("Starting...")
        await axios.post(`${API_URL}/control`, { device_id: "esp32_sim_01", command: "START" })
        setTimeout(() => setDeviceStatus("Online"), 2000)
      }
    } catch (e) {
      alert("Command failed: " + e.message)
    }
  }

  return (
    <div className="dashboard-container">
      <header className="header">
        <div className="flex items-center gap-2">
          <ShieldCheck size={32} color="#646cff" />
          <h1>IoT Security Dashboard</h1>
        </div>
        <div className={`status-badge ${deviceStatus === 'Offline' ? 'offline' : ''}`}>
          <Activity size={16} />
          {deviceStatus}
        </div>
      </header>

      {loading && <div style={{ padding: '2rem', textAlign: 'center', color: '#888' }}>Loading dashboard data...</div>}
      {error && <div style={{ padding: '1rem', marginBottom: '1rem', background: 'rgba(255,0,0,0.2)', borderRadius: '8px', color: '#ff8888' }}>{error}</div>}

      {/* Metric Cards */}
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-title flex items-center gap-2"><Server size={16} /> Active Devices</span>
          <span className="metric-value">{new Set(logs.map(l => l.device_id)).size}</span>
        </div>
        <div className="metric-card">
          <span className="metric-title flex items-center gap-2"><AlertTriangle size={16} /> Security Alerts</span>
          <span className="metric-value anomaly">{logs.filter(l => l.sensors?.motion).length}</span>
        </div>
        <div className="metric-card">
          <span className="metric-title flex items-center gap-2"><Thermometer size={16} /> Max Temp</span>
          <span className="metric-value">
            {logs.length > 0 ? Math.max(...logs.map(l => l.sensors?.temperature || 0)).toFixed(1) : 0}°C
          </span>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="charts-section">
        <div className="chart-card">
          <h3>Real-time Telemetry</h3>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis dataKey="time" stroke="#888" />
                <YAxis stroke="#888" />
                <Tooltip contentStyle={{ backgroundColor: '#333', border: '1px solid #555' }} />
                <Legend />
                <Line type="monotone" dataKey="temp" stroke="#8884d8" name="Temp (°C)" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="humidity" stroke="#82ca9d" name="Hum (%)" dot={false} strokeWidth={2} />
                <Line type="stepAfter" dataKey="motion" stroke="#ff4444" name="Motion" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-card">
          <h3>Device Control</h3>
          <div className="control-panel flex-col">
            <p className="text-gray-400 mb-4">Manage IoT Device State</p>
            <div className="flex gap-4">
              <button
                className="btn btn-primary flex-1"
                onClick={() => handleDeviceControl("START")}
                disabled={deviceStatus === "Starting..."}
              >
                Start Device
              </button>
              <button
                className="btn btn-danger flex-1"
                onClick={() => handleDeviceControl("STOP")}
                disabled={deviceStatus === "Stopping..."}
              >
                Emergency Stop
              </button>
            </div>

            <div className="mt-8 p-4 bg-black/20 rounded">
              <h4>Blockchain Trust Score</h4>
              <div className="flex items-center gap-4 mt-2">
                <div className="h-2 w-full bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full ${trustScore > 70 ? 'bg-green-500' : trustScore > 40 ? 'bg-yellow-500' : 'bg-red-500'}`}
                    style={{ width: `${trustScore}%` }}
                  ></div>
                </div>
                <span className={`font-bold ${trustScore > 70 ? 'text-green-400' : trustScore > 40 ? 'text-yellow-400' : 'text-red-400'}`}>
                  {trustScore}/100
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-2">Device: esp32_sim_01</p>
              {blockchainLogs.length > 0 && (
                <div className="mt-4">
                  <h5 className="text-sm font-semibold mb-2">Recent Blockchain Events:</h5>
                  <div className="max-h-24 overflow-y-auto text-xs">
                    {blockchainLogs.slice(0, 3).map((log, i) => (
                      <div key={i} className="flex flex-col py-2 border-b border-gray-700">
                        <div className="flex justify-between">
                          <span className="text-red-400">{log.event_type}</span>
                          <span className="text-gray-400">Score: {(log.anomaly_score * 100).toFixed(0)}%</span>
                        </div>
                        <div className="text-[10px] text-gray-500 font-mono mt-1 break-all">
                          Batch: {log.batch_hash}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Logs Table */}
      <div className="logs-section">
        <h3>Incoming Data Stream</h3>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Device ID</th>
                <th>Sequence</th>
                <th>Temp</th>
                <th>CPU</th>
                <th>Battery</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recentLogs.map((log, i) => {
                const isAnomaly = (log.sensors?.temperature > 40) || log.sensors?.motion
                return (
                  <tr key={i} className={`log-row ${isAnomaly ? 'anomaly' : ''}`}>
                    <td>{new Date(log.timestamp * 1000).toLocaleTimeString()}</td>
                    <td>{log.device_id}</td>
                    <td>{log.sequence_number}</td>
                    <td>
                      {log.sensors?.temperature ? `${log.sensors.temperature.toFixed(1)}°C` :
                        log.sensors?.motion ? 'MOTION!' : 'Stable'}
                    </td>
                    <td>{log.system?.cpu_usage}%</td>
                    <td>{log.system?.battery_level}%</td>
                    <td>
                      {isAnomaly ?
                        <span className="text-red-500 font-bold flex items-center gap-1"><AlertTriangle size={14} /> ALERT</span> :
                        <span className="text-green-500">Normal</span>
                      }
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default App
