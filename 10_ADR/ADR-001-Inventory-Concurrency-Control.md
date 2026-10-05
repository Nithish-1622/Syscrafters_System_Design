# ADR-001: Inventory Concurrency Control & Atomic Reservation Strategy

## Status: ACCEPTED
**Date**: October 2026  
**Authors**: Member 3 (Database Engineer), in consultation with Member 1 (System Architect)

---

## Context & Problem Statement
During a flash-sale event, 10,000 to 500,000 concurrent requests compete for 100 inventory units on a single database row. The system must guarantee:
1. **Zero Overselling**: Exactly $\le 100$ units sold.
2. **High Throughput & Low Latency**: Minimize database lock contention and thread starvation.
3. **No Deadlocks or Retry Cascades**: Avoid CPU thrashing under extreme load.

---

## Decision
We select **Atomic Conditional SQL Updates** (`UPDATE inventory SET available = available - :qty WHERE product_id = :id AND available >= :qty`) backed by a **Pre-Allocation In-Memory Redis Lua Gate** at the ingress layer.

We explicitly reject:
1. **Pessimistic Locking (`SELECT ... FOR UPDATE`)**: Creates extreme queue depth, thread starvation, and connection timeouts under 10,000 concurrent connections.
2. **Optimistic Concurrency Control (OCC) (`WHERE version = :v`)**: Under hot-spot contention on 1 row, 99.9% of concurrent transactions fail their version check, causing a catastrophic application retry storm and CPU collapse.

---

## Consequences

### Positive:
- **Mathematical Invariant Guaranteed**: PostgreSQL engine latching guarantees that the row condition is evaluated atomically. When stock hits 0, updates cleanly affect 0 rows with zero lock wait timeouts.
- **Sub-Millisecond Rejection for Excess Load**: Redis Lua pre-allocation rejects 99% of requests in memory, ensuring that only eligible reservation contenders reach the relational database.
- **Zero Application-Level Retry Storms**: Eliminates retry cascades.

### Negative / Trade-Offs:
- **Redis Cache Coordination**: If Redis crashes, stock counters must be repopulated from PostgreSQL.
- **Slight Overhead on Redis Cluster**: Redis must maintain high availability (Sentinel or Multi-AZ Cluster).
