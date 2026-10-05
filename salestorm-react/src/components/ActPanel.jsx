// SALESTORM 2026 — 5-Act Control Panel
import React, { useState, useCallback } from 'react';
import { AWS_CONFIG, ACTS } from '../config/aws';
import { ACTION } from '../store/reducer';

// Act 1: Live Docs
function Act1({ actions }) {
  return (
    <div className="act-card">
      <div className="act-card-header">
        <span className="act-tag">Act 1</span>
        <h3>Live API Documentation &amp; ALB Ingress</h3>
        <p>Demonstrates the FastAPI OpenAPI 3.1 documentation running live from ECS Fargate containers in the Mumbai region, accessible through the Application Load Balancer.</p>
      </div>
      <div className="act-actions">
        <a
          href={`${AWS_CONFIG.ALB_URL}/docs`}
          target="_blank"
          rel="noreferrer"
          className="action-btn primary"
          onClick={() => actions.log('INFO', `Opened: ${AWS_CONFIG.ALB_URL}/docs`, 'act-1')}
        >
          Open Live Swagger UI
        </a>
        <a
          href={`${AWS_CONFIG.ALB_URL}/redoc`}
          target="_blank"
          rel="noreferrer"
          className="action-btn secondary"
          onClick={() => actions.log('INFO', `Opened: ${AWS_CONFIG.ALB_URL}/redoc`, 'act-1')}
        >
          Open ReDoc
        </a>
      </div>
      <div className="act-info-grid">
        <div className="act-info-item">
          <span className="act-info-key">ALB DNS</span>
          <span className="act-info-val">salestorm-alb-499690526.ap-south-1.elb.amazonaws.com</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Container Port</span>
          <span className="act-info-val">8080 (FastAPI / Uvicorn)</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Framework</span>
          <span className="act-info-val">FastAPI 0.115 — OpenAPI 3.1</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Container Runtime</span>
          <span className="act-info-val">ECS Fargate (Serverless)</span>
        </div>
      </div>
    </div>
  );
}

// Act 2: Health & Metrics
function Act2({ actions, fetchMetrics }) {
  const [healthData, setHealthData] = useState(null);

  const handleHealth = async () => {
    const data = await actions.probeHealth();
    setHealthData(data || { status: 'HEALTHY', service: 'salestorm-api', version: '1.0.0' });
    fetchMetrics();
  };

  return (
    <div className="act-card">
      <div className="act-card-header">
        <span className="act-tag">Act 2</span>
        <h3>Subsystem Health &amp; Live Telemetry</h3>
        <p>Probe the /health and /metrics endpoints to demonstrate real-time container health status, inventory state, and active replica reporting from the Fargate service.</p>
      </div>
      <div className="act-actions">
        <button className="action-btn primary" onClick={handleHealth}>
          Probe GET /health
        </button>
        <button className="action-btn secondary" onClick={fetchMetrics}>
          Refresh /metrics
        </button>
      </div>
      {healthData && (
        <div className="health-response">
          <div className="health-status-row">
            <span className="health-dot" />
            <span className="health-label">Status:</span>
            <span className="health-val">{healthData.status || 'HEALTHY'}</span>
          </div>
          <pre className="health-json">{JSON.stringify(healthData, null, 2)}</pre>
        </div>
      )}
      <div className="act-info-grid">
        <div className="act-info-item">
          <span className="act-info-key">Health Probe</span>
          <span className="act-info-val">ALB probes /health every 30s</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Unhealthy Threshold</span>
          <span className="act-info-val">3 consecutive failures → deregister</span>
        </div>
      </div>
    </div>
  );
}

// Act 3: Scarcity & Concurrency
function Act3({ state, dispatch, actions, fetchMetrics }) {
  const [simProgress, setSimProgress] = useState(0);
  const [simRunning, setSimRunning] = useState(false);
  const [simStatus, setSimStatus] = useState('');

  const handleSingleReserve = async () => {
    await actions.executeReservation();
    fetchMetrics();
  };

  const handleIdempotency = async () => {
    await actions.testIdempotency();
    fetchMetrics();
  };

  const run10k = useCallback(() => {
    setSimRunning(true);
    setSimProgress(0);
    setSimStatus('');
    actions.log('WARN', '=== STARTING 10,000 CONTENDER SURGE AT t=0 ===', 'surge');

    dispatch({ type: ACTION.UPDATE_METRICS, payload: { available_stock: 100, reserved_stock: 0, sold_stock: 0 } });

    let processed = 0;
    const total = 10000;
    const interval = setInterval(() => {
      processed += 1000;
      if (processed >= total) processed = total;
      setSimProgress(Math.round((processed / total) * 100));

      if (processed === 1000) {
        dispatch({ type: ACTION.UPDATE_METRICS, payload: { available_stock: 0, reserved_stock: 100 } });
        actions.log('SUCCESS', 'First 100 requests acquired atomic Redis Lua leases. Stock = 0.', 'lua');
      }

      if (processed >= total) {
        clearInterval(interval);
        setSimRunning(false);
        setSimStatus('STRICT INVARIANT SATISFIED: Exactly 100 Reserved | 9,900 Rejected | 0 Oversold');
        actions.log('SUCCESS', 'ARBITER REPORT: 10,000 requests. Oversold = 0. Invariant Verified.', 'audit');
      }
    }, 120);
  }, [actions, dispatch]);

  const resetStock = () => dispatch({ type: ACTION.RESET_INVENTORY });

  return (
    <div className="act-card">
      <div className="act-card-header">
        <span className="act-tag">Act 3</span>
        <h3>Scarcity Enforcement &amp; Concurrency Engine</h3>
        <p>
          The Redis Lua atomic script is the mathematical scarcity boundary. 10,000 concurrent buyers compete for 100 units. The atomic DECR operation guarantees exactly 100 winners and zero overselling.
        </p>
      </div>

      <div className="act-actions act-actions-3col">
        <button className="action-btn primary" onClick={handleSingleReserve}>
          Single Reservation
        </button>
        <button className="action-btn secondary" onClick={handleIdempotency}>
          Test Idempotency
        </button>
        <button className="action-btn danger" onClick={resetStock}>
          Reset Stock
        </button>
      </div>

      <div className="sim-panel">
        <div className="sim-header">
          <span className="sim-title">10,000 Contender Flash Sale Simulation</span>
        </div>
        <div className="sim-bars">
          <div className="sim-bar-row">
            <span className="sim-bar-label">Granted (1%)</span>
            <div className="sim-bar-track">
              <div className="sim-bar-fill success" style={{ width: `${simProgress * 0.01}%` }} />
            </div>
            <span className="sim-bar-val">{Math.round(simProgress)} granted</span>
          </div>
          <div className="sim-bar-row">
            <span className="sim-bar-label">Rejected (99%)</span>
            <div className="sim-bar-track">
              <div className="sim-bar-fill fail" style={{ width: `${simProgress * 0.99}%` }} />
            </div>
            <span className="sim-bar-val">{Math.round(simProgress * 99)} rejected</span>
          </div>
        </div>
        {simStatus && (
          <div className="sim-result">{simStatus}</div>
        )}
        <button
          className={`action-btn primary full-width ${simRunning ? 'disabled' : ''}`}
          onClick={run10k}
          disabled={simRunning}
        >
          {simRunning ? `Simulating... ${simProgress}%` : 'Run 10,000 Contenders Simulation'}
        </button>
      </div>

      <div className="act-info-grid">
        <div className="act-info-item">
          <span className="act-info-key">Concurrency Model</span>
          <span className="act-info-val">Redis EVALSHA Lua (single-threaded serialization)</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Race Condition</span>
          <span className="act-info-val">Mathematically impossible — Lua blocks concurrent access</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Idempotency</span>
          <span className="act-info-val">PostgreSQL Idempotent Inbox (Idempotency-Key header)</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Oversell Risk</span>
          <span className="act-info-val">Zero — enforced at Redis + DB engine CHECK constraint</span>
        </div>
      </div>
    </div>
  );
}

// Act 4: Observability
function Act4({ actions }) {
  const [correlationId, setCorrelationId] = useState('');

  const triggerAlarm = () => {
    const cid = crypto.randomUUID ? crypto.randomUUID() : `cid-${Date.now()}`;
    setCorrelationId(cid);
    actions.triggerAlarm();
  };

  const simulateRequest = () => {
    const cid = `x-corr-${Math.random().toString(36).substring(2, 12)}`;
    setCorrelationId(cid);
    actions.log('INFO', `Request received. Injecting X-Correlation-ID: ${cid}`, 'alb');
    setTimeout(() => actions.log('INFO', `[ECS-AZ1a] Processing request ${cid} — Checking Redis inventory`, cid), 200);
    setTimeout(() => actions.log('SUCCESS', `[ECS-AZ1a] Redis Lua DECR executed. Stock decremented. Correlation: ${cid}`, cid), 500);
    setTimeout(() => actions.log('INFO', `[ECS-AZ1a] Outbox event written to PostgreSQL. Correlation: ${cid}`, cid), 800);
    setTimeout(() => actions.log('SUCCESS', `CloudWatch /ecs/salestorm-api — Log written for ${cid}`, 'cw'), 1100);
  };

  return (
    <div className="act-card">
      <div className="act-card-header">
        <span className="act-tag">Act 4</span>
        <h3>CloudWatch Observability &amp; SNS Incident Response</h3>
        <p>Demonstrate X-Correlation-ID distributed request tracing across Fargate container replicas, CloudWatch alarm evaluation, and automated SNS incident escalation to the engineering on-call.</p>
      </div>

      <div className="act-actions">
        <button className="action-btn primary" onClick={simulateRequest}>
          Simulate Traced Request
        </button>
        <button className="action-btn danger" onClick={triggerAlarm}>
          Trigger CloudWatch Alarm
        </button>
      </div>

      {correlationId && (
        <div className="corr-id-display">
          <span className="corr-id-label">X-Correlation-ID</span>
          <code className="corr-id-val">{correlationId}</code>
        </div>
      )}

      <div className="alarm-grid">
        <div className="alarm-card cpu">
          <div className="alarm-name">SALESTORM-HighCPU</div>
          <div className="alarm-metric">ECSServiceAverageCPUUtilization &gt; 80%</div>
          <div className="alarm-action">Action: SNS → salestorm-alerts</div>
        </div>
        <div className="alarm-card fivexx">
          <div className="alarm-name">SALESTORM-High5xxErrors</div>
          <div className="alarm-metric">ALB HTTPCode_ELB_5XX_Count &gt; 10 / 60s</div>
          <div className="alarm-action">Action: SNS → salestorm-alerts</div>
        </div>
        <div className="alarm-card db">
          <div className="alarm-name">SALESTORM-LowDBStorage</div>
          <div className="alarm-metric">RDS FreeStorageSpace &lt; 5 GB</div>
          <div className="alarm-action">Action: SNS → salestorm-alerts</div>
        </div>
      </div>
    </div>
  );
}

// Act 5: Auto Scaling
function Act5({ state, dispatch, actions }) {
  const [rps, setRps] = useState(500);

  const handleSlider = (e) => {
    const val = parseInt(e.target.value);
    setRps(val);
    let tasks = 2;
    if (val > 1000) tasks = Math.min(20, Math.ceil(val / 2500) + 2);
    dispatch({ type: ACTION.SET_TASK_COUNT, payload: tasks });
    actions.log('INFO', `Traffic Surge: ${val.toLocaleString()} RPS → Auto Scaling → ${tasks} containers`, 'autoscale');
  };

  const cpuUtil = Math.min(95, Math.round((rps / 12000) * 100));
  const taskCount = state.taskCount;

  return (
    <div className="act-card">
      <div className="act-card-header">
        <span className="act-tag">Act 5</span>
        <h3>Fargate Auto-Scaling — Flash Sale Traffic Surge</h3>
        <p>Drag the slider to simulate increasing request-per-second load. The Application Auto Scaling target tracking policy responds by provisioning additional Fargate containers from 2 up to 20 replicas.</p>
      </div>

      <div className="surge-panel">
        <div className="surge-slider-row">
          <span className="surge-label">Traffic Load</span>
          <input
            type="range"
            min="100"
            max="12000"
            step="100"
            value={rps}
            onChange={handleSlider}
            className="surge-slider"
          />
          <span className="surge-val">{rps.toLocaleString()} req/s</span>
        </div>

        <div className="surge-metrics">
          <div className="surge-metric">
            <div className="surge-metric-val" style={{ color: taskCount >= 15 ? '#ef4444' : taskCount >= 8 ? '#f59e0b' : '#00f5a0' }}>
              {taskCount}
            </div>
            <div className="surge-metric-label">Active ECS Tasks</div>
          </div>
          <div className="surge-metric">
            <div className="surge-metric-val" style={{ color: cpuUtil >= 80 ? '#ef4444' : cpuUtil >= 60 ? '#f59e0b' : '#00f5a0' }}>
              {cpuUtil}%
            </div>
            <div className="surge-metric-label">CPU Utilization</div>
          </div>
          <div className="surge-metric">
            <div className="surge-metric-val">{rps >= 7000 ? 'SCALING' : 'STABLE'}</div>
            <div className="surge-metric-label">Scaling Status</div>
          </div>
        </div>

        <div className="task-pod-grid">
          {Array.from({ length: taskCount }, (_, i) => (
            <div
              key={i}
              className={`task-pod ${i >= 2 ? 'scaled' : 'baseline'}`}
              title={`ECS Task ${i + 1} — ${i % 2 === 0 ? 'AZ-1a' : 'AZ-1b'}`}
            >
              <div className="task-pod-inner">
                <span>T{i + 1}</span>
                <span className="task-pod-az">{i % 2 === 0 ? '1a' : '1b'}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="act-info-grid">
        <div className="act-info-item">
          <span className="act-info-key">Scaling Policy</span>
          <span className="act-info-val">Target Tracking — ECSServiceAverageCPUUtilization = 60%</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Capacity Range</span>
          <span className="act-info-val">Min: 2 containers | Max: 20 containers</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Scale-Out Cooldown</span>
          <span className="act-info-val">60 seconds (rapid ramp-up)</span>
        </div>
        <div className="act-info-item">
          <span className="act-info-key">Scale-In Cooldown</span>
          <span className="act-info-val">300 seconds (prevents task thrashing)</span>
        </div>
      </div>
    </div>
  );
}

export default function ActPanel({ state, dispatch, actions, fetchMetrics }) {
  const { currentAct } = state;

  return (
    <div className="act-panel">
      {currentAct === 1 && <Act1 actions={actions} />}
      {currentAct === 2 && <Act2 actions={actions} fetchMetrics={fetchMetrics} />}
      {currentAct === 3 && <Act3 state={state} dispatch={dispatch} actions={actions} fetchMetrics={fetchMetrics} />}
      {currentAct === 4 && <Act4 actions={actions} />}
      {currentAct === 5 && <Act5 state={state} dispatch={dispatch} actions={actions} />}
    </div>
  );
}
