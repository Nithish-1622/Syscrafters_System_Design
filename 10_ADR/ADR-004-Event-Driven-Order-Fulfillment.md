# ADR-004: Event-Driven Order Fulfillment via At-Least-Once Messaging & Idempotent Consumers

## Status: ACCEPTED
**Date**: October 2026  
**Authors**: Member 3 (API, Event & Reliability Engineer)

---

## Context & Problem Statement
When a customer payment succeeds, the order must be created, confirmed, inventory permanently deducted, and fulfillment dispatched. We must guarantee that:
1. **Zero Order Loss**: If the Order Service or database crashes for 30 seconds, no paid order is lost.
2. **Zero Duplicate Fulfillment**: If a network glitch re-delivers the `PaymentSucceeded` message, the system must not create duplicate orders or ship two items.

---

## Decision
We select **At-Least-Once Asynchronous Messaging** (via durable message broker: AWS SQS FIFO / Kafka) paired with an **Idempotent Message Consumer Store**:

1. **Durable Buffer**: The message broker retains unacknowledged messages with a 14-day retention window.
2. **Consumer Deduplication Store**: Before executing order creation, the consumer attempts an atomic insert into `idempotency_records` using the CloudEvents `id`.
3. **Poison Message Policy**: Messages failing more than 3 consecutive delivery attempts are diverted to a Dead-Letter Queue (DLQ) with an immediate P1 alert.

---

## Consequences

### Positive:
- **Resilience to Cascading Failures**: Order Service can be offline for minutes or hours without dropping customer transactions.
- **Decoupled Architecture**: Payment Service completes instantly without waiting for Order, Warehouse, or Shipment systems.

### Negative / Trade-Offs:
- **Message Broker Dependency**: Requires high-availability message infrastructure.
- **Deduplication Storage Overhead**: Idempotency records must be maintained with a 7-day TTL.
