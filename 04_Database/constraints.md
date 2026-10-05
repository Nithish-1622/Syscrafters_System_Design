# SALESTORM 2026 | Database Constraints & Invariant Enforcement

## 1. Executive Invariant Philosophy

In distributed high-concurrency systems, **application-level validation alone is insufficient**. Race conditions, network partitions, split-brain nodes, or transient application thread crashes can bypass in-memory guards.

Therefore, SALESTORM implements a **Defense-in-Depth Invariant Architecture**:
1. **Application Layer (Fast-Path Filter)**: Immediate memory bounds checks, schema parsing, and optimistic rejection to shield the database from unnecessary load.
2. **Database Engine (Authoritative Guard)**: Declarative SQL `CHECK`, `UNIQUE`, and `FOREIGN KEY` constraints acting as the immutable physical safety net. Any transaction violating physical consistency is aborted by the database engine with an explicit constraint error.

---

## 2. Inventory Invariant Matrix

The central engineering requirement of SALESTORM is:
$$\text{Successful Sales} \le \text{Initial Available Inventory}$$

| Invariant | Where Enforced? | Mechanism | Failure / Violation Behavior |
| :--- | :--- | :--- | :--- |
| **`available_quantity >= 0`** | Database & Application | SQL `CHECK (available_quantity >= 0)` + Atomic `WHERE available_quantity >= :qty` | Database rejects update with `check_violation` (SQLSTATE 23514); API returns HTTP 409 Out of Stock. |
| **`reserved_quantity >= 0`** | Database & Application | SQL `CHECK (reserved_quantity >= 0)` | Prevents release of non-existent reservations. |
| **`sold_quantity >= 0`** | Database & Application | SQL `CHECK (sold_quantity >= 0)` | Prevents negative sold counters. |
| **Quantity Conservation Law**: $\text{avail} + \text{resv} + \text{sold} = \text{total}$ | Database | SQL `CHECK (available_quantity + reserved_quantity + sold_quantity = total_quantity)` | Any arithmetic leak immediately rolls back the SQL transaction. |
| **Reservation Cannot Be Confirmed Twice** | Database & Application | State Machine check (`WHERE status = 'RESERVED'`) + Unique Order-Reservation constraint | Second update returns 0 affected rows; idempotent HTTP 200 returned if already confirmed. |
| **Reservation Cannot Be Released Twice** | Database & Application | Atomic conditional update (`WHERE status = 'RESERVED'`) | Subsequent release requests match zero rows; no inventory decrement or duplicate release occurs. |
| **Duplicate Reservation Request Rejection** | Database & Application | `idempotency_key VARCHAR(128) UNIQUE` on `inventory_reservations` table | Database rejects duplicate insert with `unique_violation` (SQLSTATE 23505); returns cached original hold. |
| **Payment Provider Transaction Uniqueness**| Database | `provider_transaction_id VARCHAR(128) UNIQUE` on `payments` | Prevents duplicate charge recording across retried webhooks. |

---

## 3. Explicit Constraint Catalog

### 3.1 Primary & Foreign Key Constraints
- **Primary Keys**: All core tables use 128-bit UUIDs (`gen_random_uuid()`) or BIGSERIAL (`audit_logs`). UUIDs eliminate central sequence generator contention across distributed write nodes.
- **Foreign Keys**:
  - `inventory(product_id)`: `ON DELETE RESTRICT` (Guarantees inventory is never orphaned).
  - `inventory_reservations(inventory_id)`: `ON DELETE RESTRICT` (Protects active holds).
  - `orders(reservation_id)`: `UNIQUE NOT NULL ON DELETE RESTRICT` (1-to-1 order-to-reservation guarantee).
  - `order_items(order_id)`: `ON DELETE CASCADE` (Line items belong strictly to the order aggregate).

### 3.2 Unique Constraints
- `customers(email)`: Prevents duplicate accounts.
- `inventory(product_id)`: Enforces single inventory row per SKU to avoid split stock buckets.
- `inventory_reservations(idempotency_key)`: Guarantees exactly one reservation record per client intent.
- `orders(order_number)`: Enforces unique human-readable tracking identifiers.
- `orders(reservation_id)`: Ensures an inventory reservation is consumed at most once.
- `payments(idempotency_key)`: Guarantees duplicate payment API calls cannot initiate multiple bank charges.
- `payments(provider_transaction_id)`: Deduplicates webhook deliveries from payment gateways.

### 3.3 Check Constraints (Domain Sanity)
```sql
-- Inventory Integrity
CONSTRAINT chk_inventory_quantities_balance 
    CHECK (available_quantity + reserved_quantity + sold_quantity = total_quantity);
CONSTRAINT chk_inventory_avail_positive CHECK (available_quantity >= 0);
CONSTRAINT chk_inventory_resv_positive CHECK (reserved_quantity >= 0);
CONSTRAINT chk_inventory_sold_positive CHECK (sold_quantity >= 0);

-- Financial Integrity
CONSTRAINT chk_product_price_positive CHECK (base_price >= 0);
CONSTRAINT chk_order_amount_positive CHECK (total_amount >= 0);
CONSTRAINT chk_payment_amount_positive CHECK (amount > 0);
CONSTRAINT chk_order_item_qty_positive CHECK (quantity > 0);

-- Time-Window Integrity
CONSTRAINT chk_deal_time_window CHECK (ends_at > starts_at);
```

---

## 4. Database Constraints vs Application Domain Validation

A common architectural anti-pattern is assuming either the database or the application can handle all consistency. SALESTORM establishes clear boundaries:

```
[ Incoming Request ]
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ APPLICATION DOMAIN VALIDATION                          │
│ - Request structure, syntax, and schema types          │
│ - User authentication & JWT claims                     │
│ - Business eligibility (e.g. 1 unit per customer rule) │
│ - Fast in-memory cache check (Redis inventory gauge)   │
└────────────────────────────────────────────────────────┘
         │ (Passed application checks)
         ▼
┌────────────────────────────────────────────────────────┐
│ DATABASE ATOMIC EXECUTION & ENGINE CONSTRAINTS         │
│ - Atomic WHERE condition (available_quantity >= qty)   │
│ - Row-level locking & serial transition                │
│ - Unique constraints (Idempotency key uniqueness)      │
│ - CHECK constraints (Mathematical balance law)         │
│ - ACID commit or rollback                              │
└────────────────────────────────────────────────────────┘
```

### Why Both Are Essential:
1. **Application handles context**: The database does not know if a user has exceeded promotional voucher terms or whether a client IP is blacklisted.
2. **Database handles race conditions**: Under 10,000 concurrent threads, 500 threads may simultaneously read `available = 1` in application memory. Only the database conditional atomic update `UPDATE inventory SET available = available - 1 WHERE available >= 1` can guarantee that exactly ONE transaction succeeds and 499 fail.
