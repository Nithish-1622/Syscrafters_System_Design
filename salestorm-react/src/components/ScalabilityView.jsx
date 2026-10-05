// SALESTORM 2026 — System Scalability & HLD View
import React from 'react';

const DESIGN_PILLARS = [
  {
    title: 'Scarcity Boundary',
    color: '#d97706',
    items: [
      'Redis Lua atomic DECR script — single-threaded serialization',
      'No pessimistic row locks — eliminates connection pool exhaustion',
      '300s TTL reservation lease auto-releases unpaid stock',
      'Zero-overselling mathematical invariant: counter <= 0 rejects all',
    ],
  },
  {
    title: 'Async Fulfillment Pipeline',
    color: '#7c3aed',
    items: [
      'Transactional Outbox Pattern — events written inside DB transaction',
      'Outbox relay worker polls and publishes to Kafka message queue',
      'Idempotent Inbox consumer prevents duplicate order processing',
      'At-least-once delivery with idempotency key deduplication',
    ],
  },
  {
    title: 'Zero-Trust Security',
    color: '#ef4444',
    items: [
      '4-tier security group chain: ALB-SG → ECS-SG → RDS-SG / Redis-SG',
      'Zero public internet access to RDS or ElastiCache',
      'AWS Secrets Manager — runtime KMS-encrypted credential injection',
      'IAM least-privilege execution role per task definition',
    ],
  },
  {
    title: 'Horizontal Scalability',
    color: '#0891b2',
    items: [
      'ECS Fargate: 2 baseline to 20 maximum containers',
      'Target tracking on ECSServiceAverageCPUUtilization = 60%',
      'ALB distributes across AZ-1a and AZ-1b simultaneously',
      'Scale-out cooldown: 60s | Scale-in cooldown: 300s',
    ],
  },
  {
    title: 'Observability Stack',
    color: '#ec4899',
    items: [
      'X-Correlation-ID injected per request for distributed tracing',
      'CloudWatch /ecs/salestorm-api log group: JSON structured logs',
      '3 CloudWatch alarms: HighCPU, High5xx, LowDBStorage',
      'SNS topic salestorm-alerts routes to on-call email in seconds',
    ],
  },
  {
    title: 'Data Layer Resilience',
    color: '#16a34a',
    items: [
      'RDS Multi-AZ subnet group (AZ-1a + AZ-1b) with sub-60s failover',
      'ElastiCache Redis subnet group spanning both private AZs',
      'CHECK (available_quantity >= 0) enforced at database engine level',
      'Automated RDS backup retention and patch management',
    ],
  },
];

export default function ScalabilityView() {
  return (
    <div className="scalability-view">
      <div className="scalability-header">
        <span className="scalability-title">System Design Architecture Pillars</span>
        <span className="scalability-sub">High-level engineering decisions that make SALESTORM production-grade</span>
      </div>

      <div className="pillar-grid">
        {DESIGN_PILLARS.map((pillar) => (
          <div key={pillar.title} className="pillar-card" style={{ '--pillar-color': pillar.color }}>
            <div className="pillar-title" style={{ color: pillar.color }}>
              <span className="pillar-dot" style={{ background: pillar.color }} />
              {pillar.title}
            </div>
            <ul className="pillar-list">
              {pillar.items.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
