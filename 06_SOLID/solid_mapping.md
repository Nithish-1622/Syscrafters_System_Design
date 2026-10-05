# 06_SOLID — Object-Oriented Principles Mapping

This document provides a concrete, engineering-grade mapping of the five **SOLID** principles applied directly across the **SALESTORM** microservices codebase. Generic textbook abstractions have been rejected in favor of implementation-ready classes, ports, and aggregates.

---

## 1. Single Responsibility Principle (SRP)

> **Core Rule:** A class should have one, and only one, reason to change.

```
                    ┌─────────────────────────────────────────────────────────┐
                    │               VIOLATION (ANTI-PATTERN)                  │
                    │                  ECommerceGodService                    │
                    │   - reserveStock()         - capturePayment()           │
                    │   - createOrder()          - sendEmailNotification()    │
                    │   - calculateShipping()    - generateInvoicePDF()       │
                    └─────────────────────────────────────────────────────────┘
                                                 │
                                        REFACTORED INTO SRP
                                                 ▼
┌────────────────────────────────┐ ┌────────────────────────────────┐ ┌────────────────────────────────┐
│ ReservationApplicationService  │ │   PaymentApplicationService    │ │    OrderApplicationService     │
│  - Atomically reserves stock   │ │  - Orchestrates gateway charge │ │  - Progresses order lifecycle  │
│  - Handles TTL lock expiry     │ │  - Resolves ambiguous timeouts │ │  - Validates state transitions │
└────────────────────────────────┘ └────────────────────────────────┘ └────────────────────────────────┘
```

### SALESTORM Concrete SRP Mapping

| Component / Class | Single Reason to Change | Separated Responsibilities (What it Does NOT do) |
| :--- | :--- | :--- |
| `ReservationApplicationService` | Changes in stock reservation business rules and TTL algorithms. | Does **NOT** process credit cards, calculate shipping, or send customer push notifications. |
| `ReservationExpiryScheduler` | Changes in background sweeping frequency or batch scheduling mechanics. | Does **NOT** accept user HTTP requests or create orders. |
| `PaymentReconciliationService` | Changes in PSP polling policies or ambiguous timeout verification rules. | Does **NOT** handle stock reservations or order state updates. |
| `TransactionalOutboxDispatcher`| Changes in message transport reliability or Kafka batch publishing. | Does **NOT** execute domain business validation. |
| `Order` Aggregate Root | Changes in order domain invariants (e.g. line-item calculation, state progression). | Does **NOT** interact with the database or call external carrier APIs directly. |

---

## 2. Open/Closed Principle (OCP)

> **Core Rule:** Software entities should be open for extension, but closed for modification.

```
                                  ┌───────────────────────────┐
                                  │  IPaymentProviderAdapter  │
                                  │   (Closed for Mutation)   │
                                  └─────────────▲─────────────┘
                                                │
                 ┌──────────────────────────────┼──────────────────────────────┐
                 │                              │                              │
  ┌──────────────┴──────────────┐ ┌─────────────┴─────────────┐ ┌──────────────┴──────────────┐
  │    StripePaymentAdapter     │ │    PayPalPaymentAdapter   │ │    UPIPaymentAdapter (New)   │
  │   (Open for Extension)      │ │   (Open for Extension)    │ │   (Zero core code edits)     │
  └─────────────────────────────┘ └───────────────────────────┘ └─────────────────────────────┘
```

### SALESTORM Concrete OCP Mapping

1. **Payment Gateway Integration:**
   - **Problem:** Adding a new payment partner (e.g., Apple Pay or Razorpay) previously required editing `switch(provider)` statements inside `PaymentApplicationService`.
   - **Design Decision:** `PaymentApplicationService` depends strictly on the `IPaymentProviderAdapter` interface. New providers are added simply by creating a new class implementing `IPaymentProviderAdapter` and registering it in `DefaultPaymentProviderFactory`.
   - **Benefit:** Zero modifications to existing, battle-tested payment processing code.
   - **Trade-off:** Requires defining common request/response DTOs across heterogeneous provider SDKs.

2. **Order State Lifecycle (`IOrderState`):**
   - **Problem:** Adding an intermediate state (e.g., `AWAITING_FRAUD_CHECK`) requires adding new `else if` branches across monolithic order managers.
   - **Design Decision:** State transitions are encapsulated in concrete `IOrderState` implementations (`CreatedState`, `PaymentPendingState`, `ConfirmedState`).
   - **Benefit:** Adding a new state requires creating one class implementing `IOrderState` without breaking existing state transitions.

---

## 3. Liskov Substitution Principle (LSP)

> **Core Rule:** Subtypes must be substitutable for their base types without altering the correctness of the program.

### SALESTORM Concrete LSP Mapping

- **Interface:** `IPaymentProviderAdapter`
  ```java
  public interface IPaymentProviderAdapter {
      GatewayChargeResult processPayment(GatewayChargeRequest request);
      GatewayStatusResult queryPaymentStatus(String providerRef, String idempotencyKey);
  }
  ```
- **LSP Contract Invariants:**
  1. **No Unexpected Runtime Exceptions:** `StripePaymentAdapter`, `PayPalPaymentAdapter`, and `RazorpayPaymentAdapter` must never throw unhandled vendor-specific runtime exceptions (e.g., `StripeException`, `PayPalRESTException`) to the caller. Instead, they catch and translate them into standard domain result objects (`GatewayChargeResult.declined()`, `GatewayChargeResult.timeout()`).
  2. **Preconditions & Postconditions:** No subtype may strengthen preconditions (e.g., demanding extra mandatory fields not in `GatewayChargeRequest`) or weaken postconditions (e.g., returning null instead of a valid `GatewayChargeResult`).
- **Benefit:** `PaymentApplicationService` can execute any provider interchangeably without defensive `instanceof` checks.

---

## 4. Interface Segregation Principle (ISP)

> **Core Rule:** Clients should not be forced to depend on methods they do not use.

```
                              VIOLATION (FAT INTERFACE)
        ┌───────────────────────────────────────────────────────────────────┐
        │                     IECommerceRepository                          │
        │  +saveProduct()    +reserveStock()     +chargeCard()              │
        │  +saveOrder()      +sendSMS()          +generateShippingLabel()   │
        └───────────────────────────────────────────────────────────────────┘
                                          │
                               REFACTORED INTO FOCUSED PORTS
                                          ▼
┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐
│  IInventoryRepository  │  │   IOrderRepository     │  │   IPaymentRepository   │  │   IOutboxRepository    │
│  +reserveStockAtomic() │  │   +findById()          │  │   +findById()          │  │   +saveEvent()         │
│  +releaseStockAtomic() │  │   +save()              │  │   +save()              │  │   +fetchUnsentEvents() │
└────────────────────────┘  └────────────────────────┘  └────────────────────────┘  └────────────────────────┘
```

### SALESTORM Concrete ISP Mapping

| Fat Interface Anti-Pattern | Segregated SALESTORM Interfaces | Consuming Client |
| :--- | :--- | :--- |
| Monolithic `IDataStore` | `IInventoryRepository` | `ReservationApplicationService` |
| Monolithic `IDataStore` | `IReservationRepository` | `ReservationExpiryScheduler` |
| Monolithic `IMessageBus` | `IEventPublisher` | Application Services (Publish-only) |
| Monolithic `IMessageBus` | `IProcessedEventRepository` | `IdempotentEventProcessor` (Dedup-only) |

---

## 5. Dependency Inversion Principle (DIP)

> **Core Rule:** High-level modules should not depend on low-level modules. Both should depend on abstractions. Abstractions should not depend on details; details should depend on abstractions.

```
High-Level Policy (Domain / App)           [ReservationApplicationService]
                                                          │
                                                          ▼ (Depends on Interface)
Abstraction (Port)                               [IInventoryRepository]
                                                          ▲
                                                          │ (Implements Interface)
Low-Level Infrastructure (Adapter)         [PostgresInventoryRepository]
```

### SALESTORM Concrete DIP Mapping

1. **Core Domain Independence:**
   - `ReservationApplicationService` (High-Level Policy) does **not** import `org.postgresql.Driver` or `redis.clients.jedis.Jedis`.
   - It depends exclusively on `IInventoryRepository` and `IIdempotencyStore` (Abstractions).
2. **Infrastructure Plug-and-Play:**
   - Database implementations (`PostgresInventoryRepository`, `DynamoDBInventoryRepository`) and cache adapters (`RedisIdempotencyStore`, `InMemoryIdempotencyStore` for unit testing) depend on the domain ports.
   - **Benefit:** Entire persistence engines can be swapped or mocked in unit tests without changing a single line of domain business logic.
