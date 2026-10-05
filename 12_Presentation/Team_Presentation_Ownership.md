# SALESTORM — Team Presentation Ownership & Defense Strategy Guide

**Hackathon:** SALESTORM | SYSCRAFTERS 2026 Design-First AI-Assisted System Design Hackathon  
**Target Pitch Duration:** 5 Minutes (Presentation) + 5–10 Minutes (Jury Q&A Defense)  
**Team Composition:** 4 Core Members  

---

## 1. Executive Master Allocation Matrix

| Member | Role Title | Folders Owned | Primary Presentation Phase | Time Budget | Key Visual Artifacts |
|---|---|---|---|---|---|
| **Member 1** | **System Architect + Concurrency & Scalability Lead** | `01_Requirements/`<br/>`02_HLD/`<br/>`08_Scalability_Reliability/`<br/>`10_ADR/`<br/>`12_Presentation/` | **Phase 1: Problem, HLD & Concurrency Engine** (Opening) | 1m 45s | System Context, HLD, Redis Lua Sequence, 50x Surge Scaling Diagram |
| **Member 2** | **Software Architect + LLD, SOLID & Patterns Lead** | `03_LLD/`<br/>`06_SOLID/`<br/>`07_Design_Patterns/` | **Phase 2: LLD, Object Models & Patterns** | 1m 00s | Domain Class Diagrams, State Pattern Diagram, Strategy Pattern Interface |
| **Member 3** | **Database, Backend Implementation & Testing Lead** | `04_Database/`<br/>`05_API/`<br/>`11_AI_Assisted_Validation/`<br/>Root Test Suite | **Phase 3: DB Guarantees, Outbox/Inbox & 30s Crash Recovery** | 1m 00s | ACID Schema Check Constraints, Outbox Sequence, 30s Crash Recovery Demo |
| **Member 4** | **Security, Observability, DevOps & Cloud Lead** | `09_Security_Observability/`<br/>Docker & AWS Guides | **Phase 4: Security, Observability & AWS Docker Hosting** (Closing) | 1m 15s | Rate Limiting Pipeline, Full AWS Docker Architecture Diagram |

---

## 2. Member 1: System Architect & Concurrency Lead

### Folders Owned
- `01_Requirements/` — Business goals, strict invariants ($S_{sold} \le 100$, $S_{avail} \ge 0$), non-functional requirements (NFRs).
- `02_HLD/` — System Context (C4 Level 1), High-Level Architecture, Microservice Containers (C4 Level 2), Request flows.
- `08_Scalability_Reliability/` — 500,000 RPS surge analysis, virtual stock sharding, single-SKU bottleneck mitigation.
- `10_ADR/` — Architectural Decision Records (ADR 001–005: Redis Lua vs SQL Locking, Outbox vs 2PC, FastAPI vs Java).
- `12_Presentation/` — Slide decks, pitch structure, jury defense guides.

### What Member 1 Explains
1. **The Core Dilemma:**
   - How 10,000 concurrent customers fight for exactly 100 available units at $t=0$ in under 1 second.
   - Why traditional approaches fail:
     - *Pessimistic DB Locks (`SELECT FOR UPDATE`)* cause 10,000 connections to queue on a single row, exhausting database connection pools and crashing the API Gateway with HTTP 504 timeouts.
     - *Optimistic Locking (`OCC`)* causes 9,999 transactions to fail validation simultaneously, creating a catastrophic retry storm that spikes CPU to 100%.
2. **The High-Level Architecture (HLD):**
   - The separation between **Synchronous Scarcity Boundary** (must respond in <150ms whether the user secured a reservation) and **Asynchronous Post-Payment Pipeline** (decoupled via event streaming).
   - Microservice boundaries: API Gateway, Product Service, Checkout Service, Inventory Service, Payment Service, Order Service.
3. **The Concurrency Engine (Redis Lua Script):**
   - Single-threaded atomic serialization in Redis.
   - Wire-speed sequential execution: Requests 1 to 100 decrement stock from 100 to 0 and get a 300-second lease key.
   - Requests 101 to 10,000 immediately receive return code `0` and fast-fail with HTTP 409 Conflict ("Sold Out") in <50ms.
   - For unit #100, deterministic tie-breaking is absolute: the first network packet in the Redis command buffer gets the unit; the second is rejected.
   - Database writes are strictly capped at 100.
4. **Surge Scalability (500,000 RPS):**
   - Ingress edge shedding via CloudFront/WAF.
   - Virtual counter sharding across 10 Redis shards for multi-SKU scenarios.
   - Human checkout latency smoothing: payments are spread naturally over the 300-second lease window.

### Member 1 Delivery Script (Spoken in 105 seconds)
> *"Judges, in high-scale flash sales, systems don't fail from gradual load—they fail from instant contention. At 12:00:00 PM, 10,000 customers hit 'Buy Now' for only 100 units. If you hit a relational database with 10,000 concurrent locks, your connection pool exhausts and your gateway crashes. If you use optimistic locking, 9,999 transactions abort and retry, incinerating your CPU.
> 
> In SALESTORM, we enforce two mathematical invariants: sold items can never exceed 100, and available stock can never be negative.
> 
> We solved this by splitting the architecture into a Synchronous Scarcity Tier and an Asynchronous Fulfillment Tier. When 10,000 requests hit our API Gateway, they route to the Inventory Service backed by a single-threaded Redis Lua engine. In under 200 milliseconds, Redis serializes all 10,000 operations at wire speed. The first 100 requests decrement the stock counter and lock a 300-second reservation lease. The remaining 9,900 requests fail instantly with HTTP 409 Sold Out in under 50ms.
> 
> Database writes are strictly capped to the 100 winning users. Zero database locks, zero overselling, and absolute deterministic tie-breaking on the 100th unit. Now, Member 2 will explain our object design and pattern implementation."*

---

## 3. Member 2: Software Architect + LLD, SOLID & Patterns Lead

### Folders Owned
- `03_LLD/` — Class diagrams, sequence diagrams, microservice component specifications, domain models.
- `06_SOLID/` — Explicit mapping of Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, and Dependency Inversion.
- `07_Design_Patterns/` — Gang-of-Four pattern implementations (Strategy, State, Factory, Outbox/Inbox, Adapter).

### What Member 2 Explains
1. **Object-Oriented Domain Modeling (`03_LLD/`):**
   - Clean domain aggregates: `InventoryItem`, `StockReservation`, `PaymentTransaction`, `OrderAggregate`.
   - Clear encapsulation: Domain models contain business logic and validation invariants, never raw database access.
2. **Gang-of-Four Design Patterns (`07_Design_Patterns/`):**
   - **State Pattern:** Governs the Reservation and Order lifecycles.
     - Reservation states: `PENDING` $\rightarrow$ `CONFIRMED` or `EXPIRED` $\rightarrow$ `RELEASED`.
     - Order states: `CREATED` $\rightarrow$ `PAID` $\rightarrow$ `FULFILLED` or `CANCELLED`.
     - Invalid state transitions (e.g., trying to pay for an `EXPIRED` reservation) are blocked at the type/class level.
   - **Strategy Pattern:** Used for payment processor adapters (`StripeAdapter`, `AdyenAdapter`, `MockPaymentGateway`) and inventory engines (`RedisLuaEngine` vs `PostgresEngine`). New gateways plug in without altering a single line of checkout code.
   - **Factory & Builder Patterns:** Encapsulate complex aggregate creation and event payload serialization.
3. **SOLID Principles Adherence (`06_SOLID/`):**
   - **S (Single Responsibility):** Controllers only handle HTTP; Services only execute business workflows; Repositories only persist.
   - **O (Open/Closed):** Payment and notification strategies are open for extension via interfaces, closed for modification.
   - **L (Liskov Substitution):** Any payment gateway adapter conforms strictly to `PaymentGatewayInterface` and can be substituted transparently.
   - **I (Interface Segregation):** Small, cohesive interfaces (e.g., `StockReservationReader`, `StockReservationWriter`) instead of fat interfaces.
   - **D (Dependency Inversion):** Services depend on abstract repositories and event producers injected via dependency injection, allowing in-memory mocks during unit testing.

### Member 2 Delivery Script (Spoken in 60 seconds)
> *"Building on Member 1's architecture, our Low-Level Design translates these system boundaries into clean, maintainable, object-oriented code adhering strictly to SOLID principles.
> 
> We implemented the State Pattern to govern the lifecycle of both reservations and orders. An order cannot transition to 'PAID' without an active lease, and expired reservations automatically transition to 'RELEASED', making race conditions impossible at the domain model level.
> 
> We applied the Strategy Pattern to decouple our checkout domain from payment providers. Our Payment Service talks to an abstract PaymentGatewayInterface. Whether we route transactions to Stripe, Adyen, or a regional gateway, the core checkout orchestrator remains completely untouched.
> 
> Through Dependency Inversion, every controller and service depends on abstractions rather than concrete database connections. This allowed our team to unit test every edge case in complete isolation. Now, Member 3 will walk through our database integrity and crash recovery."*

---

## 4. Member 3: Database, Backend Implementation & Testing Lead

### Folders Owned
- `04_Database/` — PostgreSQL relational schemas, migration scripts, indexes, ACID transaction isolation levels, check constraints.
- `05_API/` — REST API contracts, FastAPI routers, request/response Pydantic models, idempotency middleware.
- `11_AI_Assisted_Validation/` — Test suites, simulation runs, e2e validation scripts (`test_e2e_resilience.py`).
- Root level: `Dockerfile`, `docker-compose.yml`, `requirements.txt`.

### What Member 3 Explains
1. **Database Schema & ACID Integrity (`04_Database/`):**
   - PostgreSQL schema with engine-enforced guarantees:
     - `CHECK (available_quantity >= 0)` guarantees negative inventory is physically rejected by the storage engine.
     - `UNIQUE (user_id, item_id, active_status)` prevents duplicate reservations.
     - Composite indexes on `(sku, status)` and `(idempotency_key)` guarantee sub-5ms indexed lookups.
2. **Transactional Outbox & Inbox Patterns (`04_Database/`, `05_API/`):**
   - Dual-write elimination: When a payment succeeds, the payment record and a `PaymentSuccessfulEvent` are written to `payment_outbox` in the **exact same local ACID database transaction** (`BEGIN; UPDATE payment; INSERT INTO outbox; COMMIT;`).
   - A dedicated Outbox Relay daemon polls the outbox and publishes events to the message broker.
   - Order Service consumes via an **Idempotent Inbox Guard** (`processed_inbox`), discarding duplicate message deliveries.
3. **The 30-Second Crash Recovery Test Case (`11_AI_Assisted_Validation/`):**
   - The hackathon's core resilience challenge: *Payment succeeds, but Order Service crashes for 30 seconds.*
   - Anti-pattern: Triggering an immediate refund if Order Service is unreachable. (Customer is billed, gets bank alert, then loses order).
   - SALESTORM solution: Payment is committed and safely logged in the outbox. The event waits in the durable message queue while Order Service recovers.
   - At second 30, the restarted Order Service polls its uncommitted offset, reads the event, creates the order idempotently, and updates status to `CONFIRMED`.
   - **Zero lost orders, zero unnecessary refunds, 100% state convergence.**
4. **Live Validation Results:**
   - 5/5 passing automated end-to-end integration tests in `11_AI_Assisted_Validation/`.
   - Simulation output confirming 10,000 contenders, exactly 100 units reserved, 0 oversold.

### Member 3 Delivery Script (Spoken in 60 seconds)
> *"On the database and implementation side, our primary directive was zero data loss and bulletproof ACID guarantees.
> 
> First, we enforced mathematical safety directly into PostgreSQL with table-level check constraints: available_quantity can never be less than zero. Even if an application bug bypassed validation, the database engine itself rejects negative stock.
> 
> Second, we solved the distributed transaction dilemma using the Transactional Outbox pattern. We never perform dual writes to a database and a message queue. When Payment Service charges a card, it writes the payment record and the PaymentSuccessfulEvent in a single ACID transaction.
> 
> This directly solves the hackathon's 30-second crash scenario: when our Order Service was intentionally killed for 30 seconds during our simulation tests, zero messages were lost. The event remained safely queued. The moment Order Service rebooted, its idempotent inbox consumer ingested the event, materialized the order, and confirmed it with 100% data integrity.
> 
> Our automated test suite passes 5 out of 5 end-to-end integration tests with zero failures. Now, Member 4 will present our security and AWS cloud hosting."*

---

## 5. Member 4: Security, Observability, DevOps & Cloud Lead

### Folders Owned
- `09_Security_Observability/` — Edge security, rate limiting, authentication/authorization, PCI-DSS compliance, distributed tracing, structured logging, Prometheus metrics, CloudWatch alarms.
- `09_Security_Observability/AWS_Deployment_Guide_Dev4.md` — 11-phase comprehensive AWS deployment guide.
- `09_Security_Observability/AWS_Docker_Architecture_Diagram.md` — Canonical AWS hosting & Docker container architecture diagram.

### What Member 4 Explains
1. **Edge & API Security (`09_Security_Observability/`):**
   - **Token Bucket Rate Limiting:** Enforced at API Gateway (e.g., 20 req/s per IP with burst of 50) to stop bot scripts from monopolizing the sale.
   - **Zero-Trust & Authn/Authz:** JWT validation with RS256 asymmetric signatures; fine-grained claims verification before requests touch internal microservices.
   - **PCI-DSS Compliance:** Raw credit card PANs never enter SALESTORM networks; frontend communicates directly with Stripe/Adyen iframe tokenization. We only handle opaque payment tokens.
2. **Full-Stack Observability:**
   - **Distributed Tracing (OpenTelemetry):** End-to-end trace ID propagation (`traceparent` header) across API Gateway, Checkout, Inventory, and Order Services.
   - **Structured JSON Logging:** Every log contains `trace_id`, `span_id`, `service_name`, and timestamp for millisecond correlation.
   - **Prometheus & CloudWatch Metrics:** Real-time dashboards monitoring p99 latency, Redis memory usage, outbox queue lag, and HTTP 5xx error spikes with automated SNS alerting.
3. **AWS Cloud Docker Hosting Blueprint:**
   - **VPC & Network Isolation:** Dedicated VPC (10.0.0.0/16) across 2 Availability Zones (`ap-south-1a`, `ap-south-1b`) in AWS Mumbai.
   - **Public Subnet:** Internet Gateway, NAT Gateways, and Application Load Balancer (ALB) terminating HTTPS/TLS 1.3 on Port 443.
   - **Private App Subnet:** AWS ECS Fargate running our Docker containers (`salestorm-api`, `outbox-relay-worker`). Zero public IPs on microservices.
   - **Isolated Data Subnet:** Amazon RDS PostgreSQL 16 (Multi-AZ) and Amazon ElastiCache Redis 7 (Primary + Read Replica).
   - **DevOps Pipeline:** Amazon ECR hosting tagged Docker images; AWS Secrets Manager injecting database and cache credentials at container boot; ECS Task Execution IAM roles enforcing least-privilege access.

### Member 4 Delivery Script (Spoken in 75 seconds)
> *"A rock-solid architecture is only as good as its production hardening. I was responsible for security, observability, and our AWS Docker infrastructure.
> 
> On the security front, we implemented a Zero-Trust ingress. At the edge, Token Bucket rate limiting defends against automated botnets. All traffic terminates TLS 1.3 at our Application Load Balancer. Internally, services enforce JWT validation, while PCI-DSS compliance is achieved by handling only opaque payment tokens—raw credit card data never touches our application servers.
> 
> For observability, we instrumented OpenTelemetry distributed tracing with correlation IDs injected into every structured JSON log, enabling us to pinpoint any sub-millisecond bottleneck across the checkout pipeline.
> 
> Finally, our deployment blueprint runs on AWS in the Mumbai region across two Availability Zones. Our containerized microservices run as Docker tasks on AWS ECS Fargate in private subnets, completely shielded from direct internet access. They connect to Amazon RDS PostgreSQL and an Amazon ElastiCache Redis cluster in isolated database subnets.
> 
> Credentials are automatically rotated via AWS Secrets Manager, and container images are pulled securely from Amazon ECR. The entire setup is automated, observable, and ready for production deployment. Thank you, and our team is ready for your questions!"*

---

## 6. Complete 5-Minute Presentation Timeline

```
[0:00] ─── Member 1 ─── The Flash-Sale Problem & Concurrency Math (30s)
[0:30] ─── Member 1 ─── High-Level System Architecture & Scarcity Boundary (35s)
[1:05] ─── Member 1 ─── Redis Lua Concurrency Engine & 500k RPS Scaling (40s)
[1:45] ─── Member 2 ─── Low-Level Design & Object Aggregates (25s)
[2:10] ─── Member 2 ─── State & Strategy Design Patterns + SOLID (35s)
[2:45] ─── Member 3 ─── Database Schemas & ACID Check Constraints (25s)
[3:10] ─── Member 3 ─── Outbox/Inbox Decoupling & 30s Crash Recovery (35s)
[3:45] ─── Member 4 ─── Edge Rate Limiting, Auth & Observability (35s)
[4:20] ─── Member 4 ─── AWS Docker Infrastructure & ECS Topology (40s)
[5:00] ─── ALL ─────── Q&A Defense Begins
```

---

## 7. Jury Q&A Defense Strategy: Who Answers What

| Jury Question | Designated Respondent | Key Technical Defense Talking Points |
|---|---|---|
| *"What happens if two users click Buy Now for the 100th unit at the exact same millisecond?"* | **Member 1** | "Redis single-threaded event loop processes commands sequentially. The operating system TCP buffer serializes the packets. Whichever packet arrives first executes the Lua script, decrements stock from 1 to 0, and gets the unit. The second packet immediately evaluates `stock <= 0` and returns `0` (Sold Out). Zero race conditions." |
| *"Why didn't you use distributed 2-Phase Commit (2PC) between Payment and Order services?"* | **Member 1 / Member 3** | "2PC introduces blocking coordinator locks and severe latency degradation under flash-sale load. If the coordinator or any participant hangs, transactions freeze. We chose asynchronous eventual consistency via the Transactional Outbox pattern, which guarantees at-least-once delivery with sub-second convergence and zero blocking locks." |
| *"How do you prevent a user from paying after their 300-second reservation lease has expired?"* | **Member 2** | "Our State Pattern enforces lease validity. Payment Service verifies that the reservation status is still `ACTIVE` and that `expires_at > now()`. If the lease expired, Payment Service rejects the charge or automatically issues a reversal webhook, returning the item to stock safely." |
| *"How do you prevent duplicate order creation if Kafka sends the same payment event twice?"* | **Member 3** | "Order Service implements an Idempotent Inbox Guard using a PostgreSQL `processed_inbox` table. Before processing, it attempts to insert the event's UUID. If the key already exists, the unique constraint violates, the duplicate is cleanly acknowledged and ignored, preventing duplicate orders." |
| *"Why did you choose ECS Fargate over Kubernetes (EKS) for Docker hosting?"* | **Member 4** | "For a flash-sale microservice deployment, ECS Fargate provides serverless container execution without the operational overhead of managing Kubernetes control planes or node pools. It scales containers in seconds, integrates natively with AWS ALB, IAM Task Roles, and CloudWatch, optimizing our hackathon delivery and operational reliability." |
| *"How do you protect database credentials and API secrets in Docker containers?"* | **Member 4** | "Zero credentials are baked into Docker images or environment files. ECS Task Definitions retrieve secrets directly from AWS Secrets Manager at container launch using IAM Task Roles with least-privilege policies. Secrets exist only in ephemeral container memory." |
