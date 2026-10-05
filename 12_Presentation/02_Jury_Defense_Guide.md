# SALESTORM — Technical Jury Defense & 25 Architectural Validations

**Document Version:** 1.0.0  
**Status:** Approved Architecture Baseline  
**Lead Author:** Member 1 (System Architect + Concurrency, Inventory & Scalability Lead)  
**Target Audience:** Core Engineering Team, Hackathon Jury, Principal Systems Evaluators  

---

## Executive Overview

This defense guide provides authoritative, technically precise answers to the **25 critical architectural validation questions** established in the SALESTORM Hackathon Brief. Every answer is grounded in distributed systems principles, explicit invariants, and mathematical proofs.

---

### Q1: What happens when 10,000 users click Buy Now simultaneously?
**Architectural Answer:**  
1. All 10,000 requests pass through Edge WAF/DDoS filters and terminate TLS at the Application Load Balancer.
2. The API Gateway validates authenticated JWTs and enforces sliding-window rate limiting per `user_id`.
3. Validated requests forward via binary gRPC to the `Inventory Service`.
4. The Inventory Service evaluates an atomic Lua script running on the single-threaded event loop of the Redis Cluster shard owning that product key (`stock:item:X`).
5. **Requests 1 through 100:** Atomically decrement the in-memory counter from 100 to 0 and insert a 300-second reservation lease into a Redis hash. Each receives a `reservation_id` and HTTP 200 (Proceed to Payment).
6. **Requests 101 through 10,000:** Observe the counter $\le 0$. The script immediately returns 0, and the service returns an instant `HTTP 409 Conflict (Sold Out)` in $< 50\text{ ms}$.
7. **Database Protection:** Only the 100 winning reservations are committed to PostgreSQL via the Transactional Outbox pattern. The relational database is completely shielded from the 9,900 failing requests.

---

### Q2: Where exactly is inventory consistency guaranteed?
**Architectural Answer:**  
Inventory consistency is guaranteed at two coordinated demarcations:
1. **Contention Allocation Demarcation (Fast In-Memory):** Inside the single-threaded Redis Lua engine. Because Redis executes Lua scripts as an atomic unit with zero interleaving commands, the decrement and lease grant are strictly serialized.
2. **Durability & Invariant Demarcation (Persistent RDBMS):** Inside the PostgreSQL `inventory` table via engine-enforced relational check constraints:
   ```sql
   CHECK (available_quantity >= 0 AND reserved_quantity >= 0 AND sold_quantity >= 0);
   CHECK (available_quantity + reserved_quantity + sold_quantity = initial_quantity);
   ```
Even if an application pod crashes or corrupts memory, the relational database kernel physically rejects any write that would drive available stock negative or violate total unit conservation.

---

### Q3: What happens when two requests attempt to reserve the final unit simultaneously?
**Architectural Answer:**  
When stock $S = 1$ and Request A and Request B arrive at the network interface simultaneously ($t = 100.001\text{ ms}$ and $t = 100.002\text{ ms}$):
1. The TCP epoll multiplexer places both network packets into the Redis command buffer in sequential order.
2. The single-threaded Redis event loop pops Request A first.
3. Lua executes: `current_stock = 1`. `1 >= 1` is TRUE. It executes `decrby stock 1` ($1 \rightarrow 0$) and registers the lease. Script returns **1 (SUCCESS)**.
4. Redis immediately pops Request B.
5. Lua executes: `current_stock = 0`. `0 >= 1` is FALSE. It bypasses decrement and returns **0 (OUT OF STOCK)**.
6. Outcome is 100% deterministic: Request A gets the reservation; Request B receives `HTTP 409 Conflict`. Zero race conditions.

---

### Q4: Why did you choose your concurrency strategy?
**Architectural Answer:**  
We evaluated three approaches:
- **Pessimistic Locking (`SELECT FOR UPDATE`):** Collapses under 10,000 concurrent requests on a single row. Threads block in the database kernel, connection pools exhaust within 500ms, and upstream gateways crash with 504 timeouts.
- **Optimistic Locking (OCC):** Results in a catastrophic retry storm: 1 transaction succeeds and 9,999 transactions fail validation simultaneously, burning database CPU at 100% with rollbacks.
- **Our Selected Multi-Tier Hybrid Strategy:** Uses an in-memory single-threaded atomic engine (Redis Lua) to resolve the write contention at wire speed ($\sim 100,000\text{ ops/sec}$), followed by asynchronous PostgreSQL persistence with Transactional Outbox for the 100 winning transactions. This provides sub-millisecond contention arbitration, fast-fails the 9,900 losers in $< 50\text{ ms}$, and limits database writes to exactly 100 operations.

---

### Q5: What happens when inventory reaches zero?
**Architectural Answer:**  
1. In Redis, the Lua script returns 0 for all subsequent requests.
2. The Inventory Service emits a lightweight internal Redis Pub/Sub event: `SKU_DEPLETED(SKU_X)`.
3. All API Gateway instances update a local in-memory atomic boolean: `is_sold_out[SKU_X] = true`.
4. Subsequent incoming Buy Now requests are **rejected directly at the API Gateway edge in $< 1\text{ ms}$ with HTTP 409 (Sold Out)** without traversing internal networks, invoking gRPC calls, or querying databases.
5. Product display pages update their edge CDN micro-cache to display "Sold Out", throttling upstream browsing traffic.

---

### Q6: How are duplicate reservation requests handled?
**Architectural Answer:**  
Duplicate requests are eliminated via **Request Idempotency** at the API Gateway:
1. Every client generates a unique `Idempotency-Key: <UUIDv4>` header upon loading the product screen.
2. When a user double-clicks the button, the gateway executes an atomic Redis command: `SET idemp:req:{user_id}:{key} LOCKED NX EX 60`.
3. The first request acquires the lock and proceeds to reservation.
4. The second request fails `NX` (key already exists), intercepts the in-flight operation, and waits to return the exact cached HTTP response of the first request.
5. In PostgreSQL, a unique index on `inventory_reservation (product_id, idempotency_key)` acts as a secondary database-level defense.

---

### Q7: How are reservation expiries handled?
**Architectural Answer:**  
Reservations carry a strict **300-second (5-minute) lease TTL**:
1. When created, the `reservation_id` is indexed into a Redis Sorted Set: `ZADD reservations:expiry_zset <now + 300> <reservation_id>`.
2. A scheduled distributed sweeper daemon queries `ZRANGEBYSCORE reservations:expiry_zset 0 <current_time>` once every second.
3. For expired leases, an atomic release Lua script removes the active reservation lease, removes the sorted set index, and increments the stock counter: `INCRBY stock:item:X 1`.
4. The sweeper updates PostgreSQL reservation status to `EXPIRED`.
5. The released unit becomes instantly available for waiting customers.

---

### Q8: What happens when payment fails?
**Architectural Answer:**  
1. The payment gateway returns a definitive decline code (e.g., `card_declined`, `insufficient_funds`).
2. The Payment Service marks the transaction `FAILED` and immediately emits an internal command: `ReleaseReservationCommand(reservation_id)`.
3. The Inventory Service executes the atomic release script in Redis, restoring the stock counter (`INCRBY stock +1`).
4. The customer UI immediately displays the card failure error and allows them to retry with an alternate payment method if their 300-second reservation window is still active.

---

### Q9: What happens when payment times out?
**Architectural Answer:**  
1. If the external payment gateway fails to respond within 3,000ms, the system marks the transaction as `PENDING_VERIFICATION` (an ambiguous state).
2. The system does **NOT** blindly retry the charge (to prevent double charging) and does **NOT** immediately cancel the reservation.
3. An asynchronous worker queries the gateway's `/v1/charges` endpoint using the client's `payment_idempotency_key`.
4. If the gateway confirms payment succeeded: Transaction transitions to `PAID`, emitting `PaymentSuccessfulEvent`.
5. If the gateway confirms payment was never received: Transaction transitions to `FAILED` and releases the reservation.

---

### Q10: How do you prevent duplicate payment transactions?
**Architectural Answer:**  
1. The Payment Service derives a deterministic payment idempotency key: `hash(reservation_id, customer_id, amount)`.
2. This key is stored in PostgreSQL under a `UNIQUE` constraint index on `payment_transactions (idempotency_key)`.
3. When calling external gateways (Stripe/Adyen), this key is forwarded in the request header (`Idempotency-Key`).
4. If a network blip causes the client or service to retry the payment call, the external payment gateway recognizes the idempotency key, returns the existing charge record, and prevents a second charge against the user's card.

---

### Q11: What happens when payment succeeds but Order Service is down for 30 seconds?
**Architectural Answer:**  
This is the hackathon's defining reliability scenario. The system resolves it seamlessly:
1. When payment succeeds, the Payment Service updates the payment status to `PAID` and writes a `PaymentSuccessfulEvent` to its local **Transactional Outbox** table within a single ACID transaction.
2. The Outbox Relayer reads this event and publishes it to the durable Kafka topic `payment.success.events`.
3. Kafka writes the event to replicated disk across 3 broker nodes.
4. Because the Order Service is down for 30 seconds, the message sits safely at the uncommitted Kafka offset pointer.
5. Upstream payments continue to succeed; **payment is NEVER refunded**.
6. When Kubernetes restarts the Order Service pod at $t = 30\text{s}$, it reconnects to Kafka, consumes the buffered event, creates the confirmed order inside an idempotent transaction, and updates the user via WebSocket. Zero lost orders, zero data corruption.

---

### Q12: What happens when the same event is delivered twice?
**Architectural Answer:**  
The message broker operates under **At-Least-Once Delivery**. Downstream consumers implement the **Idempotent Consumer / Inbox Pattern**:
1. The consumer opens an ACID database transaction.
2. It executes:
   ```sql
   INSERT INTO processed_inbox (event_id, processed_at) VALUES ($event_id, NOW())
   ON CONFLICT (event_id) DO NOTHING;
   ```
3. If the insert succeeds (1 row affected), the consumer executes order creation and commits.
4. If a duplicate event arrives, `ON CONFLICT` triggers (0 rows affected). The consumer immediately skips business logic and commits the broker offset (ACK). No duplicate order or duplicate shipment is ever created.

---

### Q13: What happens when the message consumer continuously fails?
**Architectural Answer:**  
1. If a consumer encounters a transient error (e.g., database lock timeout), it retries with exponential backoff and decorrelated jitter (100ms, 500ms, 2000ms).
2. If the message fails consecutively **3 times** (indicating a permanent error or "Poison Pill", such as corrupted data), the consumer routes the message to a **Dead Letter Queue (DLQ)** topic (`order.creation.dlq`).
3. The consumer then commits its offset, preventing the poisoned message from blocking legitimate orders in the partition.
4. A high-priority PagerDuty operational alert is triggered for engineer inspection and replay.

---

### Q14: Where is the DLQ?
**Architectural Answer:**  
Dedicated Dead Letter Queues are configured in the distributed message broker for every asynchronous consumer pipeline:
1. `payment.events.dlq`: For unprocessable payment events.
2. `order.creation.dlq`: For poisoned order ingestion messages.
3. `shipment.dispatch.dlq`: For failed logistics manifest generations.
4. `notifications.dlq`: For un-deliverable SMS/Email events.

---

### Q15: Where is the circuit breaker?
**Architectural Answer:**  
Circuit breakers (Envoy / Resilience4j) are placed at every outbound synchronous network boundary:
1. **API Gateway $\rightarrow$ Internal Services:** Protects backend services if they experience degradation.
2. **Checkout Service $\rightarrow$ Inventory Service:** Trips to Open if reservation latency exceeds 300ms for $> 30\%$ of requests.
3. **Payment Service $\rightarrow$ External Payment Gateway:** Trips to Open if external gateway returns 5xx errors or socket timeouts for $> 20\%$ of requests, immediately falling back to a secondary payment gateway.

---

### Q16: What operations are synchronous?
**Architectural Answer:**  
1. Product catalog browsing and price queries (Client $\rightarrow$ Product Service via REST/CDN).
2. Cart item additions and coupon calculations (Client $\rightarrow$ Cart Service).
3. Inventory reservation allocation (Checkout $\rightarrow$ Inventory Service via gRPC).
4. Payment gateway charge authorization (Checkout $\rightarrow$ Payment Service $\rightarrow$ Bank Gateway).

---

### Q17: What operations are asynchronous?
**Architectural Answer:**  
1. Payment success $\rightarrow$ Order creation and invoice generation.
2. Payment success $\rightarrow$ Final inventory state transition (`CONFIRMED` $\rightarrow$ `SOLD`).
3. Order creation $\rightarrow$ Warehouse shipment batching and courier manifest generation.
4. System event triggers $\rightarrow$ Customer notifications (SMS, Email, Push).
5. Reservation lease expiry sweeper $\rightarrow$ Stock counter restoration.
6. Analytics and business intelligence event streaming.

---

### Q18: Why? (Justification for Sync vs. Async Demarcation)
**Architectural Answer:**  
- **Synchronous Justification:** Inventory reservation must be synchronous because scarcity allocation requires an immediate, deterministic answer. If a customer is not told immediately whether they secured stock, they cannot proceed to payment. Payment authorization must be synchronous because the user must verify fund transfer and complete 3D Secure before leaving the screen.
- **Asynchronous Justification:** Order creation, shipping manifests, and notifications operate in the domain of abundance and physical processing. A 1–2 second delay in creating an order database record does not harm the user experience, but decoupling it via asynchronous durable queues provides absolute fault tolerance against downstream crashes.

---

### Q19: What is the first bottleneck under flash-sale traffic?
**Architectural Answer:**  
The **First Bottleneck** is **Ingress Connection & Socket Exhaustion at the API Gateway**. 
At 500,000 requests/sec, half a million simultaneous TCP connections and TLS 1.3 cryptographic handshakes hit the load balancers, threatening to exhaust Linux kernel socket file descriptors (`net.core.somaxconn`) and epoll threads. 
*Mitigation:* Edge CDN caching of catalog assets, TLS session resumption, HTTP/2 multiplexing, and distributed token-bucket rate limiting at the WAF edge.

---

### Q20: What changes when traffic increases by 50×?
**Architectural Answer:**  
When traffic surges from 10,000 to 500,000 req/sec:
1. **API Gateway Tier:** Autoscales horizontally from 10 pods to 120 pods.
2. **Single-SKU Serialization:** Redis key sharding activates. Instead of routing all 500,000 requests to a single Redis shard key, inventory is partitioned across 10 virtual sub-shards (`stock:SKU:0` through `stock:SKU:9`), distributing CPU and network load across 10 independent Redis primary nodes.
3. **Database Isolation:** PostgreSQL read queries are routed across 8 read replicas; writes to primary remain strictly capped at $\le 100$ transactions via connection poolers (`PgBouncer`).
4. **Edge Shedding:** Non-essential services (product reviews, recommendations) are degraded or disabled at the edge to reserve 100% of bandwidth for checkout.

---

### Q21: How can the system reason about 500,000 req/sec?
**Architectural Answer:**  
We reason about 500,000 req/sec through the mathematical principle of **Traffic Funneling and Early Shedding**:
- **At Edge (CDN/WAF):** $90\%$ of traffic (450,000 req/s) consists of catalog browsing and read queries, which are served entirely from CDN edge PoPs with 0ms origin load.
- **At API Gateway:** Out of the remaining 50,000 req/s write attempts, rate limiters drop duplicate bot clicks.
- **At In-Memory Contention Engine:** Once the 100 units are allocated (within 100ms), an in-memory boolean flag `is_sold_out` is set at the gateway, collapsing the remaining reservation attempts into fast-fail 409 responses in $< 1\text{ ms}$.
- **At Relational DB:** Database writes never exceed 100 operations. The system scales by ensuring that extreme traffic never reaches stateful bottlenecks.

---

### Q22: What are the strict consistency guarantees?
**Architectural Answer:**  
1. **Conservation of Units:** $\text{Available} + \text{Reserved} + \text{Sold} \equiv 100$ at all times.
2. **Zero Overselling:** Confirmed sales will never exceed 100 ($\text{Sold} \le 100$).
3. **Non-Negative Inventory:** Available stock can never be negative ($\text{Available} \ge 0$).
4. **Deterministic Tie-Breaking:** For the final unit ($N=1$), exactly one request commits and all concurrent competitors receive failure.
5. **Zero Double-Charges:** No customer is charged twice for the same reservation lease.

---

### Q23: What are the performance targets?
**Architectural Answer:**  
1. **Reservation Latency:** $p50 < 45\text{ ms}$, $p99 < 150\text{ ms}$.
2. **Catalog Read Latency:** $p99 < 30\text{ ms}$ at the edge.
3. **Order Finalization:** $p99 < 2,000\text{ ms}$ from payment confirmation to order DB write.
4. **Recovery Time Objective (RTO):** $< 60\text{ seconds}$ for crashed stateless pods; $< 15\text{ seconds}$ for database master failover.
5. **Recovery Point Objective (RPO):** Exactly $0\text{ seconds}$ (zero lost transactional data).

---

### Q24: What are the major architecture trade-offs?
**Architectural Answer:**  
1. **Consistency vs. Availability (CAP Theorem):** On the inventory reservation path, we sacrifice availability in favor of strict consistency (CP). If Redis becomes completely unavailable across all replicas, the system fails closed rather than allowing uncoordinated writes that could oversell stock.
2. **Synchronous Simplicity vs. Asynchronous Decoupling:** We accept the complexity of the Transactional Outbox pattern, message brokers, and idempotent consumers in order to gain immunity against downstream service outages.
3. **Dual-State Management:** By using Redis for atomic contention and PostgreSQL for durability, we accept the overhead of maintaining synchronization between in-memory caches and relational databases.

---

### Q25: Why is this architecture better than the alternatives considered?
**Architectural Answer:**  
- **Superior to Monolithic SQL Row Locking:** Because it does not collapse under 10,000 concurrent threads, does not exhaust connection pools, and preserves a sub-150ms user experience.
- **Superior to Pure Optimistic Locking:** Because it completely eliminates the catastrophic retry storm that occurs when 9,999 transactions fail validation on a single row simultaneously.
- **Superior to "Event-Driven Everything" Queuing:** Because it provides the customer with immediate, deterministic feedback on whether they won the flash-sale item, rather than forcing them to wait 15 minutes for an email notification.
- **Defensible & Operationally Sound:** It strictly guarantees zero overselling, gracefully weathers a 30-second Order Service crash with zero lost orders, and scales linearly to 500,000 req/sec through multi-tier traffic shedding.
