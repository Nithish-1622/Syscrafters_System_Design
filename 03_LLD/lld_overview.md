# 03_LLD — Low-Level Design Overview

## 1. Executive Summary & Scope

As **Member 2 (LLD, Object-Oriented Design, SOLID & Design Patterns Engineer)** of the SALESTORM engineering team, this directory contains the complete, implementation-ready object-oriented blueprint for the critical transaction services of the **SALESTORM Flash-Sale Platform**.

SALESTORM solves the core business challenge:
> **"How can we handle 10,000 concurrent purchase requests for 100 available units without overselling, while maintaining strict payment idempotency, reliable order lifecycle progression, and resilient recovery when downstream services fail?"**

This Low-Level Design (LLD) strictly consumes the architectural decisions established in **02_HLD** and provides clear domain models, interfaces, sequence diagrams, state models, and design patterns.

```
                    ┌───────────────────────────────────────────┐
                    │               CLIENT / API                │
                    └─────────────────────┬─────────────────────┘
                                          │
                  ┌───────────────────────┼───────────────────────┐
                  ▼                       ▼                       ▼
       ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
       │  Inventory Service  │ │   Payment Service   │ │    Order Service    │
       │  (Concurrency &     │ │  (Idempotency &     │ │  (State Machine &   │
       │   Reservation)      │ │   Gateway Adapter)  │ │   Event Recovery)   │
       └─────────────────────┘ └─────────────────────┘ └─────────────────────┘
                  │                       │                       │
                  └───────────────────────┴───────────────────────┘
                                          │
                                          ▼
                            ┌───────────────────────────┐
                            │  Durable Message Broker   │
                            │ (At-Least-Once Delivery)  │
                            └───────────────────────────┘
```

---

## 2. Directory Structure & Document Navigation

The LLD is structured across modular specifications and visual UML diagrams:

```
03_LLD/
├── class_diagrams/
│   ├── inventory_class_diagram.md     # Domain, Application, Port & Adapter classes for Inventory/Reservation
│   ├── payment_class_diagram.md       # Payment orchestration, Providers, Idempotency & Adapters
│   └── order_class_diagram.md         # Order aggregate, State pattern, Event consumers & Outbox
├── sequence_diagrams/
│   ├── purchase_reservation_sequence.md # 10,000 concurrent Buy requests, Idempotency & Concurrency paths
│   ├── payment_sequence.md            # Synchronous initiation, Gateway callback, Timeout & Safe Reconciliation
│   └── order_recovery_sequence.md     # Payment success with 30s Order Service outage & Idempotent replay
├── state_diagrams/
│   ├── reservation_state.md           # Formal FSM for Inventory Reservation lifecycle & Expiration
│   └── order_state.md                 # Formal FSM for Order lifecycle, Valid & Guarded transitions
├── module_design/
│   ├── inventory_lld.md               # Detailed class/method specs, Concurrency Control, Expiration worker
│   ├── payment_lld.md                 # Payment provider abstraction, Timeout resolution, Idempotency engine
│   └── order_lld.md                   # Order aggregate root, Event-driven idempotency, Outbox dispatcher
└── lld_overview.md                    # This document
```

---

## 3. Core Architectural Constraints & LLD Derivations

| Architectural Decision (HLD) | LLD Realization & OOP Construct |
| :--- | :--- |
| **No In-Memory Shared Locks Across Services** | Services are autonomous microservices communicating via clean HTTP/gRPC interfaces and Async Domain Events. |
| **Deterministic Stock Decrement (100 units max)** | Conditional Atomic Update via `InventoryRepository.decrementAvailableAndReserveAtomic()` combined with Distributed Lock / Optimistic Versioning Port. |
| **Temporary Reservation with Auto-Release** | `ReservationAggregate` with `expires_at` timestamp + `ReservationExpiryJob` running periodic sweep + TTL expiration events. |
| **Payment Provider Agnosticism** | `IPaymentProvider` abstraction using the **Adapter** & **Strategy** patterns; zero provider-specific leaking into core domain. |
| **Ambiguous Payment Timeout Safety** | Two-phase timeout handling: `PaymentTransaction.markPendingVerification()` → `PaymentReconciliationService` queries gateway before retry. |
| **Order Outage Resilience (30s downtime)** | Message broker with Dead Letter Queue (DLQ) + `IdempotentEventConsumer` using transactional deduplication on `processed_events`. |
| **Extensibility for New Rules / Providers** | Strategy and Factory abstractions for payment methods, discount calculations, and shipping partner integration. |

---

## 4. Cross-Cutting Design Standards

### 4.1 Layered Domain-Driven Architecture (Hexagonal / Ports & Adapters)
Each critical service adheres to a clean separation of concerns:
1. **API / Presentation Layer:** REST/gRPC Controllers handling HTTP parsing, header extraction (`Idempotency-Key`), and DTO transformations.
2. **Application Service Layer:** Use-case orchestration, transaction demarcation, security context checks, and idempotency interception.
3. **Domain Layer:** Pure business entities, Aggregates, Value Objects, Domain Services, and State transitions. Zero infrastructure imports.
4. **Ports (Interfaces):** Driven (SPI) and Driving (API) interfaces (e.g., `IInventoryRepository`, `IPaymentGatewayAdapter`, `IEventPublisher`).
5. **Adapters (Infrastructure):** Database repositories (SQL/PostgreSQL), Redis caching/locks, Payment gateway HTTP clients, Message broker publishers (Kafka/SQS).

### 4.2 Idempotency Contract
All mutating endpoints accept an `Idempotency-Key` header:
- **Hash calculation:** `IdempotencyRecord(key, request_hash, status, response_payload, created_at, locked_until)`
- **Conflict detection:** Concurrent requests with the exact same key return `409 Conflict` (if in-flight) or the cached response `200/201` (if completed).

### 4.3 Error Handling & Fault Isolation
- **Domain Exceptions:** `InsufficientStockException`, `ReservationExpiredException`, `InvalidOrderStateTransitionException`, `PaymentDeclinedException`.
- **Infrastructure Exceptions:** `OptimisticLockingFailureException`, `PaymentGatewayTimeoutException`, `BrokerUnavailableException`.
- **Circuit Breaker:** Applied on all outbound external HTTP adapters (`StripeAdapter`, `PayPalAdapter`) to prevent cascade thread exhaustion.
