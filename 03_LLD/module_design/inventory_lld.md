# Inventory & Reservation Service — Low-Level Design

## 1. Service Overview & Problem Scope

The **Inventory & Reservation Service** is the most concurrency-critical component in SALESTORM.
Under peak flash-sale conditions, **10,000 customers concurrently compete for 100 available units**.

The service is strictly responsible for:
1. Guaranteeing **zero overselling** under arbitrary concurrency contention.
2. Managing the complete **Reservation Lifecycle** (`AVAILABLE` → `RESERVED` → `PAYMENT_PENDING` → `CONFIRMED` → `SOLD` / `RELEASED`).
3. Guaranteeing **request-level idempotency** to prevent double reservation for duplicate client retries.
4. Enforcing **automatic expiration and asynchronous release** of unpurchased reservation holds (TTL sweep).
5. Publishing domain events to trigger downstream Checkout, Order, and Notification pipelines.

---

## 2. Hexagonal Domain Architecture & Layer Separation

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           INVENTORY SERVICE BOUNDARY                            │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                        API / Presentation Layer                         │   │
│   │   [InventoryController]            [ReservationController]              │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                       Application Service Layer                         │   │
│   │   [ReservationApplicationService]    [ReservationExpiryScheduler]       │   │
│   │   [IdempotencyInterceptor]           [InventoryQueryService]            │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                             Domain Layer                                │   │
│   │   Entities:   [InventoryItem]       [InventoryReservation]              │   │
│   │   Value Obj:  [ProductId]  [ReservationId]  [StockQuantity]  [TTL]      │   │
│   │   Enums:      [ReservationStatus]   [StockMovementType]                 │   │
│   │   Exceptions: [InsufficientStockException] [ReservationExpiredException]│   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                           Ports (SPI Interfaces)                        │   │
│   │   [IInventoryRepository]           [IReservationRepository]             │   │
│   │   [IIdempotencyStore]              [IEventPublisher]                    │   │
│   │   [IDistributedLockProvider]       [ITimeProvider]                      │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                        Adapters (Infrastructure)                        │   │
│   │   [PostgresInventoryRepository]    [PostgresReservationRepository]      │   │
│   │   [RedisIdempotencyStore]          [KafkaEventPublisher]                │   │
│   │   [RedisDistributedLockProvider]   [SystemTimeProvider]                 │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Class & Interface Specification

### 3.1 Domain Entities & Value Objects

#### `InventoryItem` (Aggregate Root)
- **Attributes:**
  - `productId: ProductId` (Immutable Value Object)
  - `totalQuantity: Int` (Total stock physically allocated to warehouse/sale)
  - `availableQuantity: Int` (Currently claimable stock: $available = total - reserved - sold$)
  - `reservedQuantity: Int` (Currently held in active reservations)
  - `soldQuantity: Int` (Confirmed purchased units)
  - `version: Long` (Optimistic locking version counter)
  - `updatedAt: Instant`
- **Invariants Enforced:**
  - $availableQuantity \ge 0$
  - $reservedQuantity \ge 0$
  - $soldQuantity \ge 0$
  - $totalQuantity = availableQuantity + reservedQuantity + soldQuantity$
- **Methods:**
  - `canReserve(requestedQty: Int): Boolean`
  - `reserve(requestedQty: Int): ReservationResult` — Throws `InsufficientStockException` if $requestedQty > availableQuantity$. Decrements available, increments reserved.
  - `confirmSale(reservedQty: Int): Unit` — Decrements reserved, increments sold.
  - `releaseReservation(reservedQty: Int): Unit` — Decrements reserved, increments available.

#### `InventoryReservation` (Entity)
- **Attributes:**
  - `reservationId: ReservationId` (UUID v4)
  - `idempotencyKey: IdempotencyKey`
  - `productId: ProductId`
  - `userId: UserId`
  - `quantity: Int`
  - `status: ReservationStatus` (`RESERVED`, `PAYMENT_PENDING`, `CONFIRMED`, `EXPIRED`, `RELEASED`, `CANCELLED`)
  - `reservedAt: Instant`
  - `expiresAt: Instant` (Default: `reservedAt + 10 minutes`)
  - `confirmedAt: Optional[Instant]`
- **Methods:**
  - `isExpired(now: Instant): Boolean`
  - `markPaymentPending(): Unit`
  - `confirm(): Unit` — Transitions to `CONFIRMED`. Throws `InvalidStateTransitionException` if status $\ne$ `RESERVED` and $\ne$ `PAYMENT_PENDING`.
  - `expire(): Unit` — Transitions to `EXPIRED`.
  - `release(): Unit` — Transitions to `RELEASED`.

---

### 3.2 Ports / Interfaces (SPI)

```java
public interface IInventoryRepository {
    Optional<InventoryItem> findByProductId(ProductId productId);
    
    // Concurrency-critical atomic update in SQL
    // UPDATE inventory SET available_quantity = available_quantity - :qty, reserved_quantity = reserved_quantity + :qty, version = version + 1 WHERE product_id = :id AND available_quantity >= :qty
    boolean reserveStockAtomic(ProductId productId, int quantity);
    
    // Release stock on timeout / payment failure
    // UPDATE inventory SET available_quantity = available_quantity + :qty, reserved_quantity = reserved_quantity - :qty, version = version + 1 WHERE product_id = :id AND reserved_quantity >= :qty
    boolean releaseStockAtomic(ProductId productId, int quantity);
    
    // Finalize sale on payment success
    // UPDATE inventory SET reserved_quantity = reserved_quantity - :qty, sold_quantity = sold_quantity + :qty, version = version + 1 WHERE product_id = :id AND reserved_quantity >= :qty
    boolean confirmSaleAtomic(ProductId productId, int quantity);
    
    void save(InventoryItem item);
}
```

```java
public interface IReservationRepository {
    Optional<InventoryReservation> findById(ReservationId id);
    Optional<InventoryReservation> findByIdempotencyKey(IdempotencyKey key);
    List<InventoryReservation> findActiveExpiredReservations(Instant cutoffTime, int batchSize);
    void save(InventoryReservation reservation);
    boolean updateStatusIfCurrent(ReservationId id, ReservationStatus current, ReservationStatus next);
}
```

```java
public interface IIdempotencyStore {
    // Atomic SETNX / check-and-set with TTL
    IdempotencyStatus checkOrLock(String idempotencyKey, String requestFingerprint, Duration lockTtl);
    void storeResult(String idempotencyKey, Object resultPayload, Duration resultTtl);
    Optional<Object> getResult(String idempotencyKey);
}
```

```java
public interface IEventPublisher {
    void publish(DomainEvent event);
}
```

---

### 3.3 Application Services

#### `ReservationApplicationService`
- **Responsibilities:**
  - Orchestrates the full lifecycle of reservation creation, confirmation, and release.
  - Implements the **Idempotency Guard**: checks if the incoming `Idempotency-Key` was already executed. If so, returns the cached `ReservationResponseDTO` without re-executing stock mutation.
  - Executes database transaction with conditional row-level atomic decrement.
  - Dispatches `InventoryReservedEvent` or `InventoryOutOfStockEvent` to the event broker.

#### `ReservationExpiryScheduler`
- **Responsibilities:**
  - Scheduled worker running every $N$ seconds (e.g., every 5 seconds).
  - Queries `IReservationRepository.findActiveExpiredReservations(now, batchSize=500)`.
  - For each expired reservation:
    1. Atomically sets status to `EXPIRED` using CAS (`updateStatusIfCurrent(id, RESERVED, EXPIRED)`).
    2. Calls `IInventoryRepository.releaseStockAtomic(productId, qty)` to return available units.
    3. Publishes `ReservationExpiredEvent(reservationId, productId, qty)`.
  - If node crashes halfway through batch, the next run picks up unreleased records safely (idempotent state transition).

---

## 4. Concurrency Control Strategy: Defense & Analysis

### 4.1 Comparison of Alternatives for 10,000 Concurrent Requests on 100 Units

| Concurrency Approach | Mechanism | Pros | Cons / Failure Modes | Evaluation for SALESTORM |
| :--- | :--- | :--- | :--- | :--- |
| **In-Memory Java Lock (`synchronized` / `ReentrantLock`)** | JVM level lock on Product object | Simple, 0 network latency | **Fatal in Distributed System:** Fails across multiple pod replicas; pod restart loses locks; oversells instantly. | ❌ **Rejected** (Unsafe) |
| **Pessimistic DB Lock (`SELECT FOR UPDATE`)** | DB locks row for duration of transaction | Absolute serializability | High DB connection pool saturation; 10,000 threads blocked on 1 DB row lock leads to connection timeouts and latency spikes. | ⚠️ **Suboptimal for Spike** |
| **Optimistic Locking via Version (`version = version + 1`)** | Read version, attempt update, retry on version mismatch | No long DB holds | Heavy retry storm: 10,000 threads trying to update version results in 9,900 failed updates and retry CPU thrashing. | ⚠️ **Suboptimal without backoff** |
| **Atomic Conditional SQL Decrement (Selected Core)** | `UPDATE ... WHERE available >= qty` | Zero application-level lock holding; leverages DB row write lock only for the microsecond duration of the single UPDATE; deterministic return of rows affected (1 = success, 0 = sold out). | High throughput; scales up to DB write limit (~5,000–10,000 TPS on single row with batching); clean zero-oversell guarantee. | ✅ **SELECTED CORE MECHANISM** |
| **Redis Lua Script Pre-allocation Token (Edge Shield)** | Atomic `EVAL` script decrements Redis integer; only successful tokens reach DB | Absorbs 100k+ QPS at Redis memory speed; relieves DB from processing 9,900 failing queries. | Requires cache-DB sync reconciliation; potential stale cache if not invalidated properly. | ✅ **SELECTED TIER 1 SHIELD** |

---

## 5. Idempotency Flow

```
Client Request (Buy Now)
  ├── Header: Idempotency-Key: "order-cust-9876-req-1"
  └── Payload: { productId: "PROD-100", quantity: 1 }
         │
         ▼
[IdempotencyInterceptor]
  ├── Query IIdempotencyStore.checkOrLock(key, payloadHash, ttl=15min)
  │
  ├── CASE A: Key exists & Status == COMPLETED
  │     └── Return Cached Response (HTTP 200 OK + Existing ReservationDTO)
  │
  ├── CASE B: Key exists & Status == IN_FLIGHT (Lock Active)
  │     └── Return HTTP 409 Conflict ("Request currently processing. Please retry.")
  │
  └── CASE C: Key is NEW (Lock Acquired)
        │
        ▼
   [ReservationApplicationService.createReservation()]
        │
        ├── Step 1: Execute Atomic SQL Decrement
        │     `UPDATE inventory SET available = available - 1, reserved = reserved + 1 WHERE id = 'PROD-100' AND available >= 1`
        │
        ├── Step 2A (Affected Rows == 1): SUCCESS
        │     ├── Insert into `inventory_reservations` (status='RESERVED', expires_at=now+10m)
        │     ├── Update IdempotencyStore with Success DTO (status=COMPLETED)
        │     ├── Publish `InventoryReservedEvent`
        │     └── Return HTTP 201 Created (ReservationDTO)
        │
        └── Step 2B (Affected Rows == 0): OUT OF STOCK
              ├── Update IdempotencyStore with OutOfStock DTO (status=COMPLETED)
              ├── Publish `InventorySoldOutEvent`
              └── Return HTTP 409 / 422 Out of Stock ("Product is sold out")
```

---

## 6. Error & Failure Scenarios Handled

1. **Simultaneous Contention for the 100th Unit (2 users hitting at same millisecond):**
   - Both issue `UPDATE ... WHERE available >= 1`.
   - PostgreSQL/MySQL engine serializes the row lock.
   - User 1's statement decrements `available` from 1 to 0 $\rightarrow$ `rows_affected = 1` (Success).
   - User 2's statement executes immediately next: `available` is now 0 $\rightarrow$ `available >= 1` condition fails $\rightarrow$ `rows_affected = 0` (Out of Stock).
   - **Zero overselling guaranteed by the database ACID engine.**

2. **Node Crash After Stock Decrement but Before Event Publication:**
   - Transactional Outbox Pattern ensures reservation record and event are written in the *same atomic DB transaction*.
   - Outbox dispatcher process asynchronously reads un-dispatched events and publishes to message broker.

3. **Scheduler Dies During Expiry Sweep:**
   - Uses atomic status CAS: `UPDATE inventory_reservations SET status = 'EXPIRED' WHERE reservation_id = :id AND status = 'RESERVED'`.
   - If node crashes, remaining reservations remain in `RESERVED` state and are picked up by the next scheduler tick or backup replica.
