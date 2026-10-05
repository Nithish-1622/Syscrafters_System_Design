# SALESTORM 2026 | Data Consistency Matrix

## 1. Architectural Strategy: Bounded Consistency

In a distributed flash-sale system handling 500,000 req/sec, **claiming that the entire system is strongly consistent is an anti-pattern**. 

SALESTORM strictly delineates:
- **Strong Consistency**: Limited strictly to inventory decrement and hold operations to prevent overselling.
- **Eventual Consistency**: Applied to asynchronous fulfillment, notifications, and analytics to preserve high availability.

---

## 2. Authoritative Data Consistency Matrix

| Data / Domain Operation | Consistency Requirement | Exact Guarantee | Underlying Mechanism | Failure Behavior & Recovery |
| :--- | :--- | :--- | :--- | :--- |
| **Inventory Stock Decrement & Hold** | **STRONG CONSISTENCY** | Strict Linearizability; Zero Overselling | Atomic Conditional SQL: `UPDATE inventory SET available = available - :qty WHERE available >= :qty` + DB row lock latch. | If condition fails, transaction aborts; HTTP 409 Out of Stock returned. |
| **Reservation Expiry & Stock Release** | **STRONG CONSISTENCY** (at transition point) | At most once stock return; no double-release | Atomic Conditional SQL: `UPDATE reservations SET status = 'RELEASED' WHERE status = 'RESERVED' RETURNING qty`. | If already confirmed or released, 0 rows affected; stock balance preserved. |
| **Payment Gateway Authorization** | **EXTERNAL CONSISTENCY** | At most one financial charge per checkout | Client `Idempotency-Key` + Payment Gateway unique idempotency tokens. | Ambiguous network timeout triggers `RECONCILIATION_REQUIRED`; no duplicate charge. |
| **Payment Webhook Settlement** | **AT-LEAST-ONCE -> EXACTLY-ONCE EFFECT** | Deduplicated state update | `provider_transaction_id VARCHAR UNIQUE` + Database Upsert / On Conflict Ignore. | Duplicate webhook ignored; original 200 OK returned. |
| **Order Creation from Payment** | **EVENTUAL CONSISTENCY** (Target < 2.0s) | Guaranteed eventual creation; zero order loss | Transactional Outbox + Durable Message Broker (SQS / Kafka) + Idempotent Consumer. | If Order Service is down (e.g. 30s outage), messages buffer in queue and process upon recovery. |
| **Order Confirmation -> Sold Inventory Ledger** | **EVENTUAL CONSISTENCY** (Asynchronous) | Ledger reconciles to exactly match confirmed orders | Order Service emits `OrderConfirmed`; Inventory worker updates `reserved_quantity` to `sold_quantity`. | Idempotent worker retries until confirmed. Audit ledger cross-checks nightly. |
| **Customer Pre-Checkout Cart** | **EVENTUAL CONSISTENCY** / Session Scoped | Last-Write-Wins (LWW) per customer | Redis session store or standard PostgreSQL update with customer lock. | Minor cart sync delays acceptable; strict checks occur at reservation. |
| **Logistics & Shipment Creation** | **EVENTUAL CONSISTENCY** (Target < 10m) | At least once dispatch tracking | Async message consumption from `OrderConfirmed` topic with Dead Letter Queue. | Transient carrier API downtime handled via exponential backoff retries. |
| **Customer Email / SMS Notifications** | **BEST EFFORT / EVENTUAL** | At least once message dispatch | Async worker polling notification queue with provider failover. | Failures logged; customer can always check order status in self-service dashboard. |
