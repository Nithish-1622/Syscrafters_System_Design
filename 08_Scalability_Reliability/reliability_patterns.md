# SALESTORM 2026 | Distributed Reliability Patterns Specification

## 1. Implementation-Facing Reliability Patterns

This document details the exact technical implications (Data, API, Event, State, and Validation) for the core distributed reliability patterns implemented across the SALESTORM ecosystem.

---

## 2. Deep-Dive Pattern Specifications

### 2.1 Timeout
- **Definition**: Hard time limit on any synchronous operation before abandoning and failing fast.
- **Boundaries**:
  - API Gateway to Microservice: **2,000 ms**
  - Database Transaction: **1,000 ms** (`statement_timeout = '1000ms'`)
  - Payment Provider Network Call: **3,000 ms**
- **Data Implications**: Aborted database operations release row locks immediately.
- **API Implications**: Returns `HTTP 504 Gateway Timeout` or `HTTP 408 Request Timeout`.
- **Event Implications**: Emits `TransactionTimeout` diagnostic metric.
- **State Implications**: Does not infer success or failure; marks state as `TIMED_OUT` or `RECONCILIATION_REQUIRED`.

---

### 2.2 Retry with Exponential Backoff and Full Jitter
- **Definition**: Resending failed transient requests with dynamically expanding delays randomized to prevent the "thundering herd" problem.
- **Backoff Formula**:
  $$t_{\text{sleep}} = \text{random}(0, \min(t_{\text{max}}, t_{\text{base}} \times 2^{\text{attempt}}))$$
  Where $t_{\text{base}} = 100\text{ms}$, $t_{\text{max}} = 5,000\text{ms}$, $\text{attempt} \in \{1, 2, 3\}$.
- **Validation Rule**: Retries are permitted **ONLY on idempotent requests** (GET, PUT, or POST with verified `Idempotency-Key`). Retrying non-idempotent operations without a key is strictly prohibited.

---

### 2.3 Circuit Breaker (Closed, Open, Half-Open)
- **Definition**: Protects the system from cascading failure when a downstream dependency (e.g. Payment Gateway or Database) is degraded.
- **State Transitions**:
  - **CLOSED**: Normal operation. Failure rate monitored over a 30-second sliding window.
  - **OPEN**: Triggered if error rate > 50% or latency p99 > 2,000ms. All subsequent calls immediately fail fast (HTTP 503) without touching downstream.
  - **HALF-OPEN**: After a 15-second cooldown, admits 5% of traffic as probe canary requests. If 100% succeed, resets to CLOSED; otherwise re-opens.
- **Metrics**: Emits `salestorm_circuit_breaker_state` gauge (`0` = Closed, `1` = Half-Open, `2` = Open).

---

### 2.4 Dead-Letter Queue (DLQ) & Poison Message Handling
- **Definition**: Secondary durable queue where unprocessable messages are redirected after retry exhaustion.
- **Rules**:
  - Max Delivery Attempts: **3** (or 5 for network partitions).
  - Poison message retained in DLQ with original headers, exception stack trace, and timestamp.
  - Generates immediate **P1 Critical Alert** (`increase(salestorm_dlq_messages_total[1m]) > 0`).

---

### 2.5 Idempotent Consumer
- **Definition**: Message consumer pattern ensuring that receiving the same event multiple times produces the exact same outcome as receiving it once.
- **Implementation**:
  - Consumer inspects `idempotency_records` table using the CloudEvents `id`.
  - If record exists with status `COMPLETED`, the consumer acknowledges the message to SQS/Kafka and exits immediately without executing downstream writes.

---

### 2.6 Compensating Transactions (Saga Rollback)
- **Definition**: Explicit business undo action executed when a distributed workflow fails midway.
- **SALESTORM Use Case**:
  - Flow: Reservation Created -> Payment Attempted -> Payment Fails.
  - Compensation: Inventory Service receives `PaymentFailed` event -> Executes `UPDATE reservations SET status = 'RELEASED'` -> Restores `available_quantity = available_quantity + qty`.
- **Invariance**: Compensation is idempotent; calling release twice cannot corrupt inventory counters.

---

### 2.7 Payment Reconciliation
- **Definition**: Automated asynchronous background worker resolving ambiguous payment states.
- **Trigger**: Payment remains in `INITIATED` or `TIMED_OUT` for > 5 minutes without webhook resolution.
- **Action**: Queries Payment Gateway API (`GET /v1/charges?idempotency_key=...`).
  - If charge exists & succeeded -> Emits synthetic `PaymentSucceeded` to resume order creation.
  - If charge does not exist -> Updates status to `FAILED`, releases reservation.
