import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  AreaChart, Area, ResponsiveContainer, YAxis
} from 'recharts';
import { Activity, Terminal, AlertTriangle } from 'lucide-react';
import './App.css';

const API_URL = "http://127.0.0.1:8000";
const THREAD_ID = "demo_session_1";

const App = () => {
  const [status, setStatus] = useState("ONLINE");
  const [logs, setLogs] = useState([]);
  const [telemetry, setTelemetry] = useState([]); // This will hold the raw transaction data
  const [pendingAction, setPendingAction] = useState(null);

  const logsEndRef = useRef(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Logic to calculate metrics based on the telemetry logs from server.py
  const metrics = useMemo(() => {
    if (!telemetry || telemetry.length === 0) return { successRate: 100, avgLatency: 0 };
    const total = telemetry.length;
    const successCount = telemetry.filter(t => t.status === "SUCCESS").length;
    const totalLatency = telemetry.reduce((acc, t) => acc + (t.latency_ms || 0), 0);
    return {
      successRate: ((successCount / total) * 100).toFixed(1),
      avgLatency: Math.round(totalLatency / total)
    };
  }, [telemetry]);

  // Polling System: Now handles both Telemetry (Chart data) and Agent State (Approval check)
  useEffect(() => {
    const pollSystem = async () => {
      try {
        // 1. Fetch live telemetry from the log file via server.py
        const telRes = await fetch(`${API_URL}/telemetry`);
        const telData = await telRes.json();
        if (telData.logs) setTelemetry(telData.logs);

        // 2. Check if the Agent is stuck at the 'Sentry' node
        if (status !== "ACTION_REQUIRED") {
          const stateRes = await fetch(`${API_URL}/agent_state?thread_id=${THREAD_ID}`);
          const stateData = await stateRes.json();
          if (stateData.status === "WAITING_FOR_APPROVAL") {
            setStatus("ACTION_REQUIRED");
            const proposal = JSON.parse(stateData.proposal || "{}");
            setPendingAction(proposal);
          }
        }
      } catch (e) { console.error("Polling error:", e); }
    };
    const interval = setInterval(pollSystem, 1000); // Fast poll for the chart
    return () => clearInterval(interval);
  }, [status]);

  // Driver: Runs the Agent loop
  useEffect(() => {
    let timeoutId;
    let isMounted = true;
    const driveAgent = async () => {
      if (status === "ACTION_REQUIRED") return;
      try {
        const res = await fetch(`${API_URL}/run_cycle`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ thread_id: THREAD_ID })
        });
        const data = await res.json();
        if (data.logs && data.logs.length > 0) {
          const newLogs = data.logs.map(l => ({
            id: Math.random(),
            timestamp: new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            content: l
          }));
          setLogs(prev => [...prev, ...newLogs]);
        }
      } catch (e) { console.error(e); }
      finally {
        if (isMounted && status !== "ACTION_REQUIRED") timeoutId = setTimeout(driveAgent, 2000);
      }
    };
    if (status !== "ACTION_REQUIRED") driveAgent();
    return () => { isMounted = false; clearTimeout(timeoutId); };
  }, [status]);

  const handleDecision = async (approved) => {
    try {
      const res = await fetch(`${API_URL}/approve_action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: THREAD_ID, approved })
      });
      const data = await res.json();

      // Immediately log the execution result
      const resultLogs = (data.logs || []).map(l => ({
        id: Math.random(),
        timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
        content: l
      }));
      setLogs(prev => [...prev, ...resultLogs]);
      setPendingAction(null);
      setStatus("ONLINE");
    } catch (e) { console.error(e); }
  };

  const renderApprovalCard = () => {
    if (!pendingAction) return null;
    const { action_type, target_region } = pendingAction;

    return (
      <div className="approval-overlay">
        <div className="approval-card security-alert">
          <div className="approval-header">
            <AlertTriangle size={16} color="#f87171" />
            <h3>Security Intervention Required</h3>
          </div>
          <p className="approval-text">
            Critical {action_type || "BLOCK"} detected in {target_region || "US"}.
          </p>
          <div className="approval-actions">
            <button className="btn-reject" onClick={() => handleDecision(false)}>REJECT</button>
            <button className="btn-approve" onClick={() => handleDecision(true)}>AUTHORIZE</button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="app-container">
      <div className="header-wrapper">
        <div className="brand-container">
          <div className="brand-title">A.S.P.E.N</div>
          <div className="brand-subtitle">Autonomous Orchestration</div>
        </div>
        <div className={`status-badge ${status === "ACTION_REQUIRED" ? "status-alert" : ""}`}>
          <div className="status-dot"></div>
          <span>{status === "ACTION_REQUIRED" ? "WAITING FOR HUMAN" : "SYSTEM ONLINE"}</span>
        </div>
      </div>

      {status === "ACTION_REQUIRED" ? renderApprovalCard() : (
        <div className="main-grid">
          <div className="col-left">
            <div className="section-header">
              <Activity size={12} /> Latency
            </div>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={telemetry} margin={{ top: 5, right: 0, left: 0, bottom: 5 }}>
                  {/* Remove 'hide' temporarily to see the scale, or set a tighter domain */}
                  <YAxis hide domain={['dataMin - 5', 'dataMax + 5']} />
                  <Area
                    type="monotone" // Monotone looks smoother than 'step' for latency spikes
                    dataKey="latency_ms"
                    stroke="#fafafa"
                    strokeWidth={2}
                    fill="rgba(250, 250, 250, 0.1)"
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="col-right">
            <div className="section-header">
              <Terminal size={12} /> Intelligence Trace
            </div>
            <div className="console-container">
              {logs.length === 0 && <div className="console-empty" style={{ color: '#52525b' }}>System initializing...</div>}
              {logs.map(log => (
                <div key={log.id} className={`log-entry ${log.content.includes("Anomaly") ? "anomaly" : ""}`}>
                  <span className="log-ts">{log.timestamp}</span>
                  <span className="log-msg">{log.content}</span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>
        </div>
      )}
      <div className="metrics-row">
        <div className="metric-card">
          <div className="metric-label">Global Success Rate</div>
          <div className="metric-value">{metrics.successRate}%</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Avg Latency (ms)</div>
          <div className="metric-value">{metrics.avgLatency}ms</div>
        </div>
      </div>
    </div>
  );
};

export default App;
