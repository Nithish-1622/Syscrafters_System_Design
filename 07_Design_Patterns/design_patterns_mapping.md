# 07_Design_Patterns — Design Patterns Mapping & Engineering Evaluation

This document details the object-oriented design patterns implemented within the **SALESTORM** architecture. Every pattern is justified by a concrete architectural challenge, with full analysis of classes involved, runtime interactions, benefits, trade-offs, and defense against simpler alternatives.

---

## 1. Master Design Pattern Matrix

| Pattern | Category | SALESTORM Component | Primary Problem Solved | Trade-off Introduced |
| :--- | :--- | :--- | :--- | :--- |
| **Strategy** | Behavioral | `IPaymentStrategy` / Payment Provider selection | Dynamic routing between credit cards, UPI, wallets at runtime. | Additional interface indirection. |
| **Adapter** | Structural | `StripePaymentAdapter`, `PayPalPaymentAdapter` | Shielding domain from third-party vendor SDKs and breaking changes. | Translation overhead between vendor DTOs and domain models. |
| **State** | Behavioral | `IOrderState` (`CreatedState`, `ConfirmedState`...) | Enforcing valid order state transitions; eliminating fragile `switch-case` blocks. | Increased number of small state classes. |
| **Factory** | Creational | `DefaultPaymentProviderFactory` | Encapsulating runtime instantiation of payment adapters. | Extra factory boilerplate. |
| **Repository** | Architectural | `IInventoryRepository`, `IOrderRepository` | Decoupling domain entities from SQL queries and relational ORMs. | Mapping overhead between DB records and rich domain aggregates. |
| **Circuit Breaker** | Reliability | `Resilience4jCircuitBreakerAdapter` | Preventing thread pool exhaustion when external PSPs encounter downtime/latency spikes. | Added latency check per call; tuning complexity for thresholds. |
| **Transactional Outbox** | Distributed / Structural | `TransactionalOutboxDispatcher` | Solving dual-write race condition (DB write + Kafka publish) atomically. | Polling latency and secondary database table storage. |

---

## 2. Deep-Dive Pattern Specifications

### 2.1 Adapter Pattern (Structural)
- **Problem & Context:** External payment providers (Stripe, PayPal, Razorpay) use drastically different SDK interfaces, request formats (JSON vs form-urlencoded), error structures, and response schemas. Direct coupling would contaminate the core payment domain.
- **Pattern Solution:** Implement `IPaymentProviderAdapter` as an internal domain port. Each external SDK is wrapped inside a dedicated adapter (`StripePaymentAdapter`, `PayPalPaymentAdapter`).
- **Classes Involved:**
  - Target Interface: `IPaymentProviderAdapter`
  - Concrete Adapters: `StripePaymentAdapter`, `PayPalPaymentAdapter`
  - Adaptees: `StripeClient`, `PayPalHttpClient`
  - Client: `PaymentApplicationService`
- **Benefit:** If Stripe changes its API version or fields, only `StripePaymentAdapter` is modified. Zero changes to domain entities or business services.
- **Why Chosen over Simpler Alternative:** A simpler alternative of direct HTTP calls inside the service leads to massive vendor lock-in and impossible unit testing without live network mocks.

---

### 2.2 Strategy Pattern (Behavioral)
- **Problem & Context:** Customers can choose different payment instruments (Credit Card, Instant Bank UPI, Digital Wallet) each with distinct validation and processing mechanics.
- **Pattern Solution:** Define `IPaymentStrategy` allowing `PaymentApplicationService` to select the processing algorithm dynamically at runtime based on the incoming request payload.
- **Classes Involved:**
  - Strategy Interface: `IPaymentStrategy`
  - Concrete Strategies: `CardPaymentStrategy`, `UPIPaymentStrategy`, `WalletPaymentStrategy`
  - Context: `PaymentApplicationService`
- **Benefit:** Simplifies unit testing of individual payment instrument validation rules; clean Open/Closed Principle adherence.

---

### 2.3 State Pattern (Behavioral)
- **Problem & Context:** Order lifecycle involves multiple strictly ordered states (`CREATED` $\rightarrow$ `PAYMENT_PENDING` $\rightarrow$ `CONFIRMED` $\rightarrow$ `PROCESSING` $\rightarrow$ `SHIPPED` $\rightarrow$ `DELIVERED`). Large `if-else` or `switch` statements scattered across services are error-prone and risk invalid jumps (e.g. `CREATED` $\rightarrow$ `DELIVERED`).
- **Pattern Solution:** Encapsulate state-specific behavior and transition guards inside `IOrderState` classes (`CreatedState`, `PaymentPendingState`, `ConfirmedState`, `ShippedState`).
- **Classes Involved:**
  - Context: `Order` Aggregate Root
  - State Interface: `IOrderState`
  - Concrete States: `CreatedState`, `PaymentPendingState`, `ConfirmedState`, `ProcessingState`, `ShippedState`, `DeliveredState`, `CancelledState`
- **Interaction:**
  ```java
  public void confirmPayment(PaymentTransactionId paymentId) {
      // Order delegates validation directly to current state object
      this.currentState = this.currentState.transitionTo(this, OrderStatus.CONFIRMED);
  }
  ```
- **Trade-off:** Creates 7+ small classes instead of a single enum. Justified by absolute domain safety against invalid state corruption.

---

### 2.4 Factory Pattern (Creational)
- **Problem & Context:** Decoupling the creation and lookup of provider adapters from the business workflow.
- **Pattern Solution:** `DefaultPaymentProviderFactory` encapsulates the mapping between `PaymentProviderType` enums and singleton adapter instances.
- **Classes Involved:**
  - Factory Interface: `IPaymentProviderFactory`
  - Concrete Factory: `DefaultPaymentProviderFactory`
- **Benefit:** Allows mock adapters to be injected during automated CI/CD pipeline integration tests.

---

### 2.5 Repository Pattern (Architectural)
- **Problem & Context:** Direct SQL / ORM annotations inside domain aggregates couple business invariants to database storage mechanics.
- **Pattern Solution:** `IInventoryRepository`, `IOrderRepository`, and `IPaymentRepository` expose collection-like domain interfaces (`findById()`, `save()`, `reserveStockAtomic()`).
- **Benefit:** Complete isolation of domain business rules from database schema evolution. Facilitates testing with in-memory test doubles.

---

### 2.6 Circuit Breaker Pattern (Reliability / Structural)
- **Problem & Context:** When third-party payment gateways suffer latency spikes (e.g., 30s response time instead of 200ms), synchronous HTTP client threads back up, exhausting Tomcat/Netty thread pools and crashing the entire platform.
- **Pattern Solution:** Wrap external adapter calls inside `ICircuitBreaker` (`Resilience4jCircuitBreakerAdapter`).
- **Behavior:**
  - **Tripping:** 50% failures in a 20-call sliding window transitions state to `OPEN`.
  - **Fast Fail:** Immediate `503 Service Unavailable` returned to caller in <1ms without opening outbound network sockets.
  - **Auto-Recovery:** `HALF-OPEN` probe checks gateway health after 15 seconds.

---

## 3. Deliberately Rejected Patterns & Anti-Pattern Defense

### ❌ Rejected: Monolithic Facade (God Object)
- **Why Rejected:** Creating a single `ECommerceCheckoutFacade` that coordinates inventory decrement, payment gateway, order creation, and email sending turns into a giant monolithic god class with high coupling.
- **Adopted Alternative:** Autonomous microservices communicating via explicit Domain Events over Kafka/RabbitMQ.

### ❌ Rejected: Distributed Two-Phase Commit (2PC) / XA Transactions
- **Why Rejected:** 2PC across Inventory, Payment, and Order databases creates catastrophic lock contention under flash-sale spikes, reducing availability to the lowest common denominator.
- **Adopted Alternative:** SAGA Choreography with Idempotent Event Consumers and compensating transactions.

### ❌ Rejected: In-Memory JVM Singleton Observer Pattern for Cross-Service Events
- **Why Rejected:** An in-process `java.util.Observable` or Guava `EventBus` cannot span microservice network boundaries and loses all events on pod crash.
- **Adopted Alternative:** Distributed Event Publishing via Message Broker (Kafka) backed by the Transactional Outbox Pattern.
