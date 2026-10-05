# SALESTORM — Requirements, Assumptions & Engineering Guarantees Specification

**Document Version:** 1.0.0  
**Status:** Approved Architecture Baseline  
**Lead Author:** Member 1 (System Architect + Concurrency, Inventory & Scalability Lead)  
**Target Audience:** Core Engineering Team (Members 2, 3, 4), Technical Jury, Operations  

---

## 1. Executive Summary & Problem Scope

SALESTORM is an enterprise flash-sale e-commerce platform designed to operate with absolute consistency, high availability, and extreme resilience during ultra-high concurrency events. 

The canonical flash-sale event defined in the hackathon brief is:
- **Available Product Stock:** Exactly **100 units** of a limited-edition flash-sale SKU (Product X).
- **Contention Window:** Exactly **10,000 customers** simultaneously clicking **"BUY NOW"** within a sub-second window ($t = 0$).
- **Business Imperative:** Zero overselling ($\le 100$ successful sales), zero negative inventory, zero phantom or duplicate reservations, deterministic last-unit contention, and seamless recovery from partial downstream outages (e.g., a 30-second Order Service crash).
- **Traffic Envelope:** Baseline operations at **10,000 requests/sec**, scaling gracefully to support a **50× peak burst of 500,000 requests/sec**.

This document outlines the formal functional requirements, measurable non-functional requirements (NFRs), explicit assumptions, and strict guarantees versus engineering targets that form the unassailable foundation for the entire SALESTORM system.

---

## 2. End-to-End Business Pipeline & Functional Requirements

The system must satisfy the 12-stage business pipeline defined in the hackathon brief:

```
Customer 
  → 1. Product Discovery 
  → 2. Cart 
  → 3. Inventory Check 
  → 4. Inventory Reservation 
  → 5. Checkout 
  → 6. Payment Initiation / Processing 
  → 7. Order Generation 
  → 8. Fulfilment 
  → 9. Shipment 
  → 10. Notification 
  → 11. Delivery Tracking
```

### Detailed Functional Requirements (FR)

| Req ID | Pipeline Stage | Functional Requirement Description | Owner / Service Boundary |
| :--- | :--- | :--- | :--- |
| **FR-01** | Product Discovery | The system must serve high-throughput, low-latency product catalog reads (title, specs, price, media, sale rules) without hitting transactional inventory databases. Cached data must be refreshed when catalogue changes occur. | `Product Service` |
| **FR-02** | Product Availability | The system must display near-real-time inventory indicators (e.g., "In Stock", "Few Left", "Sold Out"). During flash sales, discovery pages may show slightly stale availability (eventual consistency) without compromising reservation correctness. | `Product Service` + Cache |
| **FR-03** | Cart Management | Customers may add items to a persistent cart. Adding an item to the cart **does not** reserve inventory. The cart validates item eligibility, quantity limits (max 1 unit per customer during flash sales), and applies promotional deals/coupons. | `Cart Service` |
| **FR-04** | Buy Now / Fast-Track | The system must support an express "Buy Now" flow that bypasses standard multi-item cart accumulation, directly linking product selection with reservation and checkout orchestration. | `Checkout Service` |
| **FR-05** | Inventory Check | Prior to attempting a write-lock or reservation lease, the system performs an atomic check against available stock. If available stock is 0, the request is immediately rejected with a fast-fail `OUT_OF_STOCK` response. | `Inventory Service` |
| **FR-06** | Inventory Reservation | The system must atomically deduct exactly the requested quantity from available stock and place it into a `RESERVED` state. It must generate a cryptographically unique `reservation_id` tied to a tenant/user `idempotency_key`. | `Inventory Service` |
| **FR-07** | Reservation Expiry Window | Every reservation must carry a strict Time-To-Live lease (configured to **300 seconds / 5 minutes**). If payment is not completed before `expires_at`, the lease lapses automatically. | `Inventory Service` |
| **FR-08** | Reservation Release | Upon reservation expiry or explicit payment cancellation/failure, the reserved quantity must be safely, atomically, and idempotently returned to available inventory. | `Inventory Service` |
| **FR-09** | Checkout Orchestration | Coordinates the customer order context, billing/shipping address verification, applied discounts, tax calculation, and links the active `reservation_id` to the session. | `Checkout Service` |
| **FR-10** | Payment Initiation | The customer initiates payment using an external or tokenized payment gateway. The request requires a `payment_idempotency_key` ensuring that retries do not trigger duplicate authorizations. | `Payment Service` |
| **FR-11** | Payment Success Callback | On verified gateway authorization/settlement, the system updates transaction state to `PAID`, emits an asynchronous durable `PaymentSuccessfulEvent`, and triggers inventory confirmation (`SOLD`). | `Payment Service` |
| **FR-12** | Payment Failure Handling | If the payment gateway returns an error (e.g., insufficient funds, fraud alert), the system immediately transitions payment to `FAILED`, releases the associated inventory reservation, and notifies the client. | `Payment Service` + `Inventory Service` |
| **FR-13** | Payment Timeout Handling | If the gateway does not respond within the defined timeout window (3,000 ms), the system enters an ambiguous state resolution: it queries gateway status via an out-of-band reconciliation call before deciding whether to reverse or finalize. | `Payment Service` |
| **FR-14** | Order Generation | The Order Service consumes `PaymentSuccessfulEvent` and creates a permanent, immutable `Order` record with status `CONFIRMED`. It must be completely idempotent against duplicate event deliveries. | `Order Service` |
| **FR-15** | Order Lifecycle Management | The system manages valid state progressions: `CREATED` $\rightarrow$ `PAYMENT_PENDING` $\rightarrow$ `CONFIRMED` $\rightarrow$ `PROCESSING` $\rightarrow$ `SHIPPED` $\rightarrow$ `OUT_FOR_DELIVERY` $\rightarrow$ `DELIVERED` (or `CANCELLED` / `REFUNDED`). | `Order Service` |
| **FR-16** | Fulfilment Orchestration | Confirmed orders are batched and routed to the warehouse management/fulfilment system, triggering packaging, picking, and shipment allocation. | `Shipment Service` |
| **FR-17** | Shipment & Tracking | Generates waybills/tracking numbers via carrier integrations, logs transit checkpoints, and exposes delivery tracking APIs to the customer. | `Shipment Service` |
| **FR-18** | Customer Notification | Emits multi-channel alerts (SMS, Email, Push, WebSocket updates) for reservation creation, payment success/failure, order placement, and shipping milestones. Failures in notification must never roll back orders. | `Notification Service` |

---

## 3. Non-Functional Requirements (NFR)

The system enforces measurable, quantifiable engineering targets designed to withstand stress scenarios.

| Dimension | Metric / Requirement | Target Value | Measurement Protocol |
| :--- | :--- | :--- | :--- |
| **Throughput (Normal)** | Read & write operations across all business services | **10,000 req/sec** | Sustained load over 60 minutes across all endpoints |
| **Throughput (Flash Peak)** | Ingress traffic capacity during flash sale campaign | **500,000 req/sec** | Synthetic load generator (Locust/k6/Distributed load test) |
| **Throughput (Contention)** | Burst write contention on a single flash-sale SKU | **10,000 concurrent req** | Arriving in $< 1,000\text{ ms}$ at $t = 0$ |
| **Latency: Product Read** | p50 / p95 / p99 response time for catalog and price | **p50 < 10ms, p99 < 30ms** | Measured at API Gateway edge (Edge CDN / Redis read) |
| **Latency: Reservation** | p50 / p95 / p99 response time for Buy Now reservation | **p50 < 45ms, p99 < 150ms** | End-to-end client round-trip to reservation confirmation |
| **Latency: Order Confirm** | Asynchronous end-to-end order processing latency | **p99 < 2,000ms** | From payment confirmation event to confirmed order in DB |
| **Availability (Read Tier)** | Product catalogue, cart view, and static assets | **99.99% (Four Nines)** | Max allowable downtime: 4.38 mins/month |
| **Availability (Write Tier)**| Checkout, reservation, and payment processing | **99.95%** | Max allowable downtime: 21.92 mins/month |
| **Data Consistency** | Inventory balance & reservation correctness | **Strong Consistency** | Linearizable/atomic invariant: $\sum \text{Allocated} \le \text{Total}$ |
| **Order Consistency** | Downstream order creation, notifications, shipments | **Eventual Consistency** | Guaranteed convergence via durable transactional outbox |
| **Security: Auth & Authz** | Authentication, token exchange, authorization | **OAuth2 / JWT** | Expiring stateless tokens with cryptographically signed claims |
| **Security: API Shielding** | Rate limiting, bot mitigation, DDoS defense | **WAF + Token Bucket** | 100 req/min per IP/User for standard endpoints; 5 req/min for checkout |
| **Security: Data at Rest** | Database volumes, transaction logs, and caches | **AES-256 GCM** | Encrypted tablespaces, connection SSL/TLS 1.3 enforced |
| **Security: PCI-DSS** | Credit card numbers, CVVs, sensitive payment data | **Zero In-Memory Storage**| Hosted fields / Gateway tokenization; no PAN enters internal VPC |
| **Reliability: RTO** | Recovery Time Objective for primary service crash | **$< 60\text{ seconds}$** | Automated pod rescheduling and container health-probe restart |
| **Reliability: RPO** | Recovery Point Objective for transactional data | **$0\text{ seconds}$ (RPO = 0)** | Multi-AZ synchronous replication / WAL flushing |
| **Fault Isolation** | Downstream failure blast radius (e.g. Order outage) | **100% Isolated** | Order service down for 30s has 0% impact on payment success rate |

---

## 4. Clear Categorization of System Directives

To maintain engineering integrity, all architectural assertions are classified into four unambiguous categories:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SYSTEM DIRECTIVE TAXONOMY                             │
├───────────────────────┬─────────────────────────────────────────────────────────┤
│ 1. Official Req       │ Explicit mandates from the Hackathon Brief Revised PDF. │
├───────────────────────┼─────────────────────────────────────────────────────────┤
│ 2. Team Assumption    │ Engineering assumptions required to close open variables│
├───────────────────────┼─────────────────────────────────────────────────────────┤
│ 3. Design Target      │ Quantifiable performance goals (p99 latency, RPS).      │
├───────────────────────┼─────────────────────────────────────────────────────────┤
│ 4. Design Decision    │ Concrete architectural choices justified by trade-offs. │
└───────────────────────┴─────────────────────────────────────────────────────────┘
```

### A. Official Requirements from Brief
1. Stock = 100 units; Concurrent purchase requests = 10,000 customers.
2. Available stock cannot be oversold ($100\text{ units} \implies \le 100\text{ successful sales}$).
3. Available quantity must never become negative ($\text{available\_quantity} \ge 0$).
4. Two concurrent requests for the final unit must produce a deterministic outcome: 1 succeeds, 1 fails.
5. Temporary reservations must be provided with automatic expiry and stock release.
6. System must handle practical test conditions: 95% payment success, 5% payment failure, 2% duplicate requests, and Order Service down for 30 seconds.
7. Architecture must scale from 10,000 req/sec normal traffic to 500,000 req/sec flash traffic.
8. At least two concurrency strategies must be compared (Optimistic vs. Pessimistic).

### B. Team Architectural Assumptions
1. **User Identity:** All 10,000 concurrent customers participating in the flash sale are authenticated prior to sale onset ($t < 0$) via JWT bearer tokens containing a verified `user_id`. Unauthenticated users are rejected at the API Gateway.
2. **Item Limit:** To democratize access and prevent bot hoarding, each unique customer account is restricted to a maximum purchase limit of **1 unit** of the flash-sale SKU.
3. **Reservation Lease Duration:** The reservation Time-To-Live (TTL) is set to **300 seconds (5 minutes)**. This provides adequate time for 3D-Secure payment challenges while releasing uncommitted stock promptly.
4. **Payment Gateway Latency & Throughput:** The third-party payment gateway provides an average response time of $400\text{ ms}$, but caps merchant API concurrency at $2,000\text{ TPS}$. The architecture must smooth and throttle gateway calls accordingly.
5. **Clock Synchronization:** Cluster server nodes utilize Network Time Protocol (NTP) with an assumed clock skew of $\Delta t < 20\text{ ms}$. Expiry mechanisms rely on monotonic counters and absolute database timestamps.
6. **Network Reliability:** Network partitions between services are assumed to occur periodically (CAP theorem theorem holds). Services must rely on durable queues rather than persistent point-to-point RPCs for post-reservation flows.

### C. Design Targets
1. **Flash Sale Reservation Burst Processing:** Complete processing and resolution of all 10,000 concurrent Buy Now requests within **1,500 milliseconds** of sale opening.
2. **Fast-Fail Rejection Speed:** For the 9,900 customers who cannot secure inventory, the API Gateway/Reservation Service returns an HTTP `409 Conflict` (or `429 Too Many Requests` / `200 Sold Out`) within **$< 50\text{ ms}$**.
3. **Queue Ingestion Throughput:** The message broker must absorb bursts of up to $50,000\text{ msgs/sec}$ with zero backpressure on the payment-to-order pipeline.
4. **Order Service Recovery Reconciliation:** Upon recovery from a 30-second crash, the Order Service processes the accrued queue backlog within **$< 15\text{ seconds}$** without dropping a single order.

### D. Design Decisions
1. **Decoupled Reservation & Order State:** We separate the synchronous Reservation Engine (in-memory atomic decrement via Redis Lua + RDBMS write-through) from asynchronous Order Generation (Kafka/Transactional Outbox).
2. **Two-Tier Concurrency Architecture:** We select an In-Memory Atomic Reservation Engine fronting an ACID-compliant Relational Store (PostgreSQL) rather than raw row-locking inside the database.
3. **Durable Asynchronous Messaging for Downstream Pipelines:** Payment-to-Order, Order-to-Fulfilment, and Order-to-Notification communicate strictly via an append-only message log with at-least-once delivery semantics.

---

## 5. Strict Guarantees vs. Engineering Targets

To prevent architectural ambiguity during jury defense, the table below establishes the line between non-negotiable correctness guarantees and empirical performance targets:

| Dimension | Strict Guarantee (Zero Tolerance) | Engineering Target (Best Effort / SLA) |
| :--- | :--- | :--- |
| **Inventory Integrity** | **$\text{Sold} + \text{Reserved} \le \text{Total Inventory}$**.<br>Overselling is strictly prohibited under all race conditions. | Reservation confirmation round-trip $< 150\text{ ms}$ at p99. |
| **Negative Stock** | **$\text{available\_quantity} \ge 0$**.<br>Database constraint rejects any transaction driving stock $< 0$. | Immediate client feedback within 50ms when stock drops to 0. |
| **Deterministic Tie-Breaking** | For the final remaining unit ($N = 1$), exactly **one request commits** and all concurrent competitors receive failure. | Sub-millisecond decision time inside the atomic serialization unit. |
| **Idempotency** | Repeating a request with identical `idempotency_key` yields the identical business result and **never creates a second reservation or charge**. | Cache lookup for idempotency key takes $< 5\text{ ms}$. |
| **Payment Integrity** | A customer is **never double-charged** for a single reservation, regardless of network retries. | Payment authorization round-trip under $1,200\text{ ms}$. |
| **Order Fulfilment** | Every successful payment **must eventually materialize as a confirmed order** (100% delivery guarantee). | Order creation completes within $2,000\text{ ms}$ of payment webhook. |
| **Availability vs. Consistency** | Consistency is favored over availability on the reservation write path (CP). Reads are highly available (AP). | 99.99% read uptime, 99.95% write uptime. |

---

## 6. Architectural Contracts for Downstream Team Members

To guarantee independent execution across the 4-member engineering team without boundary shifts, Member 1 specifies the following structural contracts:

### A. Contract for Member 2 (LLD, SOLID, Design Patterns)
- **Domain Entities:** Must implement rich domain models for `InventoryItem`, `ReservationLease`, `PaymentTransaction`, and `OrderAggregate`.
- **State Machine Pattern:** Implement explicit State Pattern for `ReservationState` (`AVAILABLE`, `RESERVED`, `PAYMENT_PENDING`, `CONFIRMED`, `SOLD`, `RELEASED`) and `OrderState` (`CREATED`, `PAYMENT_PENDING`, `CONFIRMED`, `PROCESSING`, `SHIPPED`, `DELIVERED`, `CANCELLED`).
- **Strategy Pattern:** Decouple concurrency engines (`OptimisticLockStrategy`, `PessimisticLockStrategy`, `RedisAtomicLuaStrategy`) and Payment Gateway Adapters (`StripeAdapter`, `PayPalAdapter`, `MockGatewayAdapter`).
- **Command & Query Separation:** Command handlers (`ReserveInventoryCommand`, `AuthorizePaymentCommand`, `CreateOrderCommand`) must separate side-effects from query models.

### B. Contract for Member 3 (Database, API, Events, Reliability)
- **Database Schema Constraints:**
  - `inventory` table must feature `CHECK (available_quantity >= 0)`, `CHECK (reserved_quantity >= 0)`, and an integer `version` column.
  - Unique composite index on `inventory_reservation (product_id, idempotency_key)` to enforce database-level duplicate prevention.
  - Foreign key constraints linking `order_item` to `product` and `order` to `customer`.
- **API Idempotency Specification:**
  - Every write endpoint (`POST /api/v1/reservations`, `POST /api/v1/payments/charge`) must accept and validate an `Idempotency-Key: <UUIDv4>` header.
- **Transactional Outbox Table:**
  - Schema must include `outbox_events (event_id, aggregate_type, aggregate_id, payload, status, created_at, processed_at)`.
- **Event Contracts:**
  - Standard JSON schemas for `InventoryReservedEvent`, `InventoryReleasedEvent`, `PaymentSuccessfulEvent`, and `OrderCreatedEvent`.

### C. Contract for Member 4 (AWS Cloud & Deployment Mapping)
- **Logical Ingress:** Edge CDN $\rightarrow$ WAF $\rightarrow$ Application Load Balancer $\rightarrow$ Containerized Gateway.
- **Compute Sizing:** Stateless microservices running in auto-scaling container clusters (EKS/ECS) decoupled from stateful datastores.
- **Durable Broker Requirement:** High-throughput, distributed partitioned commit log (Kafka / AWS MSK / Amazon Kinesis) with persistent replication factor $\ge 3$.
- **Distributed Cache Requirement:** In-memory cluster supporting atomic multi-key Lua scripts and sub-millisecond key-value lookups (Redis Cluster / AWS ElastiCache).
- **Relational Storage Requirement:** Multi-AZ ACID RDBMS with read replicas (PostgreSQL / AWS Aurora Serverless v2).

---

*End of 01_Requirements_and_Assumptions.md — Authoritative Requirements Foundation.*
