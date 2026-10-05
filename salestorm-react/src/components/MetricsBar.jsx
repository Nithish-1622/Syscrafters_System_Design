// SALESTORM 2026 — Live Metrics Status Bar
import React from 'react';

function MetricCard({ label, value, accent, sub }) {
  return (
    <div className="metric-card" style={{ '--accent': accent }}>
      <div className="metric-value" style={{ color: accent }}>{value}</div>
      <div className="metric-label">{label}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

export default function MetricsBar({ metrics, taskCount }) {
  const soldPct = metrics.initial_stock > 0
    ? Math.round((metrics.sold_stock / metrics.initial_stock) * 100)
    : 0;

  return (
    <div className="metrics-bar">
      <MetricCard
        label="Available Stock"
        value={metrics.available_stock}
        accent="#00f5a0"
        sub="Redis Atomic Counter"
      />
      <MetricCard
        label="Reserved"
        value={metrics.reserved_stock}
        accent="#f59e0b"
        sub="5-min TTL Leases"
      />
      <MetricCard
        label="Sold"
        value={metrics.sold_stock}
        accent="#a855f7"
        sub={`${soldPct}% of ${metrics.initial_stock} units`}
      />
      <MetricCard
        label="p99 Latency"
        value={`${metrics.latency_ms}ms`}
        accent="#00f2fe"
        sub="ALB Round-trip"
      />
      <MetricCard
        label="ECS Tasks"
        value={taskCount}
        accent="#ec4899"
        sub="Fargate Replicas"
      />
      <div className="metric-card alb-status">
        <div className="alb-endpoint-label">ALB Endpoint</div>
        <a
          href="http://salestorm-alb-499690526.ap-south-1.elb.amazonaws.com/docs"
          target="_blank"
          rel="noreferrer"
          className="alb-link"
        >
          /docs (Swagger UI)
        </a>
        <div className="alb-region">ap-south-1 (Mumbai)</div>
      </div>
    </div>
  );
}
