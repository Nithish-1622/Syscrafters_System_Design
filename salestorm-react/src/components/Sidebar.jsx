// SALESTORM 2026 — AWS Services Sidebar
import React from 'react';
import { AWS_SERVICES } from '../config/aws';

const SERVICE_ICON_MAP = {
  network: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="5" r="3"/><circle cx="19" cy="19" r="3"/><circle cx="5" cy="19" r="3"/>
      <line x1="12" y1="8" x2="19" y2="16"/><line x1="12" y1="8" x2="5" y2="16"/>
    </svg>
  ),
  shield: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  package: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
      <polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>
    </svg>
  ),
  key: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
    </svg>
  ),
  lock: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
      <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  ),
  database: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
    </svg>
  ),
  zap: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
    </svg>
  ),
  'git-fork': (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>
      <path d="M18 9a9 9 0 0 1-9 9"/><line x1="6" y1="9" x2="6" y2="15"/>
    </svg>
  ),
  cpu: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>
      <line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/>
      <line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>
      <line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/>
      <line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>
    </svg>
  ),
  activity: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  ),
  bell: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
      <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  ),
  'trending-up': (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
      <polyline points="17 6 23 6 23 12"/>
    </svg>
  ),
};

export default function Sidebar({ activeServiceId, openService }) {
  const services = Object.values(AWS_SERVICES);

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">AWS Services</span>
        <span className="sidebar-count">{services.length} Active</span>
      </div>

      <div className="sidebar-services">
        {services.map((svc) => (
          <button
            key={svc.id}
            className={`sidebar-service-btn ${activeServiceId === svc.id ? 'active' : ''}`}
            style={{ '--svc-color': svc.color }}
            onClick={() => openService(svc.id)}
            title={svc.fullName}
          >
            <span className="svc-icon" style={{ color: svc.color }}>
              {SERVICE_ICON_MAP[svc.icon] || SERVICE_ICON_MAP.cpu}
            </span>
            <span className="svc-label">{svc.name}</span>
            <span className="svc-dot" style={{ background: svc.color }} />
          </button>
        ))}
      </div>

      <div className="sidebar-infra-info">
        <div className="infra-row">
          <span className="infra-key">VPC CIDR</span>
          <span className="infra-val">10.0.0.0/16</span>
        </div>
        <div className="infra-row">
          <span className="infra-key">Public Subnets</span>
          <span className="infra-val">AZ-1a, AZ-1b</span>
        </div>
        <div className="infra-row">
          <span className="infra-key">Private Subnets</span>
          <span className="infra-val">AZ-1a, AZ-1b</span>
        </div>
        <div className="infra-row">
          <span className="infra-key">Compute</span>
          <span className="infra-val">ECS Fargate</span>
        </div>
        <div className="infra-row">
          <span className="infra-key">Replicas</span>
          <span className="infra-val">2 - 20 tasks</span>
        </div>
      </div>
    </aside>
  );
}
