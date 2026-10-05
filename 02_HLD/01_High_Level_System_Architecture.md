# SALESTORM — High-Level System Architecture (HLD)

**Document Version:** 1.0.0  
**Status:** Approved Architecture Baseline  
**Lead Author:** Member 1 (System Architect + Concurrency, Inventory & Scalability Lead)  
**Target Audience:** Core Engineering Team (Members 2, 3, 4), Technical Jury, Operations  

---

## 1. Architectural Philosophy & Core Tenets

The SALESTORM architecture is built on three uncompromising principles designed specifically for extreme contention flash-sale e-commerce:

1. **Isolation of the Contention Hotspot (Single-SKU Serialization Boundary):**  
   Under a flash sale where 10,000 users contend for 100 units of a single product, traditional ACID database row-locking collapses due to thread pool exhaustion, latch contention, lock waiting timeouts, and deadlocks. We decouple high-frequency atomic contention checks from durable business transactional persistence using a multi-tiered reservation architecture.

2. **Synchronous Boundary for Scarcity, Asynchronous Pipeline for Abundance:**  
   The decision to allocate scarce stock must be **synchronous, atomic, and deterministic**. Once the reservation lease is established, downstream business operations (payment callbacks, order generation, invoice generation, warehouse routing, notifications) transition to **asynchronous, durable, event-driven pipelines** that provide fault isolation and absorb traffic spikes without backpressuring the user.

3. **Zero Data Loss via Transactional Outbox & Idempotent Receivers:**  
   Every state change that triggers a downstream event is committed in an atomic local database transaction alongside an Outbox record. Downstream consumers guarantee idempotent processing, ensuring that network partitions, service crashes (such as an Order Service 30-second outage), and duplicate deliveries converge on identical, valid business states.

---

## 2. Logical Service Boundaries & State Ownership

The SALESTORM domain is partitioned into eight bounded contexts adhering strictly to Domain-Driven Design (DDD) principles. Each microservice encapsulates its own data store to ensure zero database-level coupling.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   SALESTORM BOUNDED CONTEXTS                                    │
├──────────────────────┬────────────────────────┬─────────────────────────────────────────────────┤
│ Microservice         │ Primary Protocol       │ Encapsulated State / Datastore                  │
├──────────────────────┼────────────────────────┼─────────────────────────────────────────────────┤
│ Product Service      │ Sync (REST / gRPC)     │ Product Catalog, Categories, Search Metadata    │
│ Cart Service         │ Sync (REST / Redis)    │ Transient Shopping Baskets, Applied Coupons     │
│ Inventory Service    │ Sync (gRPC) + Async    │ Stock Balances, Active Leases, Reservation TTLs │
│ Checkout Service     │ Sync (REST Orchestr.)  │ Checkout Sessions, Pricing & Tax Calculations   │
│ Payment Service      │ Sync (Gateway) + Async │ Payment Transactions, Gateway Webhook States    │
│ Order Service        │ Async (Event Ingest)   │ Immutable Orders, Line Items, Order Lifecycle   │
│ Shipment Service     │ Async (Event Ingest)   │ Waybills, Courier Batches, Transit Checkpoints  │
│ Notification Service │ Async (Worker Queue)   │ Communication Logs, Notification Templates      │
└──────────────────────┴────────────────────────┴─────────────────────────────────────────────────┘
```

---

## 3. Deep Component Analysis: The 5 Fundamental Architectural Questions

In accordance with enterprise system design standards, every core service must answer five technical criteria:

### A. Product Service
1. **WHY does it exist?**  
   To decouple high-volume catalog browsing and discovery traffic from operational transaction processing.
2. **WHAT problem does it solve?**  
   Prevents millions of read requests (browsing, product specifications, images) from placing load on transactional checkout and inventory databases.
3. **WHAT happens if it fails?**  
   Edge CDN and reverse proxies serve stale cached catalog pages. The site remains browsable, but new product edits or updates are suspended until recovery.
4. **HOW does it scale?**  
   Horizontally stateless. Scales near-infinitely behind a CDN and distributed read-through cache (Redis Replica cluster).
5. **WHAT state does it own?**  
   `products`, `categories`, `media_assets`, `specifications`.

### B. Cart Service
1. **WHY does it exist?**  
   To manage transient shopping baskets across user sessions without creating artificial inventory scarcity.
2. **WHAT problem does it solve?**  
   Allows multi-item accumulation, coupon validations, and cart persistence across devices without holding database write-locks.
3. **WHAT happens if it fails?**  
   Users cannot modify existing carts; however, the express "Buy Now" flash-sale flow bypasses the Cart Service entirely, shielding the flash sale from cart failures.
4. **HOW does it scale?**  
   Stateless compute instances backed by an in-memory Redis cluster partitioned by `user_id`.
5. **WHAT state does it own?**  
   `cart_sessions`, `cart_items`, `applied_promotions`.

### C. Inventory Service (The Critical Hotspot Service)
1. **WHY does it exist?**  
   To maintain the absolute mathematical truth of product stock balances and govern time-bounded reservation leases.
2. **WHAT problem does it solve?**  
   Solves the 10,000-to-100 race condition. Guarantees that available stock cannot be oversold, prevents negative inventory, and deterministic tie-breaking on the final available unit.
3. **WHAT happens if it fails?**  
   All new reservations are rejected immediately (Fail-Closed). Existing uncommitted reservations hold their leases until the service or sweeper reconciles them. No overselling can ever occur.
4. **HOW does it scale?**  
   Two-tier architecture: In-Memory atomic Lua scripts on Redis Cluster (sharded by `product_id`) for lightning-fast atomic decrements ($< 2\text{ ms}$), backed by a PostgreSQL cluster using Optimistic Concurrency Control (OCC) and Transactional Outbox.
5. **WHAT state does it own?**  
   `inventory (available_qty, reserved_qty, sold_qty, version)`, `inventory_reservations (reservation_id, user_id, expires_at, status)`.

### D. Checkout Service
1. **WHY does it exist?**  
   To act as the saga/orchestration facade for the customer purchase journey.
2. **WHAT problem does it solve?**  
   Aggregates user address, tax computation, discount logic, and pairs the customer session with an active `reservation_id` before routing to payment.
3. **WHAT happens if it fails?**  
   In-flight checkout sessions stall. Customers can retry with their existing `idempotency_key`, which recovers their existing reservation without re-deducting stock.
4. **HOW does it scale?**  
   Completely stateless compute nodes. Auto-scales based on incoming HTTP request concurrency.
5. **WHAT state does it own?**  
   Ephemeral checkout orchestrator tokens; no permanent business master state.

### E. Payment Service
1. **WHY does it exist?**  
   To encapsulate external payment gateway integrations, handle tokenized credit card transactions, and guarantee payment idempotency.
2. **WHAT problem does it solve?**  
   Shields internal systems from external payment gateway latency, rate limits, and network flakiness. Guarantees a customer is never double-charged.
3. **WHAT happens if it fails?**  
   Out-of-band reconciliation workers query payment gateway APIs using the client's unique `payment_idempotency_key` to resolve indeterminate transactions.
4. **HOW does it scale?**  
   Stateless worker nodes fronted by asynchronous worker pools that throttle gateway outbound traffic to stay within payment provider rate limits ($2,000\text{ TPS}$).
5. **WHAT state does it own?**  
   `payment_transactions (transaction_id, reservation_id, amount, status, gateway_ref, idempotency_key)`.

### F. Order Service
1. **WHY does it exist?**  
   To record and manage the immutable, legal business contract of a completed sale and drive the fulfillment lifecycle.
2. **WHAT problem does it solve?**  
   Maintains the canonical order record. Decouples the fast checkout/payment pipeline from downstream warehouse fulfillment and delivery tracking.
3. **WHAT happens if it fails (e.g., 30-Second Crash Scenario)?**  
   Upstream payments continue to succeed! Payment success events are durably buffered in the message broker. When the Order Service restarts, it processes the backlog idempotently. Zero orders or payments are lost.
4. **HOW does it scale?**  
   Event consumer worker groups partitioned by `order_id` / `customer_id`. Scaled horizontally to consume from message broker partitions.
5. **WHAT state does it own?**  
   `orders (order_id, customer_id, total, status, created_at)`, `order_items (order_id, product_id, quantity, price)`.

### G. Shipment Service
1. **WHY does it exist?**  
   To manage warehouse logistics, package allocation, courier integrations, and tracking number assignment.
2. **WHAT problem does it solve?**  
   Isolates physical delivery complexities and external carrier API latencies from core e-commerce transactions.
3. **WHAT happens if it fails?**  
   Orders remain in `CONFIRMED` or `PROCESSING` state in the Order database. Fulfillment resumes as soon as logistics integration is restored.
4. **HOW does it scale?**  
   Asynchronous background workers pulling from a fulfillment queue.
5. **WHAT state does it own?**  
   `shipments`, `waybills`, `tracking_events`, `carrier_manifests`.

### H. Notification Service
1. **WHY does it exist?**  
   To manage multi-channel customer communications (Email, SMS, Push notifications, WebSockets).
2. **WHAT problem does it solve?**  
   Prevents external communication latency (SMTP/SMS gateway delays) from degrading order or payment response times.
3. **WHAT happens if it fails?**  
   Notifications are retried via Dead Letter Queues (DLQ). Core e-commerce and inventory states are **never rolled back** due to notification failures.
4. **HOW does it scale?**  
   Stateless consumer workers pulling from dedicated notification message queues.
5. **WHAT state does it own?**  
   `notification_logs`, `delivery_receipts`, `templates`.

---

## 4. Synchronous vs. Asynchronous Communication Matrix

The decision to use synchronous versus asynchronous communication is a fundamental architectural boundary. We reject the anti-pattern of "making everything asynchronous" just because the architecture is distributed.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              COMMUNICATION BOUNDARY MAP                                │
├───────────────────────────────────────────┬────────────────────────────────────────────┤
│ SYNCHRONOUS (Tight Consistency Boundary)  │ ASYNCHRONOUS (Eventual Consistency & Scale)│
├───────────────────────────────────────────┼────────────────────────────────────────────┤
│ • Product Read / Availability Query       │ • Payment Success → Order Creation         │
│ • Cart Item Modification                  │ • Reservation Expiry → Stock Release       │
│ • Inventory Reservation (Buy Now)         │ • Order Creation → Shipment Allocation     │
│ • Checkout Orchestration                  │ • Order / Shipping Events → Notifications  │
│ • Payment Gateway Charge Authorization    │ • Analytics, Audit & Business Intelligence │
└───────────────────────────────────────────┴────────────────────────────────────────────┘
```

### Comprehensive Technical Justification Table

| Business Operation | Source Service $\rightarrow$ Target Service | Protocol / Mode | Architectural Reasoning | Failure Handling Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **Product Detail Read** | Client $\rightarrow$ Product Service | **Synchronous** (HTTP/REST) | The customer requires immediate UI feedback to view product details, pricing, and specs before deciding to buy. | Edge CDN caching; fallback to local replica cache; default to stale cache if origin is unreachable. |
| **Inventory Reservation** | Checkout $\rightarrow$ Inventory Service | **Synchronous** (gRPC) | **Scarcity Allocation:** The customer must know deterministically within $< 150\text{ ms}$ whether they secured the item or if it is sold out. Async queueing here causes user frustration and race conditions. | Fast-fail: Return `409 Conflict` (Sold Out) immediately if balance $< 1$. Circuit breaker on Inventory Service. |
| **Payment Authorization** | Checkout $\rightarrow$ Payment Service | **Synchronous** (HTTPS) | Payment authorization requires immediate verification with customer bank / 3DS challenge. User must confirm transaction status before leaving screen. | Timeout after 3,000ms; query gateway with `idempotency_key`; if failed, release inventory reservation immediately. |
| **Order Creation** | Payment Service $\rightarrow$ Order Service | **Asynchronous** (Durable Event Bus) | **Decoupling & Resilience:** Payment is legally settled. Order record creation should not block the user. If Order Service crashes for 30s, the message sits safely in broker. | Message retained in durable broker (retention = 7 days); consumer retries with exponential backoff; DLQ after 5 attempts. |
| **Inventory Commitment (Sold)**| Payment Service $\rightarrow$ Inventory Service | **Asynchronous** (Durable Event Bus) | Transitioning state from `RESERVED` to `SOLD` does not impact available stock (it is already decremented). Can be processed asynchronously. | Event consumer updates RDBMS `reserved_qty -= 1, sold_qty += 1`. Re-deliverable and idempotent via `reservation_id`. |
| **Stock Release (On Cancel/Expiry)**| Scheduler/Payment $\rightarrow$ Inventory | **Asynchronous** (Delayed Queue) | Releasing stock back to available pool upon payment failure or TTL expiry is an internal maintenance event that can tolerate a 1–2 second delay. | Dead-man switch / TTL sweeper; atomic increment in Redis & RDBMS: `available_qty += 1, reserved_qty -= 1`. |
| **Shipment Creation** | Order Service $\rightarrow$ Shipment Service | **Asynchronous** (Message Queue) | Physical warehouse packaging and carrier assignment operates on human/robotic timescales (minutes/hours), completely decoupled from online checkout. | Retried via queue; dead-lettering for invalid shipping addresses; manual ops dashboard for stuck shipments. |
| **Customer Notifications** | Event Bus $\rightarrow$ Notification Service | **Asynchronous** (Fan-out Queue) | External SMS/Email gateways have unpredictable latency (2–10 seconds). Must never be in the critical checkout synchronous call path. | Non-blocking; background worker retry with jitter; failures logged to DLQ; does not affect order status. |

---

## 5. High-Traffic Request Path: The 10,000-to-100 Flash Sale Execution

Here we trace technical execution when **10,000 authenticated users simultaneously click "BUY NOW" at $t = 0$** for a flash-sale item with only **100 units** available.

```
10,000 Concurrent Users (t = 0)
    │
    ▼
[Cloudflare / Edge CDN + WAF] ─── Bot filtering & Rate limiting (DDoS Protection)
    │
    ▼
[Application Load Balancer (ALB)] ─── TLS Termination & Least-Outstanding-Requests Routing
    │
    ▼
[API Gateway Cluster] ─── JWT Validation, Token Bucket Rate Limiting, Header Verification
    │
    ▼
[Checkout Service Instances] ─── Fast-Track Request Formulation & Idempotency Key Injection
    │
    ▼ (Synchronous gRPC)
[Inventory Reservation Engine]
    ├── Tier 1: In-Memory Redis Lua Engine (Atomic Contention Serialization)
    │     ├── First 100 requests: Decrement available_stock (100 -> 0) ──► SUCCESS (HTTP 200)
    │     └── Next 9,900 requests: Stock == 0 ─────────────────────────► FAST FAIL (HTTP 409)
    │
    ▼ (First 100 Successful Reservations Only)
[PostgreSQL Inventory DB] ─── Async Write-Behind / Transactional Outbox (Durable Lease Record)
    │
    ▼
[Customer Proceeds to Payment] ─── 300-Second TTL Lease Active
```

### Step-by-Step Technical Execution Breakdown:

1. **Ingress, Filtering & Edge Routing ($t = 0\text{ to }15\text{ ms}$):**
   - 10,000 HTTP POST requests hit the Edge WAF. WAF scrubs automated scrapers and bots via challenge tokens.
   - Load Balancer terminates TLS 1.3 connections across multi-AZ ingress instances and distributes requests to the API Gateway tier using round-robin with least-connections weighting.

2. **Gateway Verification & Rate Limiting ($t = 15\text{ to }30\text{ ms}$):**
   - API Gateway validates the signed JWT in the `Authorization` header, extracting `user_id`.
   - Redis-backed sliding-window rate limiter ensures no single `user_id` or IP sends more than 1 reservation request per 10 seconds. Duplicate client clicks ($2\%$ expected per brief) are caught at this layer via `idempotency_key` deduplication.

3. **Routing to Inventory Reservation Engine ($t = 30\text{ to }45\text{ ms}$):**
   - Checkout instances forward the request via high-performance binary gRPC with HTTP/2 multiplexing to the `Inventory Service`.
   - The Inventory Service does **NOT** issue a raw `SELECT ... FOR UPDATE` on the relational database. Doing so would cause 10,000 concurrent threads to queue on a single row lock, resulting in lock wait timeouts, thread pool starvation, and database CPU spiking to $100\%$.

4. **Atomic Serialization in Redis via Lua Script ($t = 45\text{ to }60\text{ ms}$):**
   - Redis processes commands on a single-threaded event loop. A single Redis Lua script executes atomically for the target SKU key `stock:item:X`:
     ```lua
     local stock = tonumber(redis.call('get', KEYS[1]))
     if stock == nil or stock < tonumber(ARGV[1]) then
         return -1 -- Out of stock / Sold out
     end
     redis.call('decrby', KEYS[1], ARGV[1])
     redis.call('hset', KEYS[2], ARGV[2], ARGV[3]) -- Store reservation lease
     return 1 -- Reservation success
     ```
   - Because Redis executes this Lua script atomically with zero intervening commands:
     - **Requests 1 through 100:** Decrement the counter from $100 \rightarrow 0$. Each receives return code `1` (SUCCESS).
     - **Request 101 through 10,000:** Observe counter $\le 0$. Each receives return code `-1` (OUT OF STOCK).

5. **Immediate Client Response Demarcation ($t = 60\text{ to }90\text{ ms}$):**
   - **For the 9,900 unsuccessful requests:** The Inventory Service immediately returns `HTTP 409 Conflict` (Payload: `{"status": "SOLD_OUT", "message": "All flash sale inventory has been reserved."}`). These requests are terminated safely in $< 100\text{ ms}$ with zero database queries.
   - **For the 100 successful requests:** The Inventory Service generates a unique `reservation_id` (UUIDv4) and registers a reservation lease with `expires_at = now() + 300s`.

6. **Durable Persistence & Transactional Outbox ($t = 90\text{ to }120\text{ ms}$):**
   - The 100 successful reservations are persisted to PostgreSQL:
     ```sql
     INSERT INTO inventory_reservation (reservation_id, product_id, user_id, quantity, status, expires_at, idempotency_key)
     VALUES ($1, $2, $3, 1, 'RESERVED', NOW() + INTERVAL '5 MINUTE', $4);
     ```
   - An `InventoryReservedEvent` is written to the `outbox_events` table in the same ACID transaction.
   - The client receives `HTTP 200 OK` with `reservation_id` and is directed to the checkout payment screen with a 5-minute countdown timer.

---

## 6. End-to-End Bottleneck Identification & Engineering Mitigations

A senior distributed systems architect never claims "infinite scalability." Under high-scale flash sales, physical and logical bottlenecks exist at specific boundaries:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SYSTEM BOTTLENECK PROFILE                                 │
├──────┬───────────────────────────────┬─────────────────────────────────────────────────┤
│ Tier │ Physical Bottleneck Location   │ Architectural Mitigation Mechanism              │
├──────┼───────────────────────────────┼─────────────────────────────────────────────────┤
│ 1st  │ Single-SKU Row Contention      │ Decoupled Redis Lua Atomic Decrement            │
│ 2nd  │ Ingress Connection Pool Sat.  │ Edge Rate Limiting + Keep-Alive HTTP/2 Multiplex│
│ 3rd  │ External Payment Gateway TPS   │ Asynchronous Queueing + Client Idempotency Keys │
│ 4th  │ DB Connection Pool Exhaustion  │ PgBouncer / Connection Pooling + Outbox Pattern │
└──────┴───────────────────────────────┴─────────────────────────────────────────────────┘
```

1. **Bottleneck #1: Single-SKU Lock Contention:**  
   *Problem:* 10,000 requests contending on a single database row.  
   *Mitigation:* Single-threaded atomic in-memory serialization in Redis. Database is shielded from 99% of requests.
2. **Bottleneck #2: Connection & Thread Exhaustion at Ingress:**  
   *Problem:* 10,000 simultaneous TCP handshakes and TLS negotiations exhaust socket descriptors at the API Gateway.  
   *Mitigation:* Edge CDN connection pooling, TLS session resumption, non-blocking asynchronous event loop gateways (Netty/Envoy), and aggressive rate limiting on unauthenticated IPs.
3. **Bottleneck #3: Third-Party Payment Gateway Limits:**  
   *Problem:* Banks and payment gateways typically enforce hard limits (e.g., max 2,000 transactions/second).  
   *Mitigation:* Staggered user payment completion (natural human latency entering OTP/CVV over the 300-second reservation window smooths the payment curve). Outbound gateway rate limiters prevent overwhelming payment endpoints.
4. **Bottleneck #4: Database Connection Pool Limits:**  
   *Problem:* Each backend service instance maintaining 50 DB connections can overwhelm PostgreSQL connection limits (max ~1,000 connections).  
   *Mitigation:* Stateless microservices connect via `PgBouncer` connection poolers operating in transaction pooling mode. Read queries are routed to read replicas, preserving the primary master exclusively for writes.

---

*End of 01_High_Level_System_Architecture.md — Authoritative HLD Blueprint.*
