# SALESTORM 2026 | Hotspot Contention Analysis & Scalability Architecture

## 1. The Anatomy of Single-Record Contention (The Flash-Sale Hotspot)

In the SALESTORM scenario:
- **Product**: 1 high-demand item (e.g. flagship phone at 90% discount).
- **Physical Stock**: Exactly 100 units represented by a single database row: `inventory_id = 'inv-001'`.
- **Concurrency**: 10,000 to 500,000 customers clicking "Buy Now" at the exact same millisecond.

### Why Horizontal Database Scaling FAILS on Single-Record Contention:
A common misconception is that "adding more database servers (read replicas or sharding)" solves this problem. **It does not**:
1. **Read Replicas Cannot Process Writes**: Replicas asynchronously replicate data from the primary writer. Directing stock reservation writes to replicas causes dirty reads and catastrophic overselling.
2. **Sharding Does Not Divide a Single Key**: Database sharding partitions records by key (e.g., `product_id`). All 10,000 requests target the *exact same product key*, mapping to the *exact same database shard*!
3. **Physical NVMe / Row Latching Limits**: At the storage engine level, updating a single row requires an exclusive page latch and write-ahead log (WAL) sync. PostgreSQL can physically commit ~3,000 to 5,000 write operations per second on a single row before lock queue contention causes latency degradation.

---

## 2. Multi-Tiered Contention Control Architecture

SALESTORM solves single-record contention through a **Hierarchical Defense Pyramid**:

```
[ Ingress Peak: 500,000 req/sec ]
                │
                ▼
┌────────────────────────────────────────────────────────┐
│ LEVEL 1: EDGE TRAFFIC SHAPING (Virtual Waiting Room)   │
│ - Smooths burst into a stable queue                    │
│ - Rejects abusive bot requests before origin           │
└────────────────────────────────────────────────────────┘
                │ (Controlled stream: 20,000 req/sec)
                ▼
┌────────────────────────────────────────────────────────┐
│ LEVEL 2: IN-MEMORY REDIS PRE-ALLOCATION GATE           │
│ - Redis Cluster counter initialized with 100 tokens    │
│ - Atomic Lua Script decrements counter in RAM (<0.5ms) │
│ - 19,900 losers rejected IMMEDIATELY in memory!        │
└────────────────────────────────────────────────────────┘
                │ (ONLY 100 WINNERS REACH THE DATABASE!)
                ▼
┌────────────────────────────────────────────────────────┐
│ LEVEL 3: RELATIONAL DATABASE (PostgreSQL)              │
│ - Receives exactly ~100-110 reservation transactions   │
│ - Executes atomic conditional SQL update as final guard│
│ - DB Latency: < 3ms; Lock Queue Depth: < 5 connections │
│ - Zero overselling guaranteed with 100% ACID safety!   │
└────────────────────────────────────────────────────────┘
```

---

## 3. Database Scalability Techniques Evaluation

| Technique | When Needed? | Problem It Solves | Complexity Introduced | Decision for SALESTORM |
| :--- | :--- | :--- | :--- | :--- |
| **Read Replicas** | High catalog browsing read volume (>10k req/sec). | Offloads read traffic from primary database. | Replication lag (50-200ms); stale catalog data. | **ADOPTED FOR CATALOG READS ONLY**. Excluded from reservation writes. |
| **In-Memory Caching (Redis)** | High-frequency product metadata and stock availability indicators. | Sub-millisecond reads; absorbs 95% of product page views. | Cache invalidation complexity; potential cache stampede. | **ADOPTED WITH SHORT TTL (2s)** + Cache stampede mutex locks. |
| **Connection Pooling (PgBouncer)** | When thousands of application threads connect to PostgreSQL. | Prevents process-forking overhead and RAM exhaustion. | Session-level features disabled if transaction pooling used. | **MANDATORY**: Caps active DB connections to 100 physical connections. |
| **Table Partitioning** | High-volume append-only tables (`audit_logs`, `idempotency_records`). | Eliminates vacuum bloat; enables instant zero-cost partition dropping. | Partition routing overhead; cross-partition queries slow. | **ADOPTED FOR AUDIT & IDEMPOTENCY TABLES**. |
| **Batch Operations** | Outbox event relaying and background expiry cleanup. | Reduces network roundtrips and WAL write volume. | Lock holding duration if batch is too large. | **ADOPTED WITH STRICT BATCH CAPS (LIMIT 500)**. |
| **Database Sharding** | When total catalog exceeds 100M+ distinct SKUs across thousands of categories. | Horizontal write scaling across distinct products. | Cross-shard transactions, distributed queries, re-sharding. | **DEFERRED (PREMATURE COMPLEXITY)**: A single high-spec RDS instance comfortably handles 100k products. |
