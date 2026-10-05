// SALESTORM 2026 — React port of the original three-scene.js
// Initialised once in a useEffect and exposed via ref

const AWS_CONFIG = {
  ALB_URL: 'http://salestorm-alb-499690526.ap-south-1.elb.amazonaws.com',
  PRODUCT_ID: '550e8400-e29b-41d4-a716-446655440000',
  CUSTOMER_ID: '00000000-0000-0000-0000-000000000001',
};

export const AWS_SERVICES_CATALOG = {
  clients: {
    name: '10,000 Flash-Sale Clients',        category: 'Ingress & Client Applications',
    ports: 'HTTPS (443)',                      securityGroup: 'Public Internet (0.0.0.0/0)',
    subnets: 'Global Network',
    purpose: '10,000 concurrent buyers competing for 100 available units at timestamp zero.',
    advantage: 'Sub-150ms p99 response time target under extreme contention.',
  },
  route53: {
    name: 'Amazon Route 53',                  category: 'Networking & Content Delivery',
    ports: 'DNS (53)',                         securityGroup: 'AWS Global Anycast',
    subnets: 'Global Edge PoPs',
    purpose: 'Authoritative DNS resolution with latency-based routing and health-check failover.',
    advantage: 'Sub-millisecond DNS resolution across Asia-Pacific.',
  },
  'cloudfront-waf': {
    name: 'CloudFront CDN + AWS WAF',          category: 'Security & Edge Shield',
    ports: 'HTTPS (443) / TLS 1.3',           securityGroup: 'salestorm-waf-policy',
    subnets: 'Global Edge Network',
    purpose: 'Scrubs malicious bots, mitigates DDoS attacks, and enforces rate limit of 2,000 req/5min per IP.',
    advantage: 'Offloads 85%+ static traffic; blocks automated scraping before reaching the VPC.',
  },
  alb: {
    name: 'Application Load Balancer (salestorm-alb)', category: 'Networking & Content Delivery',
    ports: 'Port 80 → 443 → Target 8080',    securityGroup: 'salestorm-alb-sg (Ingress 80/443 from 0.0.0.0/0)',
    subnets: 'Public: 10.0.1.0/24 (AZ-1a) & 10.0.2.0/24 (AZ-1b)',
    purpose: 'Layer 7 routing, cross-zone load balancing, active /health monitoring every 30s.',
    advantage: 'Zero-downtime rolling deployments; immediately drains unhealthy container replicas.',
  },
  'ecs-cluster': {
    name: 'Amazon ECS Fargate (salestorm-api-service)', category: 'Containers / Serverless Compute',
    ports: 'Port 8080 (tg-salestorm-api)',    securityGroup: 'salestorm-ecs-sg (8080 ONLY from alb-sg)',
    subnets: 'Private: 10.0.10.0/24 (AZ-1a) & 10.0.11.0/24 (AZ-1b)',
    purpose: 'Serverless container execution running FastAPI microservices and outbox relay workers.',
    advantage: 'Zero EC2 OS maintenance; auto-scales 2 → 20 containers on CPU threshold.',
  },
  'elasticache-redis': {
    name: 'Amazon ElastiCache (Redis 7)',      category: 'Databases / In-Memory Cache',
    ports: 'Port 6379 (RESP Protocol)',        securityGroup: 'salestorm-redis-sg (6379 ONLY from ecs-sg)',
    subnets: 'salestorm-redis-subnet (Private AZ-1a & 1b)',
    purpose: 'Atomic Lua script inventory decrement engine and 300-second reservation lease TTL.',
    advantage: 'Sub-millisecond wire-speed atomicity; mathematically guarantees zero overselling.',
  },
  'rds-postgres': {
    name: 'Amazon RDS (PostgreSQL 16 Multi-AZ)', category: 'Databases / ACID Persistence',
    ports: 'Port 5432 (PostgreSQL Wire)',      securityGroup: 'salestorm-rds-sg (5432 ONLY from ecs-sg)',
    subnets: 'salestorm-db-subnet-group (Private AZ-1a & 1b)',
    purpose: 'ACID storage for financial orders, payments, reservation audit trails, Transactional Outbox.',
    advantage: 'CHECK (available_quantity >= 0) at engine level. Sub-60s automated failover.',
  },
  ecr: {
    name: 'Amazon Elastic Container Registry (ECR)', category: 'Containers / Image Registry',
    ports: 'HTTPS (443) via IAM Auth',         securityGroup: 'AWS Internal Backbone / VPC Endpoints',
    subnets: 'Regional: ap-south-1',
    purpose: 'Immutable Docker image storage (salestorm:latest) with CVE scanning on push.',
    advantage: 'High-speed layer ingestion directly to ECS Fargate within the same region.',
  },
  'secrets-manager': {
    name: 'AWS Secrets Manager',               category: 'Security, Identity & Compliance',
    ports: 'HTTPS (443) via KMS CMK',          securityGroup: 'AWS Internal / PrivateLink',
    subnets: 'Regional: ap-south-1',
    purpose: 'Runtime dynamic credential injection (DATABASE_URL, REDIS_URL) without plaintext exposure.',
    advantage: 'Zero-Secret Invariant: No credentials in Git, Dockerfiles, or disk at any point.',
  },
  cloudwatch: {
    name: 'Amazon CloudWatch Logs & Metrics',  category: 'Management & Governance',
    ports: 'HTTPS (443) via awslogs driver',   securityGroup: 'VPC Endpoint / CloudWatch API',
    subnets: 'Log Group: /ecs/salestorm-api',
    purpose: 'Centralized JSON logs with X-Correlation-ID tracing and p99 latency alarms.',
    advantage: 'End-to-end request tracing across distributed container replicas.',
  },
  sns: {
    name: 'Amazon Simple Notification Service (SNS)', category: 'Application Integration',
    ports: 'HTTPS (443)',                      securityGroup: 'Topic: salestorm-alerts',
    subnets: 'Regional: ap-south-1',
    purpose: 'Automated alarm target dispatching real-time outage alerts to engineering on-call.',
    advantage: 'Immediate escalation when CPU > 80%, 5xx errors spike, or DB storage runs low.',
  },
  autoscaling: {
    name: 'AWS Application Auto Scaling',      category: 'Compute & Scaling Policy',
    ports: 'Internal ECS Coordination',        securityGroup: 'Target Tracking: salestorm-cpu-scale-out',
    subnets: 'VPC-Wide Coordination',
    purpose: 'Target tracking at 60% CPU, dynamically provisioning from 2 up to 20 containers.',
    advantage: 'Handles sudden 50x flash sale traffic surges with zero manual intervention.',
  },
};

export default AWS_CONFIG;
