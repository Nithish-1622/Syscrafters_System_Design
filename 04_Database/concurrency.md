# SALESTORM 2026 | Concurrency Control & Hotspot Contention Engineering

## 1. The Central Engineering Challenge

In the SALESTORM practical scenario:
- **Available Stock**: 100 units
- **Simultaneous Contenders**: 10,000 concurrent requests arriving within a ~100ms window
- **Peak Flash-Sale Throughput Target**: Up to 500,000 requests/sec across the distributed ingress

All 10,000 requests target the **exact same product and database row**. If concurrency control is designed incorrectly, the system will suffer from either:
1. **Overselling**: More than 100 units reserved (catastrophic business & legal failure).
2. **Database Thrashing / Lock Starvation**: Connection pool exhaustion, lock wait timeouts, and cascading server crashes.
3. **Optimistic Retry Storms**: 99.9% abort rate forcing hundreds of thousands of retries that consume 100% of database CPU.

---

## 2. In-Depth Comparison of Concurrency Strategies

| Concurrency Model | Mechanism Under 10,000 Concurrent Requests on 1 Row | Latency Under Load | Throughput | Overselling Risk | Evaluation for SALESTORM |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Pessimistic Locking** (`SELECT ... FOR UPDATE`) | Transaction locks row exclusively; 9,999 other transactions wait in the DB lock queue. | Very High (>5,000ms); lock timeout spikes (`57014`). | Poor (~100-200 tx/sec per row). | Zero | **REJECTED**: Causes thread pool exhaustion and HTTP 504 timeouts. |
| **Optimistic Concurrency Control (OCC)** (`WHERE version = :v`) | Reads version; attempts commit with `version = :v`. 1 succeeds; 9,999 fail due to version mismatch. | Spikes exponentially due to application retries. | Collapses under hot contention (<5% efficiency). | Zero | **REJECTED**: Massive retry amplification; CPU thrashing. |
| **Atomic Conditional SQL Update** (`WHERE available_quantity >= :qty`) | Atomic arithmetic decrement directly inside engine page latch; no read-then-write phase. | Low (<15ms per successful reserve). | High (~3,000 - 5,000 tx/sec per physical core). | **Zero (Guaranteed)** | **SELECTED FOR CORE PERSISTENCE**. |
| **Redis In-Memory Token Bucket / Lua Pre-Allocation** | Atomic Lua script in single-threaded Redis memory buffer gates DB requests. | Ultra-Low (<2ms at 500k req/sec with cluster). | Ultra-High (>100,000 ops/sec). | Zero | **SELECTED FOR FLASH-SALE INGRESS ADMISSION**. |

---

## 3. The Authoritative Database Operation: Atomic Conditional SQL Update

To guarantee that exactly 100 units are sold and 0 overselling occurs, SALESTORM executes the following atomic SQL statement:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :requestedQuantity,
    reserved_quantity  = reserved_quantity + :requestedQuantity,
    version            = version + 1,
    updated_at         = CURRENT_TIMESTAMP
WHERE product_id = :productId 
  AND available_quantity >= :requestedQuantity
RETURNING inventory_id, available_quantity, reserved_quantity;
```

### Detailed Execution Mechanics Inside PostgreSQL / ANSI SQL Engine:
1. **Engine Row Latching**: When the database worker executes this statement, it acquires an internal exclusive row write lock on the target tuple.
2. **Atomic Condition Evaluation**: Under `READ COMMITTED` isolation, the engine inspects the latest committed version of the row on disk/buffer pool.
3. **Branching**:
   - **Case A (`available_quantity >= :requestedQuantity`)**: The arithmetic is applied atomically, the row is updated, and the new values are returned. Rows affected = 1.
   - **Case B (`available_quantity < :requestedQuantity`)**: The `WHERE` predicate evaluates to `FALSE`. The engine touches nothing and releases the lock. Rows affected = 0.
4. **No Dirty Reads / No Phantom Reads**: Because the decrement occurs within the update expression itself (`available_quantity - :qty`), there is **no gap** between reading the stock and writing the decrement.

---

## 4. The Final Unit Race (Scenario: 1 Unit Left, 2 Simultaneous Requests)

Consider the critical boundary condition:
- `available_quantity` = 1
- **Request A** (User 1) and **Request B** (User 2) arrive simultaneously at the database.

```mermaid
sequenceDiagram
    autonumber
    participant AppA as Request A (User 1)
    participant DB as PostgreSQL Engine
    participant AppB as Request B (User 2)

    Note over DB: Current State: available_quantity = 1
    AppA->>DB: UPDATE inventory SET available = available - 1 WHERE id = :id AND available >= 1
    AppB->>DB: UPDATE inventory SET available = available - 1 WHERE id = :id AND available >= 1
    
    activate DB
    Note over DB: Lock granted to Request A.<br/>Request B placed in row lock wait queue.
    DB->>DB: Evaluate Request A: 1 >= 1 (TRUE)<br/>available_quantity: 1 -> 0<br/>reserved_quantity: 99 -> 100
    DB-->>AppA: Rows Affected = 1 (SUCCESS!)
    deactivate DB

    activate DB
    Note over DB: Lock released by A; granted to Request B.
    Note over DB: Re-evaluates WHERE clause against newly committed row state:
    DB->>DB: Evaluate Request B: 0 >= 1 (FALSE!)
    Note over DB: No rows updated.
    DB-->>AppB: Rows Affected = 0 (OUT OF STOCK)
    deactivate DB

    AppA-->>AppA: Issue Reservation, Return HTTP 201 Created
    AppB-->>AppB: Rollback, Return HTTP 409 Conflict (Out of Stock)
```

### Result:
- Request A receives 1 row affected and proceeds to payment.
- Request B receives 0 rows affected, immediately terminates with an `OUT_OF_STOCK` domain error, and returns HTTP 409 Conflict.
- **Physical Invariant Maintained**: `available_quantity` reaches exactly 0. It can never become -1.

---

## 5. Hotspot Mitigation at 500,000 Requests/Sec

A single database row locked sequentially cannot process 500,000 writes/sec due to physics and NVMe I/O latching (maximum throughput for a single row in PostgreSQL is ~3,000–5,000 writes/sec).

To achieve 500,000 req/sec flash-sale traffic without collapsing the database, SALESTORM pairs the database with **Layered Hotspot Mitigation**:

```
[ Ingress: 500,000 req/sec ]
              │
              ▼
┌────────────────────────────────────────────────────────┐
│ LEVEL 1: EDGE RATE LIMITING & VIRTUAL WAITING ROOM    │
│ - Drops abusive bots; admits authenticated customers   │
└────────────────────────────────────────────────────────┘
              │ (Admitted: 20,000 req/sec)
              ▼
┌────────────────────────────────────────────────────────┐
│ LEVEL 2: IN-MEMORY REDIS PRE-ALLOCATION (Lua Script)   │
│ - Atomic decrement on Redis counter:                   │
│   if redis.call('get', KEYS[1]) >= ARGV[1] then        │
│       return redis.call('decrby', KEYS[1], ARGV[1])    │
│   else return -1 end                                   │
│ - Rejects 19,900 requests in RAM (<1ms latency)        │
└────────────────────────────────────────────────────────┘
              │ (Only 100 winners proceed to DB!)
              ▼
┌────────────────────────────────────────────────────────┐
│ LEVEL 3: RELATIONAL DATABASE (PostgreSQL)              │
│ - Receives ONLY legitimate reservation transactions    │
│ - Executes atomic conditional SQL update as final guard│
│ - 100% throughput success; zero database contention!   │
└────────────────────────────────────────────────────────┘
```

By placing the atomic Redis gate in front of the database, the database **never sees 500,000 writes/sec** on a single row. It sees only the authorized reservation transactions, completing in milliseconds with mathematical consistency.
