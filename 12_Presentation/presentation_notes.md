# SALESTORM 2026 | Technical Presentation Speaker Notes & Defense Guide

## Slide 1: The Central Flash-Sale Challenge
- **Talking Points**:
  - In a flash sale with 10,000 requests competing for 100 items, the primary risk is not just raw speed, but **data consistency under race conditions**.
  - A simple `SELECT stock` followed by `UPDATE stock` produces catastrophic overselling under concurrent execution.
  - Adding horizontal database replicas worsens the problem because replicas cannot handle concurrent writes on a single row.

---

## Slide 2: Concurrency & Database Invariants
- **Talking Points**:
  - We compared three concurrency approaches: Pessimistic locking (`SELECT FOR UPDATE`), Optimistic Concurrency Control (OCC), and Atomic Conditional SQL Updates.
  - Pessimistic locking creates queue exhaustion and 504 timeouts.
  - OCC results in a 99% retry abort storm that melts CPU cores.
  - We chose **Atomic Conditional SQL Updates**: `UPDATE inventory SET available = available - 1 WHERE available >= 1`.
  - Backed by an in-memory Redis pre-allocation filter, only eligible contenders reach the database.

---

## Slide 3: Distributed Reliability & Outage Recovery
- **Talking Points**:
  - We explicitly rejected Two-Phase Commit (2PC) due to lock holding latency during 3-second bank gateway calls.
  - We implemented a **Choreographed Saga with Transactional Outbox**.
  - **The 30-Second Outage Test**: We validated that when the Order Service crashes for 30 seconds, `PaymentSucceeded` events buffer safely in the durable message broker.
  - Upon restart, the consumer drains the queue with idempotent deduplication. Result: **Zero lost orders**.

---

## Slide 4: Idempotency & Financial Safety
- **Talking Points**:
  - 2% of flash-sale traffic consists of duplicate submissions from jittery shoppers clicking "Buy Now" repeatedly.
  - We implemented a 3-tier idempotency model with `Idempotency-Key` headers and SHA-256 body hashing.
  - Duplicates are recognized in milliseconds, returning cached results without touching inventory counters or charging cards twice.

---

## Slide 5: Empirical Simulation Evidence
- **Talking Points**:
  - We wrote and executed an automated Python test harness (`simulate_flash_sale.py`).
  - Parameters: 10,000 customers, 100 stock units, 95% payment success, 5% decline, 2% duplicates, 30s outage.
  - **Results**: Exactly 100 units sold, 0 oversold, 7 payment declines compensated and returned to stock, 100 orders recovered. Mathematical proof confirmed.
