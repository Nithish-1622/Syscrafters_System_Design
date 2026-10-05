# SALESTORM — Reliability, Fault Tolerance & Failure Recovery Architecture

**Document Version:** 1.0.0  
**Status:** Approved Architecture Baseline  
**Lead Author:** Member 1 (System Architect + Concurrency, Inventory & Scalability Lead)  
**Target Audience:** Core Engineering Team (Members 2, 3, 4), Technical Jury, Operations  

---

## 1. Reliability Philosophy & Core Resilience Principles

SALESTORM is designed under the distributed systems axiom: **"Failures are not exceptional; they are inevitable operational constants."**

Under peak flash-sale load:
- Networks partition.
- External payment gateways drop connections.
- Downstream microservices crash under out-of-memory (OOM) pressure.
- Databases experience transient replication lag or failover.

To guarantee zero data loss, zero duplicate charges, and zero overselling, SALESTORM implements four core resilience pillars:
1. **Bounded Fail-Fast at the Front, Durable Decoupling at the Back:** Synchronous reservation calls fail immediately on scarcity, preventing client queue backpressure. Downstream post-payment workflows are decoupled using persistent append-only event logs.
2. **Exponential Backoff with Full Decorrelated Jitter:** Prevents the "Thundering Herd" problem when failed clients or recovering services retry simultaneously.
3. **Idempotent At-Least-Once Consumer Contracts:** Downstream services accept that network retries will deliver duplicate messages and implement deterministic Inbox deduplication.
4. **Autonomous Dual-Path Reconciliation:** A scheduled background safety net constantly audits state differences across services to heal lost events or interrupted transactions without manual operator intervention.

---

## 2. Timeout, Retry, Circuit Breaker & Backpressure Framework

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              RESILIENCE CONTROL FRAMEWORK                              │
├───────────────────┬────────────────────┬──────────────────────┬────────────────────────┤
│ Hop / Interaction │ Timeout Budget     │ Retry Policy         │ Circuit Breaker Config │
├───────────────────┼────────────────────┼──────────────────────┼────────────────────────┤
│ Gateway → Checkout│ 2,000 ms           │ 0 Retries (Idemp. re)│ Trips @ 50% errors     │
│ Checkout → Inv Svc│ 300 ms             │ 1 Retry (Fast backoff│ Trips @ 30% errors     │
│ Inv Svc → Redis   │ 50 ms              │ 2 Retries (10ms wait)│ Failover to Replica    │
│ Payment → Gateway │ 3,000 ms           │ 0 Retries (Query 1st)│ Trips @ 20% errors     │
│ Broker → Order Svc│ 30,000 ms (Polling)│ Infinite (Backoff)   │ Backpressure throttling│
└───────────────────┴────────────────────┴──────────────────────┴────────────────────────┘
```

### Mathematical Retry Formula: Exponential Backoff with Full Jitter
To ensure retry bursts do not synchronize:
$$t_{\text{sleep}} = \text{random}(0, \, \min(t_{\text{max}}, \, t_{\text{base}} \times 2^{\text{attempt}}))$$
Where $t_{\text{base}} = 100\text{ ms}$, $t_{\text{max}} = 5,000\text{ ms}$, and $\text{attempt} \in [1, 5]$.

### Circuit Breaker State Transition Engine (Resilience4j / Envoy Specification)
- **Closed State:** Traffic flows normally. If failure rate exceeds $50\%$ over a sliding window of 100 calls, trip to **Open**.
- **Open State:** Immediate fail-fast. No calls forwarded; returns fallback response (HTTP 503 / Degraded). Remains open for 10 seconds.
- **Half-Open State:** Allows 10 trial requests through. If success rate is $\ge 90\%$, transitions to **Closed**; otherwise, returns to **Open** for another 30 seconds.

---

## 3. The 12 Critical Failure Scenarios Matrix

The table below details the complete lifecycle for every critical failure mode identified in the Hackathon Brief:

| # | Failure Scenario | Detection Mechanism | Immediate Behavior | Retry Policy | Circuit Breaker | Queue / DLQ Action | Compensation / Reconciliation | Final System State |
| :- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Inventory Service Failure** | API Gateway health check probe (HTTP 500 / TCP timeout $> 300\text{ms}$). | **Fail-Closed:** Returns `503 Service Unavailable`. Halts new reservations immediately. | 0 retries on write path (prevents stampede). | Opens after 5 consecutive failures. | In-flight DB writes drain safely. | Uncommitted Redis leases expire naturally after 300s TTL. | Zero overselling; platform remains safe; customer sees clean error. |
| **2** | **Primary Database Crash** | PostgreSQL health agent detects master unresponsiveness. | Automatic failover to Synchronous Standby replica via Patroni / Raft. | Application connection pool reconnects after 3,000ms. | Trips for 5 seconds during master promotion. | Transactions in-flight abort safely; outbox worker resumes on replica. | Redis state remains intact; RPO = 0 due to synchronous replication. | Standby promoted to Master in $< 15\text{s}$; zero data lost. |
| **3** | **Payment Gateway Outage** | Gateway returns HTTP 502/503 or socket connection refused. | Gateway marked UNREACHABLE; user notified: "Payment partner offline." | 0 retries of raw charges. | Breaker OPEN for 60s; fallback to secondary gateway (e.g., Adyen $\rightarrow$ Stripe). | Payment request retained in client session. | If no secondary gateway, customer's reservation is preserved for 300s. | Customer can switch payment method; no double charges occur. |
| **4** | **Payment Request Timeout** | Client/Payment Service waits $> 3,000\text{ms}$ with no HTTP response from gateway. | **Ambiguous State:** Payment status marked `PENDING_VERIFICATION`. Do NOT retry charge! | 0 blind retries. | N/A | Enqueued to `payment.verify.queue`. | Background worker calls Gateway Query API using `idempotency_key` to fetch true state. | Resolved to `PAID` or `FAILED` within 10 seconds. |
| **5** | **Payment Failed (Card Decline)** | Gateway returns definitive decline (e.g., `insufficient_funds`, `do_not_honor`). | Payment marked `FAILED`. UI immediately displays card error reason. | 0 retries on same card. | N/A | None. | **Immediate Stock Release:** Emits `ReservationReleaseCommand`; Redis Lua increments stock $+1$. | Reservation cancelled; stock immediately returned to available pool for other buyers. |
| **6** | **Order Service Down for 30s** | Container health probe fails; consumer heartbeats cease in Kafka. | Upstream Payment Service succeeds! Emits `PaymentSuccessfulEvent` to durable Kafka broker. | Kafka consumer pauses polling until pod restarts. | N/A (Isolated by Kafka). | Messages safely retained in Kafka topic (Retention = 7 days). | When Order Service restarts at $t = 30\text{s}$, it processes backlog idempotently. | **100% Order Recovery:** All paid orders materialized; zero lost purchases. |
| **7** | **Message Broker Partition/Failure** | Producer write error (`LeaderNotAvailableException`). | Services fall back to **Transactional Outbox Table** in local PostgreSQL database. | Outbox CDC poller retries broker connection every 1,000ms. | Producer buffers events in local DB. | Outbox table acts as local persistent buffer. | Once broker recovers, outbox poller replays all uncommitted events in exact order. | Zero message loss; eventual consistency restored seamlessly. |
| **8** | **Duplicate Message Delivery** | Broker re-delivers message due to consumer ACK timeout or rebalance. | Order Service consumer intercepts message and extracts `event_id`. | Consumer processes normally. | N/A | None. | **Inbox Pattern:** Checks `processed_events` table. Matches existing `event_id` $\rightarrow$ drops silently. | Consumer commits offset (ACK); no duplicate order created. |
| **9** | **Duplicate Client Request (2%)** | Impatient customer double-clicks "Buy Now" button within 200ms. | API Gateway checks Redis key `idemp:req:{user_id}:{idempotency_key}`. | 0 retries. | N/A | None. | Second request detects active lock; returns identical response as the first request. | Exactly one reservation created; customer receives single reservation token. |
| **10**| **Reservation Expiry (TTL=300s)**| User abandons checkout; 300 seconds elapse without payment. | Redis Sorted Set Sweeper identifies `expires_at < now()`. | Automated worker task. | N/A | Pushed to `inventory.release.events`. | Sweeper executes release Lua script: increments stock $+1$, deletes lease hash, marks DB `EXPIRED`. | Stock returned to available inventory; late payment attempts automatically rejected/refunded. |
| **11**| **Notification Service Outage** | External Email/SMS provider down or worker crash. | Notification worker catches error and writes failed payload to Notification DLQ. | Exponential backoff (1s, 5s, 30s) up to 5 attempts. | Breaker opens on external email API. | Moves to `notification.dlq` after 5 failures. | Ops alert triggered. Core payment and order workflows **remain 100% unaffected**. | Orders confirmed; notifications replayed once carrier restores API. |
| **12**| **Shipment Service Failure** | Warehouse ERP connection times out or carrier API down. | Order Service marks order `CONFIRMED_AWAITING_FULFILLMENT`. | Retried every 60s by logistics scheduler. | N/A | Order event buffered in Kafka topic `order.fulfillment.queue`. | Once carrier API recovers, batch manifest generation resumes without data loss. | Physical goods dispatched; tracking numbers populated asynchronously. |

---

## 4. Deep-Dive on the Critical Hackathon Test Case: Payment Succeeds BUT Order Service is Unavailable for 30 Seconds

One of the most vital test scenarios from the brief is:
> **Test Condition:** Stock = 100 | Concurrent users = 10,000 | Payment success = 95% | Order Service unavailable for 30 seconds.

### The Catastrophic Anti-Pattern (What Amateurs Do)
In an amateur synchronous microservices architecture:
1. Customer pays $1,000 successfully on Stripe.
2. Payment Service makes a synchronous HTTP POST to `http://order-service/api/orders`.
3. Order Service is down $\implies$ HTTP call throws `500 Connection Refused`.
4. Payment Service catches the exception and attempts to "roll back" by calling Stripe Refund.
5. **Why this is catastrophic:**
   - Bank refund APIs take 5–10 business days to credit customer cards.
   - The customer receives an SMS from their bank: *"Your card was charged $1,000"*, followed by an error on their screen: *"Order failed!"*
   - Customer trust is destroyed, support queues explode, and the business loses legitimate revenue on a customer who legitimately won the flash sale!

### The SALESTORM Architectural Solution: The Transactional Outbox & Resilient Ingestion Log

```
[Customer Pays] ──► [Payment Service] 
                           │
                           ▼ (ACID Transaction)
        ┌────────────────────────────────────────────────────────┐
        │ BEGIN TRANSACTION;                                     │
        │ UPDATE payments SET status = 'PAID' WHERE id = 123;   │
        │ INSERT INTO outbox_events (event_id, type, payload)    │
        │   VALUES ('evt_999', 'PaymentSuccessful', {...});      │
        │ COMMIT;                                                │
        └────────────────────────────────────────────────────────┘
                           │
                           ▼ (Asynchronous CDC / Outbox Relayer)
        [Kafka Broker: Topic 'payment.success.events']
        (Durable append-only log across 3 Availability Zones)
                           │
                           │  ◄── [Order Service CRASHED for 30s]
                           │      (Kafka retains message at uncommitted offset)
                           │
                           ▼ (At t = 30s: Kubernetes Restarts Order Service Pod)
        [Order Service Recovers & Reconnects to Kafka]
                           │
                           ▼ (Idempotent Inbox Pattern)
        ┌────────────────────────────────────────────────────────┐
        │ BEGIN TRANSACTION;                                     │
        │ INSERT INTO order_inbox (event_id) VALUES ('evt_999'); │
        │ INSERT INTO orders (order_id, status, reservation_id)  │
        │   VALUES ('ORD-555', 'CONFIRMED', 'res_123');          │
        │ COMMIT;                                                │
        └────────────────────────────────────────────────────────┘
                           │
                           ▼
        [Order Created Successfully — Zero Refunds Needed!]
```

### Step-by-Step Execution During the 30-Second Outage:
1. **$t = 0\text{s}$ (Payment Settled):**  
   Customer's payment succeeds. The Payment Service executes an atomic PostgreSQL transaction that updates the payment record to `PAID` and writes a `PaymentSuccessfulEvent` into the `outbox_events` table.
2. **$t = 0.5\text{s}$ (Message Buffered):**  
   The Outbox Relayer (Debezium / Transactional Poller) reads the outbox table and streams the event into the durable Kafka topic `payment.success.events`. Kafka writes the message to disk across 3 broker nodes.
3. **$t = 1\text{s}$ to $30\text{s}$ (The Outage):**  
   The Order Service pod suffers an OOM crash or network partition. The Kubernetes container runtime detects liveness probe failure and initiates pod recreation.
   - During these 30 seconds, Kafka tracks the consumer group offset. The message is **neither acknowledged nor lost**; it sits safely in the durable partition log.
   - The customer UI displays: *"Payment verified! We are finalizing your order confirmation..."* with a live WebSocket polling channel.
4. **$t = 30\text{s}$ (Order Service Recovery):**  
   The new Order Service pod passes readiness checks and joins the consumer group. Kafka delivers all pending messages that accumulated during the 30-second window.
5. **$t = 31\text{s}$ (Idempotent Order Materialization):**  
   The Order Service processes each event inside an idempotent transaction using its `order_inbox` table. It inserts the order as `CONFIRMED`, triggers shipment batching, and notifies the customer via WebSocket: *"Order #ORD-555 confirmed!"*

### The Ultimate Safety Net: Two-Way Asynchronous Reconciliation Worker
What if a cosmic ray causes the message broker to drop a packet, or an event offset is mismanaged?
- Every 60 seconds, an autonomous **Reconciliation Engine** runs:
  ```sql
  SELECT payment_id, reservation_id, customer_id, amount 
  FROM payments 
  WHERE status = 'PAID' 
    AND created_at < NOW() - INTERVAL '60 SECOND' 
    AND order_id IS NULL;
  ```
- For any orphaned paid transaction, the reconciliation worker calls the Order Service API directly via an idempotent internal endpoint: `POST /internal/orders/reconcile`.
- **Guarantee:** Under no circumstances can a paid reservation fail to materialize into a valid order.

---

## 5. Dead Letter Queue (DLQ) & Poison Pill Isolation Strategy

When messages cannot be processed due to corrupted payloads, schema mismatches, or persistent database deadlocks, systems must prevent "Poison Pills" from blocking the entire partition.

```
Incoming Kafka Event ──► [Order Consumer Pod]
                                │
                    Fails? ─────┴─────► Retry Attempt 1 (Wait 100ms)
                                │
                    Fails? ─────┴─────► Retry Attempt 2 (Wait 500ms)
                                │
                    Fails? ─────┴─────► Retry Attempt 3 (Wait 2,000ms)
                                │
                     Permanent Failure (Max Retries Exceeded)
                                │
                                ▼
        [Dead Letter Queue Topic: 'order.creation.dlq']
                                │
               ┌────────────────┴────────────────┐
               ▼                                 ▼
    [Ops PagerDuty Alert Triggered]    [Manual Inspection / Replay CLI]
```

1. **Max Retry Threshold:** A message is retried at most **3 times** with exponential backoff.
2. **DLQ Routing:** If the 3rd attempt fails, the message is routed to `order.creation.dlq` alongside full error metadata:
   ```json
   {
       "original_event_id": "evt_999",
       "error_class": "MalformedAddressException",
       "stack_trace": "...",
       "failed_at": "2026-10-05T10:15:30Z",
       "payload": {...}
   }
   ```
3. **Partition Unblocking:** The original consumer commits its offset, allowing the queue to proceed and process legitimate customer orders without delay.

---

*End of 02_Reliability_and_Failure_Handling.md — Authoritative Reliability Blueprint.*
