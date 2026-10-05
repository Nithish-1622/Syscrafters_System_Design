# SALESTORM — Complete System Implementation Map & Architecture-to-Code Blueprint

**Document Version:** 1.0.0  
**Status:** Approved Implementation Baseline  
**Author:** Member 1 (System Architect) in collaboration with Member 2, Member 3 & Member 4  
**Scope:** Translates the collective markdown specifications into an executable, containerized production-ready system.

---

## 1. Traceability Matrix: Architecture Specs to Executable Code

The following matrix formally maps every architecture and design deliverable into its executable code artifacts:

```
┌───────────────────────────────────────┬───────────────────────────────────────────┬────────────────────────────────────────┐
│ Design / Specification Artifact       │ Target Executable Implementation          │ Physical File Location                 │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 01_Requirements/                      │ Request validation, lease TTL (300s),     │ 05_API/src/config.py                   │
│   01_Requirements_and_Assumptions.md  │ invariants, NFR thresholds                │ 05_API/src/models/schemas.py           │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 02_HLD/                               │ High-level data flow, sync scarcity vs    │ 05_API/src/main.py                     │
│   01_High_Level_System_Architecture.md│ async event pipeline orchestration        │ 05_API/src/services/checkout.py        │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 03_LLD/module_design/                 │ InventoryItem aggregate, atomic Lua       │ 05_API/src/services/inventory.py       │
│   inventory_lld.md                    │ reserve script, 300s lease management     │ 05_API/src/services/lua_scripts.py     │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 03_LLD/module_design/                 │ PaymentTransaction, Gateway Strategy,     │ 05_API/src/services/payment.py         │
│   payment_lld.md                      │ idempotent charge, failure release        │ 05_API/src/adapters/payment_gateway.py │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 03_LLD/module_design/                 │ OrderAggregate, Outbox consumer,          │ 05_API/src/services/order.py           │
│   order_lld.md                        │ idempotent Inbox pattern deduplication    │ 05_API/src/events/consumer.py          │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 04_Database/                          │ PostgreSQL DDL, check constraints,        │ 04_Database/schema.sql                 │
│   schema.sql, transactions.md         │ SQLAlchemy ORM models, migration seed     │ 04_Database/seed.py                    │
│                                       │                                           │ 05_API/src/models/db_models.py         │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 05_API/                               │ FastAPI REST routes, schemas, headers     │ 05_API/src/routes/                     │
│   openapi.yaml, api_specification.md  │ (`Idempotency-Key`), RFC 7807 exceptions  │ 05_API/src/middleware/idempotency.py   │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 05_API/events.md                      │ CloudEvents 1.0 payloads, event publisher,│ 05_API/src/events/event_bus.py         │
│                                       │ durable stream / broker integration       │ 05_API/src/events/outbox_relay.py      │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 06_SOLID/ & 07_Design_Patterns/       │ Strategy (Gateway), State (Lifecycle),    │ 05_API/src/adapters/                   │
│                                       │ Repository (Postgres), Facade (Checkout)  │ 05_API/src/repositories/               │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 08_Scalability_Reliability/           │ Circuit breaker, retry with full jitter,  │ 05_API/src/middleware/resilience.py    │
│   02_Reliability_and_Failure_Handling │ Dead Letter Queue (DLQ), reconciliation   │ 05_API/src/services/reconciliation.py  │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ Containerization & Multi-Service      │ PostgreSQL 16 + Redis 7 + API Service     │ docker-compose.yml                     │
│                                       │ + Outbox Relayer + Worker                 │ Dockerfile                             │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ Automated Tests & Validations         │ Pytest unit & integration test suite,     │ 11_AI_Assisted_Validation/             │
│                                       │ 10k concurrent load test, 30s fault test  │   test_e2e_api.py                      │
│                                       │                                           │   test_10k_flash_concurrency.py        │
│                                       │                                           │   test_30s_outage_recovery.py          │
├───────────────────────────────────────┼───────────────────────────────────────────┼────────────────────────────────────────┤
│ 12_Presentation/ & Hand-off           │ Member 4 AWS deployment mapping, pitch    │ 12_Presentation/AWS_Deployment_Plan.md │
│                                       │ deck, jury defense guide                  │ README.md                              │
└───────────────────────────────────────┴───────────────────────────────────────────┴────────────────────────────────────────┘
```

---

## 2. Technical Stack Selection

To ensure immediate local and containerized execution on modern infrastructure, the system is built with:
- **Application Runtime:** Python 3.10+ with **FastAPI** (asynchronous ASGI framework with native OpenAPI 3.1 generation and pydantic v2 data validation).
- **In-Memory Contention Engine:** **Redis 7.x** running atomic single-threaded Lua scripts for sub-millisecond stock decrement ($< 1\text{ ms}$).
- **Transactional Database:** **PostgreSQL 15+** with SQLAlchemy 2.0 ORM + raw transactional SQL fallback, enforcing mathematical non-negative check constraints and Transactional Outbox tables.
- **Message Broker & Event Bus:** High-throughput Redis Streams / Persistent Outbox Queue (simulating Kafka / AWS SQS) providing durable at-least-once delivery with partition/consumer group semantics.
- **Container Orchestration:** **Docker & Docker Compose** configuring multi-container services with network isolation, healthchecks, and volume persistence.
- **Testing Engine:** **Pytest** + **Concurrent Futures** testing high concurrency, idempotency, and outage recovery.

---

## 3. Execution Pipeline Flow

```
1. Database Setup:
   Postgres initialized with `04_Database/schema.sql` (Tables, Constraints, Enums).
   `04_Database/seed.py` seeds Product X (100 units) and test accounts.

2. Inventory Service:
   Executes Redis atomic Lua reservation script.
   Registers 300s TTL lease.
   Persists confirmed reservation to PostgreSQL.

3. Checkout & Payment Service:
   Coordinates client session with active reservation.
   Executes idempotent charge with mock gateway.
   Atomically inserts payment record + Transactional Outbox event.

4. Event Relay & Order Service:
   Outbox Relayer publishes `PaymentSucceeded` event.
   Order Service consumes event, validates Inbox deduplication, and commits confirmed Order.
   If Order Service crashes for 30s, events safely buffer in broker and drain upon recovery.

5. Verification:
   Automated pytest suite validates all invariants:
   - Sum of (Available + Reserved + Sold) == 100
   - Confirmed Sales <= 100
   - Zero duplicate reservations or charges.
```

---

*End of Implementation Map — Authoritative execution blueprint.*
