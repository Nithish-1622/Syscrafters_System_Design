# SALESTORM — Scalability Strategy & 50× Traffic Surge Architecture

**Document Version:** 1.0.0  
**Status:** Approved Architecture Baseline  
**Lead Author:** Member 1 (System Architect + Concurrency, Inventory & Scalability Lead)  
**Target Audience:** Core Engineering Team (Members 2, 3, 4), Technical Jury, Operations  

---

## 1. Scalability Principles & Traffic Envelopes

The SALESTORM platform is engineered to handle two distinct operational regimes:
1. **Steady-State Baseline Traffic:** Approximately **10,000 requests/sec** distributed across browsing, searching, cart updates, and standard purchases.
2. **Flash-Sale Burst Traffic:** An extreme **50× surge up to 500,000 requests/sec** arriving within a 1-to-5 second window, highly concentrated on specific promotional endpoints and a limited number of flash-sale SKUs.

```
Steady State (10,000 req/s) ──────► 50x Surge ──────► Flash Peak (500,000 req/s)
[Distributed across 100K SKUs]                         [Concentrated on 1-10 Flash SKUs]
```

### The Fundamental Flash-Sale Law
> *“You cannot scale a single relational database row to 500,000 writes per second.”*  
> True horizontal scalability requires **traffic classification and shedding at the edge**, **sub-millisecond in-memory atomic contention arbitration**, and **complete asynchronous decoupling of downstream write paths**.

---

## 2. Component-by-Component Horizontal Scaling Architecture

To support a 50× surge without service collapse, every tier must have a concrete, measurable scaling vector:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               COMPONENT SCALING SPECIFICATION                                    │
├────────────────────┬────────────────────┬───────────────────────────────────┬────────────────────┤
│ Tier / Component   │ Scaling Vector     │ Sizing @ 10,000 req/s             │ Sizing @ 500,000   │
├────────────────────┼────────────────────┼───────────────────────────────────┼────────────────────┤
│ Edge CDN / WAF     │ Anycast PoP Edge   │ Standard Global CDN Caching       │ Aggressive Edge PoP│
│ Application LB     │ Regional DNS + LBs │ 4 Multi-AZ Ingress Nodes          │ 32 Scaled Ingress  │
│ API Gateway Tier   │ Stateless Pods     │ 10 Pods (2 vCPU, 4GB RAM)         │ 120 Pods (HPA)     │
│ Product Service    │ Stateless Pods     │ 8 Pods + Redis Replica Cluster    │ 60 Pods (Memcache) │
│ Inventory Service  │ Stateless Pods     │ 8 Pods + Redis Cluster Shards     │ 80 Pods            │
│ Redis In-Memory    │ Sharded Cluster    │ 3 Shards (Master/Replica)         │ 16 Shards + Pipel. │
│ Message Broker     │ Kafka Partitions   │ 12 Partitions across 3 Brokers    │ 64 Partitions (6B) │
│ Order Service      │ Event Consumer Pods│ 6 Consumer Instances              │ 64 Consumers (1:1) │
│ PostgreSQL RDBMS   │ Primary + Replicas │ 1 Master + 2 Read Replicas (Pool) │ 1 Master + 8 Rep.  │
│ Payment Outbound   │ Rate-Limited Queue │ Direct Sync Calls                 │ Throttled 2K TPS Q │
└────────────────────┴────────────────────┴───────────────────────────────────┴────────────────────┘
```

### Detailed Tier Analysis:

1. **Edge CDN & WAF (Ingress Defense):**
   - **Mechanism:** Serves $95\%$ of static product catalog assets (images, CSS, JS, product specs) directly from global edge caches (Cloudflare / CloudFront).
   - **Surge Action:** WAF enforces IP reputation scoring, validates CAPTCHA for suspicious automated scrapers, and executes Edge Micro-Caching (caching product availability for 500ms to collapse read spikes).

2. **API Gateway Tier (Stateless Reverse Proxy):**
   - **Mechanism:** Built on non-blocking, event-driven networking (Envoy / Netty / Go).
   - **Surge Action:** Horizontal Pod Autoscaler (HPA) scales pods from 10 to 120 based on CPU ($> 65\%$) and open HTTP connections. TLS 1.3 session resumption prevents expensive repeated cryptographic handshakes.

3. **Stateless Business Services (Checkout, Inventory, Product):**
   - **Mechanism:** Pods maintain zero in-memory session state; all state resides in Redis or PostgreSQL.
   - **Surge Action:** Compute instances scale horizontally across 3 Availability Zones. Container spin-up is pre-warmed 15 minutes prior to scheduled flash sales (Scheduled Scaling) to eliminate cold-start latency.

4. **In-Memory Contention Engine (Redis Cluster):**
   - **Mechanism:** Redis Cluster partitioned by hash slots based on `product_id`.
   - **Flash SKU Handling:** Flash SKUs are distributed across dedicated high-memory Redis shards. Single Redis instances handle $100,000+\text{ Lua operations/sec}$. With 8–16 dedicated shards, Redis comfortably absorbs the 500,000 req/s contention boundary.

5. **Message Broker (Distributed Commit Log):**
   - **Mechanism:** Kafka topic `payment.success.events` configured with **64 partitions**.
   - **Surge Action:** Order Service consumer group scales to exactly 64 active consumer pods (1 consumer per partition), guaranteeing max parallel event consumption with strict per-partition ordering.

6. **Relational Database (PostgreSQL) Protection:**
   - **Mechanism:** PostgreSQL Primary is **never exposed to unthrottled traffic**.
   - **Surge Action:** Writes are capped to the $\le 100$ successful reservations. Read traffic (order history, user profiles) is completely offloaded to 8 Read Replicas via connection poolers (`PgBouncer`). Primary RDBMS handles $< 200\text{ writes/sec}$, running at $< 15\%$ CPU load even during a 500,000 req/s ingress storm.

---

## 3. The Three Critical System Bottlenecks Under 50× Surge

When traffic scales from 10,000 to 500,000 req/sec, physical bottlenecks emerge sequentially. Here is our technical breakdown of each bottleneck and its definitive mitigation:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          CHRONOLOGICAL BOTTLENECK PROGRESSION                          │
├────────────────────┬────────────────────────────────────┬──────────────────────────────┤
│ Bottleneck Order   │ Location & Failure Mode            │ Engineering Mitigation       │
├────────────────────┼────────────────────────────────────┼──────────────────────────────┤
│ 1st Bottleneck     │ Ingress & Gateway Connection Storm │ Edge Rate Limiting & Shedding│
│ 2nd Bottleneck     │ Single-SKU In-Memory Hotspot Cont. │ Fast-Fail Edge Token Caching │
│ 3rd Bottleneck     │ External Payment Gateway Rate Cap  │ Tokenized Asynchronous Queue │
└────────────────────┴────────────────────────────────────┴──────────────────────────────┘
```

---

### FIRST BOTTLENECK: Ingress Connection Saturation & Gateway Thread Starvation

#### Why it becomes a bottleneck:
At 500,000 requests/sec, half a million incoming TCP connections hit the load balancer simultaneously. Each connection consumes a socket file descriptor, memory for TLS handshake buffers, and epoll listener threads. Unmitigated, the Linux kernel TCP accept queue overflows (`SYN flood` symptoms), leading to packet drops, dropped connections, and `504 Gateway Timeout` errors before requests ever reach application logic.

#### Behavior under 10K vs. 500K:
- **At 10K req/s:** Modern load balancers easily handle 10,000 concurrent sockets with $< 5\text{ ms}$ latency.
- **At 500K req/s:** Without rate limiting, the system requires over 500,000 active sockets, exhausting Linux ephemeral port ranges and socket memory limits (`net.core.somaxconn` and `fs.file-max`).

#### Architectural Mitigation:
1. **Edge Shedding & HTTP/2 Multiplexing:** Mobile apps and browsers multiplex multiple requests over a single persistent TCP connection.
2. **Distributed Leaky Bucket Rate Limiting:** Enforced at the API Gateway using Redis sliding windows:
   - Max 1 reservation request per 5 seconds per authenticated `user_id`.
   - Max 10 requests per minute per unauthenticated IP address.
3. **Early Fast-Fail Gate:** As soon as inventory hits zero in Redis, the Inventory Service broadcasts a lightweight event to the API Gateway cluster:
   ```json
   {"event": "FLASH_SKU_DEPLETED", "product_id": "SKU_X", "ttl_seconds": 600}
   ```
   Gateways store this boolean flag in local memory (Go sync.Map / Envoy filter). Subsequent requests for `SKU_X` are rejected **directly at the gateway edge in $< 1\text{ ms}$ with HTTP 409 (Sold Out)** without touching backend microservices, network links, or databases!

---

### SECOND BOTTLENECK: Single-SKU Redis Shard Network & CPU Saturation

#### Why it becomes a bottleneck:
Even though Redis is extremely fast ($\sim 100,000\text{ ops/sec}$ per core), a sudden burst of 500,000 requests/sec targeted at **a single SKU** routes to **a single Redis shard** (since hash slots are calculated by `hash(product_id) % 16384`). That single Redis node's CPU core will saturate at 100%, and its network bandwidth will become saturated with TCP payload overhead.

#### Behavior under 10K vs. 500K:
- **At 10K req/s:** Single Redis node easily handles 10,000 Lua script executions with $< 2\text{ ms}$ latency and $< 20\%$ CPU.
- **At 500K req/s:** Single Redis node is overwhelmed by $5\times$ its maximum theoretical single-core throughput.

#### Architectural Mitigation:
1. **Virtual Stock Sharding (Token Sub-Bucketing):**  
   For extreme 500K campaigns, the 100 units of Product X are partitioned into 10 sub-keys across multiple Redis shards:
   - `stock:item:X:shard:1` = 10 units
   - `stock:item:X:shard:2` = 10 units
   - ...
   - `stock:item:X:shard:10` = 10 units
   Incoming requests are hashed across shards: `shard_id = hash(user_id) % 10`. This distributes the 500,000 req/s contention evenly across 10 independent Redis primary nodes, reducing the per-node load to a manageable 50,000 req/s!
2. **Token Bucket Pre-Filtering:**  
   The API Gateway maintains an atomic token bucket for the flash sale. Only the first 500 requests are allowed to proceed to Redis; all subsequent requests are dropped immediately.

---

### THIRD BOTTLENECK: External Payment Gateway Throughput Limits

#### Why it becomes a bottleneck:
External payment processors (Stripe, Adyen, Worldpay) and acquiring banks are external third-party systems outside our infrastructure control. They enforce hard API rate limits (typically $1,000\text{ to }2,000\text{ TPS}$). If 10,000 customers all attempt to submit credit card authorizations within a 2-second window, the payment gateway will return `429 Too Many Requests` or drop connections.

#### Behavior under 10K vs. 500K:
- **At 10K overall traffic:** Payment requests arrive naturally staggered across multiple minutes.
- **At 500K flash traffic:** If 100 reservation winners proceed immediately, 100 TPS is well within gateway limits. However, if a flash sale has 5,000 units and 500K users, 5,000 concurrent payment calls would breach the 2,000 TPS ceiling.

#### Architectural Mitigation:
1. **Natural Human Latency Buffer (The 300-Second Lease Window):**  
   Because customers receive a guaranteed 300-second reservation lease, they do not submit payments simultaneously. Human actions (entering CVV, selecting payment method, receiving SMS OTP for 3D Secure) naturally smooth the payment authorization curve over 60–180 seconds.
2. **Outbound Payment Rate Limiter & Leaky Bucket:**  
   The Payment Service implements a token-bucket rate limiter that caps outbound calls to external gateway APIs to **1,500 TPS** (safely below the 2,000 TPS hard ceiling). Excess requests are held in a high-priority FIFO queue for up to 3 seconds before transmission.

---

## 4. Connection Pooling & Resource Budgeting Under 500K Surge

To prevent downstream database collapse during load spikes, strict resource budgeting is enforced at every network interface:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              CONNECTION BUDGETING MATRIX                               │
├──────────────────────┬───────────────────────┬───────────────────┬─────────────────────┤
│ Service Tier         │ Thread Pool Model     │ Connection Pooler │ Max Pool Allocation │
├──────────────────────┼───────────────────────┼───────────────────┼─────────────────────┤
│ API Gateway          │ Non-blocking Epoll    │ Keep-Alive Pool   │ 50,000 Open Sockets │
│ Inventory Service    │ Virtual Threads (Loom)│ Lettuce (Redis)   │ 200 Netty Channels  │
│ Inventory DB Access  │ HikariCP JDBC Pool    │ PgBouncer (Tx Mode)│ Max 50 per Instance │
│ PostgreSQL Engine    │ Dedicated OS Processes│ PgBouncer Proxy   │ Max 300 Server Conns│
│ Kafka Producers      │ Async Buffer Pool     │ Kafka Producer SDK│ 64MB In-Memory Batch│
└──────────────────────┴───────────────────────┴───────────────────┴─────────────────────┘
```

### HikariCP & PgBouncer Configuration Formula
Direct database connections are limited:
$$\text{Max DB Connections} = (\text{Core Count} \times 2) + \text{Effective Spindle Count}$$
For a 16-core PostgreSQL primary instance:
$$\text{Max DB Connections} \approx (16 \times 2) + 1 = 33\text{ active connections}$$
`PgBouncer` multiplexes up to 5,000 application client connections over these 33 active transaction-level server connections, preventing database latch contention and memory swapping under peak traffic.

---

*End of 01_Scalability_Strategy.md — Authoritative Scalability Blueprint.*
