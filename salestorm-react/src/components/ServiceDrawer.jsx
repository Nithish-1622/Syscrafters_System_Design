// SALESTORM 2026 — AWS Service Detail Drawer
import React from 'react';
import { AWS_SERVICES } from '../config/aws';

export default function ServiceDrawer({ serviceId, onClose }) {
  const svc = AWS_SERVICES[serviceId];
  if (!svc) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="service-drawer" onClick={(e) => e.stopPropagation()} style={{ '--svc-color': svc.color }}>
        <div className="drawer-header" style={{ borderColor: svc.color }}>
          <div className="drawer-title-row">
            <span className="drawer-badge" style={{ background: svc.bgColor, color: svc.color }}>
              {svc.category}
            </span>
            <button className="drawer-close" onClick={onClose}>&#10005;</button>
          </div>
          <h2 className="drawer-service-name" style={{ color: svc.color }}>{svc.fullName}</h2>
        </div>

        <div className="drawer-body">
          <div className="drawer-section">
            <div className="drawer-section-title">Purpose in SALESTORM</div>
            <p className="drawer-text">{svc.purpose}</p>
          </div>

          <div className="drawer-section">
            <div className="drawer-section-title">Key Advantage</div>
            <p className="drawer-text highlight">{svc.advantage}</p>
          </div>

          <div className="drawer-spec-grid">
            <div className="drawer-spec-item">
              <span className="drawer-spec-key">Ports / Protocol</span>
              <span className="drawer-spec-val">{svc.ports}</span>
            </div>
            <div className="drawer-spec-item">
              <span className="drawer-spec-key">Security Group / Policy</span>
              <span className="drawer-spec-val">{svc.securityGroup}</span>
            </div>
            <div className="drawer-spec-item">
              <span className="drawer-spec-key">Subnets / Placement</span>
              <span className="drawer-spec-val">{svc.subnets}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
