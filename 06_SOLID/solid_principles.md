# SALESTORM 2026 | SOLID Principles Implementation Guide

## 1. Single Responsibility Principle (SRP)
- **Inventory Service**: Exclusively manages stock balances, row-level latching, and reservation lifecycles. It does NOT process credit cards or generate shipping labels.
- **Payment Service**: Exclusively handles payment tokenization, provider gateway adapters, and webhook signature verification. It does NOT directly mutate inventory tables.
- **Order Service**: Exclusively orchestrates order lifecycle states, customer line items, and fulfillment dispatch.

---

## 2. Open / Closed Principle (OCP)
- The payment subsystem defines the `IPaymentGateway` interface:
  ```java
  public interface IPaymentGateway {
      PaymentResponse charge(PaymentRequest request);
  }
  ```
- **Extension without Modification**: Adding new gateways (`StripeGatewayAdapter`, `AdyenGatewayAdapter`, `ApplePayAdapter`) requires implementing the interface. The core checkout orchestrator is untouched.

---

## 3. Liskov Substitution Principle (LSP)
- Implementations of `IIdempotencyStore` (`PostgresIdempotencyStore`, `RedisIdempotencyStore`) conform to identical state machine contracts. 
- Switching between in-memory Redis and persistent PostgreSQL for idempotency storage preserves identical exception contracts and return semantics without breaking the API Gateway layer.

---

## 4. Interface Segregation Principle (ISP)
- Rather than a bloated `IInventoryService` interface, clients depend on lean, role-specific interfaces:
  - `IStockReader`: For catalog browsing (`getAvailableStock(productId)`).
  - `IStockReservation`: For checkout checkout holds (`reserveAtomic(...)`, `releaseHold(...)`).
  - `IStockAuditor`: For compliance audits (`reconcilePhysicalStock(...)`).

---

## 5. Dependency Inversion Principle (DIP)
- High-level domain business logic (`CheckoutUseCase`, `PaymentConfirmationSaga`) depends strictly on high-level abstractions (`IInventoryRepository`, `IEventPublisher`), not low-level database drivers (`psycopg2`, `pgx`) or specific cloud queues.
- This decoupling allows Member 4 to seamlessly map repositories to AWS Aurora PostgreSQL, AWS SQS, or DynamoDB without rewriting domain logic.
