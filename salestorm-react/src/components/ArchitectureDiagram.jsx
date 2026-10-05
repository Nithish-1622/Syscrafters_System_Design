// SALESTORM 2026 — AWS Architecture Diagram (Pure CSS/SVG, No Three.js dependency)
// Shows the multi-tier VPC topology with animated data flow paths
import React, { useRef, useEffect, useState } from 'react';

const LAYERS = [
  {
    id: 'internet',
    label: 'Internet / Clients',
    color: '#00f2fe',
    nodes: [
      { id: 'clients', label: '10K Clients', sub: 'Flash Sale Buyers', x: 50, y: 10 },
    ],
  },
  {
    id: 'edge',
    label: 'Public Subnet (Multi-AZ)',
    color: '#00f5a0',
    nodes: [
      { id: 'alb', label: 'ALB', sub: 'salestorm-alb\nPort 80 → 8080', x: 50, y: 27 },
    ],
  },
  {
    id: 'compute',
    label: 'Private Compute Subnet',
    color: '#0891b2',
    nodes: [
      { id: 'ecs1', label: 'ECS Fargate', sub: 'AZ-1a / :8080', x: 28, y: 44 },
      { id: 'ecs2', label: 'ECS Fargate', sub: 'AZ-1b / :8080', x: 72, y: 44 },
    ],
  },
  {
    id: 'data',
    label: 'Private Data Subnet',
    color: '#7c3aed',
    nodes: [
      { id: 'redis', label: 'ElastiCache\nRedis 7', sub: 'Atomic Lua :6379', x: 28, y: 62 },
      { id: 'rds', label: 'RDS\nPostgreSQL 16', sub: 'ACID Orders :5432', x: 72, y: 62 },
    ],
  },
  {
    id: 'managed',
    label: 'AWS Managed Services',
    color: '#ec4899',
    nodes: [
      { id: 'ecr', label: 'ECR', sub: 'Image Registry', x: 10, y: 80 },
      { id: 'secrets', label: 'Secrets Mgr', sub: 'Credentials', x: 35, y: 80 },
      { id: 'cw', label: 'CloudWatch', sub: 'Logs & Alarms', x: 60, y: 80 },
      { id: 'sns', label: 'SNS', sub: 'Alerts', x: 82, y: 80 },
    ],
  },
];

const CONNECTIONS = [
  { from: { x: 50, y: 14 }, to: { x: 50, y: 23 }, color: '#00f2fe' },
  { from: { x: 50, y: 31 }, to: { x: 28, y: 40 }, color: '#00f5a0' },
  { from: { x: 50, y: 31 }, to: { x: 72, y: 40 }, color: '#00f5a0' },
  { from: { x: 28, y: 48 }, to: { x: 28, y: 58 }, color: '#d97706' },
  { from: { x: 28, y: 48 }, to: { x: 72, y: 58 }, color: '#7c3aed' },
  { from: { x: 72, y: 48 }, to: { x: 28, y: 58 }, color: '#d97706' },
  { from: { x: 72, y: 48 }, to: { x: 72, y: 58 }, color: '#7c3aed' },
  { from: { x: 28, y: 48 }, to: { x: 10, y: 76 }, color: '#f97316' },
  { from: { x: 28, y: 48 }, to: { x: 35, y: 76 }, color: '#b91c1c' },
  { from: { x: 72, y: 48 }, to: { x: 60, y: 76 }, color: '#ec4899' },
  { from: { x: 72, y: 48 }, to: { x: 82, y: 76 }, color: '#db2777' },
];

function ArchNode({ node, layerColor, onClick }) {
  return (
    <div
      className="arch-node"
      style={{
        left: `${node.x}%`,
        top: `${node.y}%`,
        '--node-color': layerColor,
      }}
      onClick={() => onClick && onClick(node.id)}
      title={`Click to inspect: ${node.label}`}
    >
      <div className="arch-node-inner">
        <div className="arch-node-label">{node.label}</div>
        <div className="arch-node-sub">{node.sub}</div>
      </div>
    </div>
  );
}

export default function ArchitectureDiagram({ currentAct, taskCount, openService }) {
  const [animTick, setAnimTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setAnimTick(n => n + 1), 1800);
    return () => clearInterval(t);
  }, []);

  const activeConnIdx = animTick % CONNECTIONS.length;

  return (
    <div className="arch-diagram-wrap">
      <div className="arch-diagram-header">
        <span className="arch-diagram-title">AWS VPC Topology — ap-south-1 (Mumbai)</span>
        <span className="arch-diagram-sub">Click any node to inspect service configuration</span>
      </div>

      <div className="arch-diagram-canvas">
        {/* SVG Connection Lines */}
        <svg className="arch-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
          {CONNECTIONS.map((conn, i) => (
            <line
              key={i}
              x1={`${conn.from.x}%`} y1={`${conn.from.y}%`}
              x2={`${conn.to.x}%`}  y2={`${conn.to.y}%`}
              stroke={conn.color}
              strokeWidth={i === activeConnIdx ? '0.5' : '0.2'}
              strokeDasharray={i === activeConnIdx ? '2 1' : '1 2'}
              opacity={i === activeConnIdx ? 1 : 0.35}
            />
          ))}

          {/* Animated packet dot on active connection */}
          {(() => {
            const conn = CONNECTIONS[activeConnIdx];
            const t = (animTick % 4) / 4;
            const px = conn.from.x + (conn.to.x - conn.from.x) * t;
            const py = conn.from.y + (conn.to.y - conn.from.y) * t;
            return (
              <circle cx={`${px}%`} cy={`${py}%`} r="0.6" fill={conn.color} opacity="0.9" />
            );
          })()}
        </svg>

        {/* Layer Labels */}
        {LAYERS.map(layer => (
          <div
            key={layer.id}
            className="arch-layer-label"
            style={{
              top: `${LAYERS.indexOf(layer) * 20 + 4}%`,
              color: layer.color,
              opacity: 0.5,
            }}
          >
            {layer.label}
          </div>
        ))}

        {/* Nodes */}
        {LAYERS.map(layer =>
          layer.nodes.map(node => (
            <ArchNode
              key={node.id}
              node={node}
              layerColor={layer.color}
              onClick={openService}
            />
          ))
        )}

        {/* Auto-scaling task count badge */}
        <div className="arch-taskcount-badge">
          <span className="taskcount-num">{taskCount}</span>
          <span className="taskcount-label">Active Fargate Tasks</span>
        </div>
      </div>

      {/* Legend */}
      <div className="arch-legend">
        <div className="legend-item"><span style={{ background: '#00f2fe' }} />Client Ingress</div>
        <div className="legend-item"><span style={{ background: '#00f5a0' }} />ALB Public</div>
        <div className="legend-item"><span style={{ background: '#0891b2' }} />ECS Compute</div>
        <div className="legend-item"><span style={{ background: '#d97706' }} />Redis Cache</div>
        <div className="legend-item"><span style={{ background: '#7c3aed' }} />RDS Storage</div>
        <div className="legend-item"><span style={{ background: '#ec4899' }} />Managed Services</div>
      </div>
    </div>
  );
}
