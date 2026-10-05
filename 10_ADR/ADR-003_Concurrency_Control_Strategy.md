# ADR-003: Inventory Concurrency Control Strategy

**Status:** Approved  
**Date:** 2026-10-05  
**Author:** Member 1 (System Architect)  
**Deciders:** Core Engineering Team  

---

## 1. Context & Problem Statement
During the SALESTORM flash sale, 10,000 customers concurrently compete for exactly 100 available units of Product X at timestamp $t = 0$. 
The fundamental consistency invariant is:
$$\text{Confirmed Sales} \le \text{Available Units} \implies \le 100\text{ sales}$$
Under no circumstances may stock become negative or oversold. When two requests attempt to claim the final unit ($N = 1$), the concurrency engine must deterministically award the unit to exactly one request and immediately fail the other. 

We must choose a concurrency control paradigm that guarantees absolute consistency while preventing thread starvation, connection pool exhaustion, and latency spikes.

---

## 2. Options Considered

### Option 1: Database Pessimistic Row Locking (`SELECT ... FOR UPDATE`)
- **Description:** Transactions acquire an exclusive lock on the inventory row in PostgreSQL. Each transaction reads the stock, checks if stock $> 0$, decrements stock, and commits.
- **Pros:** Conceptually simple; guaranteed consistency at the database engine level; standard relational feature.
- **Cons:** Serializes 10,000 requests into a single lock wait queue. Application server threads block while waiting for database connections; database connection pools (50–200 connections) are instantly exhausted; response times spike beyond 10,000ms; upstream load balancers throw `504 Gateway Timeout`.

### Option 2: Database Optimistic Concurrency Control (OCC / Version Checking)
- **Description:** Transactions read current stock and integer version $V$. Writes execute:
  ```sql
  UPDATE inventory 
  SET available_quantity = available_quantity - 1, version = version + 1 
  WHERE product_id = 'X' AND version = V AND available_quantity >= 1;
  ```
- **Pros:** Lock-free reads; high throughput when requests access disjoint rows across many products.
- **Cons:** **Catastrophic Failure under Single-Row Contention.** When 10,000 requests target the exact same row simultaneously, exactly 1 request succeeds and 9,999 fail. If retries are implemented, a massive retry storm burns database CPU at 100% with aborts and rollbacks.

### Option 3: Two-Tier Hybrid Concurrency — In-Memory Redis Lua Engine + Database OCC Outbox (Selected)
- **Description:** 
  - **Tier 1:** Single-threaded Redis Lua script executes atomic check-and-decrement in memory at wire speed ($\sim 100,000\text{ ops/sec}$).
  - **Tier 2:** Only the 100 winning reservations write to PostgreSQL using an asynchronous write-behind transactional outbox.
- **Pros:** Eliminates database lock contention completely; deterministic tie-breaking on the last item in $< 1\text{ ms}$; fast-fails the 9,900 losers in $< 50\text{ ms}$; zero database connection saturation.
- **Cons:** Introduces Redis as a critical in-memory component requiring high-availability clustering and replication.

---

## 3. Decision
We adopt **Option 3: Two-Tier Hybrid Concurrency Control**.

### Technical Operation:
1. All 10,000 reservation requests are routed to the Redis Cluster hosting the flash SKU shard.
2. The atomic Lua script runs sequentially on the single-threaded Redis event loop:
   - Reads `stock:item:X`.
   - If stock $\ge 1$, decrements counter and writes a 300s lease into a Redis hash.
   - If stock $< 1$, returns fast-fail code `-1`.
3. The first 100 requests receive success; the subsequent 9,900 requests receive immediate failure.
4. The 100 winning requests are committed to PostgreSQL with a unique `reservation_id` and an active lease expiration timestamp (`NOW() + INTERVAL '5 MINUTE'`).

---

## 4. Architectural Consequences & Trade-offs

### Positive Consequences:
- **Zero Database Lock Contention:** The PostgreSQL database never sees more than 100 reservation writes, completely eliminating row-lock waiting queues.
- **Sub-Millisecond Tie-Breaking:** Redis resolves the race condition for the 100th unit deterministically: the first command in the network buffer wins, the second loses.
- **Fast-Fail User Experience:** 9,900 customers receive instant feedback ("Sold Out") in $< 50\text{ ms}$ rather than hanging for 15 seconds waiting on a database lock timeout.

### Negative Consequences / Trade-offs:
- **Operational Dependency on Redis:** If Redis fails, reservations cannot be processed.
- **Mitigation:** Redis is deployed as a Multi-AZ cluster with synchronous in-memory replication and automated failover via Redis Sentinel / Raft coordinator. If the cluster becomes completely unreachable, the Inventory Service fails closed (rejects all reservations) rather than risking an oversell condition.
