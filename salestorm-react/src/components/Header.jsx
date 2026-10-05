// SALESTORM 2026 — Header Component
import React from 'react';
import { AWS_CONFIG } from '../config/aws';

export default function Header({ isLiveMode, setMode, metrics }) {
  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="brand-badge">
          <span className="brand-icon">&#9889;</span>
          <span className="brand-name">SALESTORM</span>
          <span className="brand-year">2026</span>
        </div>
        <div className="brand-meta">
          <h1 className="brand-title">Flash Sale System &mdash; AWS Cloud Architecture Console</h1>
          <p className="brand-sub">
            Region: {AWS_CONFIG.REGION_LABEL} &nbsp;|&nbsp; VPC: {AWS_CONFIG.VPC_CIDR} &nbsp;|&nbsp; ECS Fargate &bull; ALB &bull; Redis &bull; PostgreSQL
          </p>
        </div>
      </div>

      <div className="header-controls">
        <div className="mode-toggle">
          <button
            className={`mode-btn ${isLiveMode ? 'active' : ''}`}
            onClick={() => setMode(true)}
          >
            Live AWS
          </button>
          <button
            className={`mode-btn ${!isLiveMode ? 'active' : ''}`}
            onClick={() => setMode(false)}
          >
            Simulation
          </button>
        </div>

        <div className={`status-pill ${isLiveMode ? 'live' : 'sim'}`}>
          <span className="pulse-dot" />
          {isLiveMode ? 'LIVE AWS (ALB)' : 'SIMULATION MODE'}
        </div>

        <div className="header-latency">
          <span className="latency-label">p99 Latency</span>
          <span className="latency-value">{metrics.latency_ms}ms</span>
        </div>
      </div>
    </header>
  );
}
