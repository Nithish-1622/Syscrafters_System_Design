# ADR-002: Storage Engine Strategy — Polyglot Persistence (SQL vs. NoSQL)

**Status:** Approved  
**Date:** 2026-10-05  
**Author:** Member 1 (System Architect)  
**Deciders:** Core Engineering Team  

---

## 1. Context & Problem Statement
SALESTORM requires data storage that satisfies conflicting demands:
- **Transactional Absolute Correctness:** Inventory balances, payment audit logs, and legal order contracts require strict ACID guarantees, atomic check constraints, and linearizable serialization.
- **Ultra-High Throughput & Low Latency:** Flash-sale contention generates 10,000 to 500,000 operations/sec that require sub-millisecond execution to avoid queuing and gateway timeouts.
- **Flexible Ephemeral State:** Shopping carts, user session locks, and idempotency tokens expire rapidly and have high write churn.

Choosing a single storage engine (e.g., only pure SQL or only pure NoSQL) forces unacceptable compromises: pure SQL chokes on flash write contention, while pure NoSQL introduces eventual consistency anomalies and lacks relational constraints for financial auditability.

---

## 2. Options Considered

### Option 1: Pure Relational Database (PostgreSQL / MySQL for All Data)
- **Description:** Storing catalog, carts, inventory, payments, and orders exclusively in a relational SQL database.
- **Pros:** Strong ACID semantics; foreign key constraints; relational integrity; mature tooling and rich query language.
- **Cons:** A single SQL database row cannot process 10,000 concurrent update locks per second; connection pools and buffer pools exhaust quickly; volatile cart writes pollute the relational transaction log (WAL).

### Option 2: Pure NoSQL Document / Key-Value Store (MongoDB / DynamoDB / Cassandra)
- **Description:** Storing all entities as JSON documents or distributed wide-column rows.
- **Pros:** High write throughput; horizontal partition scaling across shards.
- **Cons:** Eventual consistency risks overselling under concurrent writes; conditional writes in distributed NoSQL across partitions introduce significant tail latency; lacks native foreign keys and relational constraints for legal financial records; complex multi-document transaction semantics.

### Option 3: Polyglot Persistence — Hybrid Redis Cluster + PostgreSQL RDBMS (Selected)
- **Description:** Decoupling high-velocity, ephemeral, and atomic contention state into an in-memory Redis Cluster, while preserving persistent, auditable, and relational business records in PostgreSQL with Transactional Outbox.
- **Pros:** Redis handles atomic Lua decrements and idempotency key checks at wire speed ($< 2\text{ ms}$); PostgreSQL enforces strict ACID constraints, foreign keys, and audit logging for confirmed transactions; best of both worlds.
- **Cons:** Requires explicit cache synchronization and outbox event streaming to prevent state divergence between memory and disk.

---

## 3. Decision
We adopt **Option 3: Polyglot Persistence Strategy**.

Data is distributed according to domain access patterns:
1. **Redis Cluster (In-Memory Engine):**
   - **Entities:** Flash-sale inventory counters, active reservation leases (300s TTL), idempotency request tokens, rate-limiting sliding windows, transient shopping carts.
   - **Guarantees:** Sub-millisecond latency, single-threaded atomic Lua execution, automatic TTL expiry.
2. **PostgreSQL RDBMS (ACID Master Store):**
   - **Entities:** Canonical inventory balances, finalized orders and line items, payment audit records, customer accounts, transactional outbox tables.
   - **Guarantees:** Strict ACID, WAL durability, check constraints (`CHECK (available_quantity >= 0)`), multi-AZ synchronous replication.

---

## 4. Architectural Consequences & Trade-offs

### Positive Consequences:
- **Contention Offloading:** $99\%$ of the 10,000 flash-sale requests are absorbed and resolved in Redis memory without issuing a single database query to PostgreSQL.
- **Durability Where It Counts:** Payments and confirmed orders are written to an enterprise ACID store with complete transactional audit trails.
- **Zero Lock Escalation:** Relational database connections remain idle and healthy, ready to process the 100 legitimate reservation completions smoothly.

### Negative Consequences / Trade-offs:
- **Dual-State Management:** The architecture must handle rare edge cases where Redis commits an atomic reservation, but the subsequent asynchronous write to PostgreSQL fails. 
- **Mitigation:** Redis reservation leases are strictly time-bounded (300s TTL). If uncommitted to PostgreSQL, the lease automatically expires and Redis restores the stock counter.
