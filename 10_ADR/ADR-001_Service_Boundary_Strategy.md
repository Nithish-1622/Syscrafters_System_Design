# ADR-001: Domain-Driven Microservice Boundary Strategy

**Status:** Approved  
**Date:** 2026-10-05  
**Author:** Member 1 (System Architect)  
**Deciders:** Core Engineering Team  

---

## 1. Context & Problem Statement
SALESTORM is a high-scale flash-sale e-commerce platform that experiences extreme traffic bursts (10,000 to 500,000 req/sec) concentrated on limited-stock inventory. 
A naive monolithic architecture couples catalog browsing, cart calculations, inventory reservation, and payment processing into a single deployable unit and shared database. During flash sales, read-heavy catalog traffic and heavy write contention on inventory would exhaust database connections and thread pools, causing the entire platform (including checkout and payment) to crash. 

We need a clear architectural boundary strategy that isolates contention hotspots, enables independent horizontal scaling, minimizes blast radius during failures, and provides clear ownership across our 4-member engineering team.

---

## 2. Options Considered

### Option 1: Monolithic Architecture with Shared Database
- **Description:** Single codebase with modular packages, deploying to a large compute cluster backed by a centralized relational database.
- **Pros:** Simpler initial development; immediate ACID transactions across inventory, order, and payment; zero network latency between components.
- **Cons:** Shared database creates a single point of failure; high catalog browsing load degrades checkout performance; lock contention on inventory cascades across all operations; impossible to scale the inventory contention hotspot independently.

### Option 2: Fine-Grained Nano-services (30+ Microservices)
- **Description:** Decomposing every business entity (e.g., Price Service, Tax Service, Coupon Service, Address Service, Stock Service) into independent microservices.
- **Pros:** Maximum granular scaling.
- **Cons:** Extreme network hop overhead; distributed transaction nightmare; high latency on the critical checkout path; overwhelming operational complexity for a 4-member team.

### Option 3: Domain-Driven Bounded Context Microservices (Selected)
- **Description:** Partitioning the system into 8 cohesive business bounded contexts: Product Service, Cart Service, Inventory Service, Checkout Service, Payment Service, Order Service, Shipment Service, and Notification Service. Each service encapsulates its own state and database.
- **Pros:** Isolates the high-contention inventory hotspot from browsing; allows asynchronous decoupling for downstream order processing; confines failure blast radius; matches team domain ownership.
- **Cons:** Requires eventual consistency patterns (Transactional Outbox, Saga, Idempotent Consumers) across service boundaries; increases operational deployment overhead.

---

## 3. Decision
We adopt **Option 3: Domain-Driven Bounded Context Microservices**. 

Specifically:
- **Product Service:** Owns product metadata and read-heavy catalog queries.
- **Cart Service:** Owns transient shopping baskets without holding inventory locks.
- **Inventory Service:** Owns the scarce inventory balances, atomic reservation engine, and lease lifecycle.
- **Checkout Service:** Acts as the checkout orchestration facade.
- **Payment Service:** Encapsulates third-party gateway integrations and guarantees payment idempotency.
- **Order Service:** Owns the canonical, immutable order aggregate and order lifecycle.
- **Shipment Service:** Manages warehouse dispatch, carrier integrations, and tracking.
- **Notification Service:** Handles asynchronous multi-channel customer communications.

---

## 4. Architectural Consequences & Trade-offs

### Positive Consequences:
- **Hotspot Isolation:** The extreme 10,000-to-100 contention is strictly confined to the `Inventory Service` and its in-memory arbiter, protecting catalog browsing and payment processing from database thread lockups.
- **Failure Blast Radius Reduction:** An outage in the `Order Service` or `Notification Service` does not stop payments from succeeding or block customers from securing flash-sale stock.
- **Targeted Scalability:** The `Product Service` can scale 100× on read replicas, while the `Inventory Service` scales via in-memory Redis cluster sharding.

### Negative Consequences / Trade-offs:
- **No Global ACID Transactions:** We cannot perform a single SQL transaction across Inventory, Payment, and Orders. We must accept and implement asynchronous messaging, the Transactional Outbox pattern, and distributed saga compensation.
- **Data Duplication:** Basic customer and product attributes are denormalized into order snapshots to maintain immutable historical records.
