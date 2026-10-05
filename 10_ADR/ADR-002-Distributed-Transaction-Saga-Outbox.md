# ADR-002: Choreographed Saga with Transactional Outbox vs Two-Phase Commit (2PC)

## Status: ACCEPTED
**Date**: October 2026  
**Authors**: Member 3 (Database & Event Engineer), in alignment with Member 1 & Member 2

---

## Context & Problem Statement
A complete flash-sale purchase spans multiple bounded contexts:
1. Inventory Reservation
2. Payment Authorization
3. Order Creation & Fulfillment

We must decide how to coordinate these operations across independent microservices and database instances without data inconsistency or availability collapse.

---

## Decision
We select an **Asynchronous Choreographed Saga** pattern paired with the **Transactional Outbox Pattern**.

We explicitly reject **Distributed Two-Phase Commit (2PC)**:
- 2PC holds database locks across network boundaries during external payment gateway calls (500ms to 5,000ms), freezing inventory rows and starving concurrent requests.
- 2PC is fragile: coordinator crashes leave distributed participants in an uncertain, locked state.
- CAP theorem dictates that 2PC sacrifices availability for strict consistency.

---

## Technical Mechanism
1. **Local ACID Transactions**: Each service commits strictly within its local database.
2. **Transactional Outbox**: Events (e.g. `PaymentSucceeded`) are inserted into the `transactional_outbox` table in the *same* database transaction that updates business state.
3. **Outbox Relay**: A CDC / polling background relay publishes events to a durable message broker (AWS SQS / Kafka).
4. **Idempotent Consumers**: Downstream consumers (Order Service) deduplicate incoming events via `idempotency_records`.
5. **Compensating Transactions**: If payment fails, an asynchronous `PaymentFailed` event triggers an idempotent compensating transaction in the Inventory Service to release held stock.

---

## Consequences

### Positive:
- **Zero Dual-Write Inconsistencies**: Impossible to commit database state without staging the outbound event.
- **Maximum Availability & Fault Isolation**: If Order Service goes down for 30 seconds, Payment Service continues operating normally. Events buffer in the queue and recover seamlessly.
- **Ultra-Low Latency**: Checkout API does not block waiting for downstream order fulfillment.

### Negative / Trade-Offs:
- **Eventual Consistency**: There is a brief window (typically < 1.5 seconds) between payment confirmation and order generation.
- **Compensating Logic Required**: Application must maintain explicit rollback logic for failed sagas.
