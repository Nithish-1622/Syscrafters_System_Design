# ADR-005: Message Broker Architecture & Delivery Semantics

**Status:** Approved  
**Date:** 2026-10-05  
**Author:** Member 1 (System Architect)  
**Deciders:** Core Engineering Team  

---

## 1. Context & Problem Statement
The SALESTORM platform relies on an asynchronous event broker to decouple payment settlement from order creation, shipment routing, and notifications. 
Key requirements include:
- **Zero Message Loss (Durability):** Under service crashes (e.g., Order Service 30-second outage), messages must be retained on disk across multiple broker nodes.
- **Strict Ordering per Aggregate:** Events relating to a single `order_id` or `reservation_id` must be consumed in strict temporal sequence.
- **Extreme Peak Throughput:** Ability to absorb event bursts up to 50,000 messages/sec during 500k flash spikes.
- **Clear Delivery Semantics:** Distributed systems cannot achieve magical "Exactly-Once" delivery over unreliable networks without coordinated two-phase commit or consumer-side deduplication.

We must select the message broker technology and define the concrete delivery and deduplication semantics.

---

## 2. Options Considered

### Option 1: AMQP Traditional Broker (RabbitMQ)
- **Description:** Queue-based messaging where messages are removed from the broker once acknowledged by consumers.
- **Pros:** Complex message routing (topic exchanges, direct exchanges); low latency for low-to-medium volumes; rich dead-letter routing features.
- **Cons:** Messages are deleted upon consumption, making replay impossible; lower sustained write throughput under heavy backlog accumulation; broker performance degrades when queues grow to millions of messages during outages.

### Option 2: Distributed Partitioned Commit Log (Apache Kafka / AWS MSK / Kinesis) (Selected)
- **Description:** Append-only distributed commit log with persistent, partitioned topics, offset tracking, and consumer groups.
- **Pros:** Massive sequential disk write throughput ($> 100,000\text{ msgs/sec}$); configurable retention (e.g., 7 days), enabling event replay for disaster recovery; strict partition-level FIFO ordering; backpressure handled by consumer pull model.
- **Cons:** Higher operational complexity; consumers must manage offset commits and group rebalancing.

---

## 3. Decision
We select **Option 2: Distributed Partitioned Commit Log (Kafka Architecture)** configured with **At-Least-Once Delivery + Idempotent Consumer Inbox Pattern**.

### Detailed Implementation Mechanics:
1. **Producer Guarantee:**  
   Producers write via the **Transactional Outbox Pattern** with `acks=all` (wait for all in-sync replicas to acknowledge write).
2. **Partitioning Strategy:**  
   Messages are keyed by `aggregate_id` (e.g., `order_id` or `reservation_id`). This guarantees that all lifecycle events for a specific order route to the same partition, guaranteeing strict FIFO sequence.
3. **Consumer Semantics (At-Least-Once):**  
   Consumers manually commit offsets **only after** successfully completing the local database transaction. If a consumer crashes before committing its offset, Kafka will redeliver the event upon pod restart.
4. **Consumer De-duplication (The Inbox Pattern):**  
   Every consumer maintains an `inbox_events` table in its private PostgreSQL database:
   ```sql
   INSERT INTO inbox_events (event_id, processed_at) VALUES ($1, NOW())
   ON CONFLICT (event_id) DO NOTHING;
   ```
   If zero rows are inserted, the consumer skips business processing and immediately commits the offset. This achieves **Effective Exactly-Once Business Processing** without complex distributed transactions.

---

## 4. Architectural Consequences & Trade-offs

### Positive Consequences:
- **Bulletproof Crash Recovery:** During the 30-second Order Service crash test case, Kafka effortlessly retains all events at the exact uncommitted offset pointer. When the Order Service recovers, it resumes reading from the uncommitted offset with zero message loss.
- **Event Replay Capability:** If an unexpected bug corrupts order processing logic, engineers can deploy a fix, reset consumer group offsets back 2 hours, and safely re-process all events.

### Negative Consequences / Trade-offs:
- **Duplicate Processing Overhead:** Consumers must execute an indexed check on `inbox_events` for every received message. 
- **Mitigation:** The `inbox_events` table is indexed on `event_id` and pruned periodically via background vacuuming, maintaining sub-millisecond check latency.
