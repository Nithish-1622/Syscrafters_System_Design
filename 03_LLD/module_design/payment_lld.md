# Payment Service — Low-Level Design

## 1. Service Overview & Problem Scope

The **Payment Service** is responsible for orchestrating secure, idempotent financial transactions across diverse external Payment Service Providers (PSPs) such as Stripe, PayPal, Razorpay, and Bank UPI gateways.

Key requirements:
1. **Zero Duplicate Charges:** Enforce strict transaction-level idempotency so customer network retries never trigger double billing.
2. **Provider Agnosticism & Extensibility:** Support pluggable payment gateways via the **Adapter** and **Strategy** patterns without polluting the core payment domain.
3. **Resilient Ambiguous Timeout Handling:** A network timeout with an external gateway does **NOT** equal payment failure. The system must transition to a verifiable pending state and perform idempotent reconciliation / status queries before taking action.
4. **Circuit Breaker & Retry Safety:** Shield the service from downstream gateway outages using the **Circuit Breaker** pattern and exponential backoff jitter.
5. **Decoupled Event Dispatch:** Inform Inventory and Order services asynchronously upon verified payment completion.

---

## 2. Hexagonal Domain Architecture & Layer Separation

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            PAYMENT SERVICE BOUNDARY                             │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                        API / Webhook Layer                              │   │
│   │   [PaymentController]               [PaymentWebhookController]          │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                       Application Service Layer                         │   │
│   │   [PaymentApplicationService]       [PaymentReconciliationService]      │   │
│   │   [PaymentIdempotencyManager]       [PaymentRetryScheduler]             │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                             Domain Layer                                │   │
│   │   Entities:   [PaymentTransaction]   [PaymentMethod]   [RefundRecord]   │   │
│   │   Value Obj:  [Money]  [TransactionId]  [ProviderReferenceId]  [Token]  │   │
│   │   Enums:      [PaymentStatus]        [PaymentType]      [Currency]      │   │
│   │   Exceptions: [PaymentDeclinedException] [AmbiguousTimeoutException]   │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                        Ports / Abstract Contracts                       │   │
│   │   [IPaymentProviderAdapter]         [IPaymentRepository]                │   │
│   │   [ICircuitBreaker]                 [IEventPublisher]                   │   │
│   │   [IIdempotencyStore]               [IPaymentProviderFactory]           │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                        Adapters (Infrastructure)                        │   │
│   │   [StripePaymentAdapter]            [PayPalPaymentAdapter]              │   │
│   │   [Resilience4jCircuitBreaker]      [PostgresPaymentRepository]         │   │
│   │   [KafkaPaymentEventPublisher]      [RedisIdempotencyStore]             │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Class & Interface Specification

### 3.1 Domain Model & Entities

#### `PaymentTransaction` (Aggregate Root)
- **Attributes:**
  - `transactionId: PaymentTransactionId` (UUID v4)
  - `idempotencyKey: IdempotencyKey` (Mandatory client token)
  - `orderId: OrderId`
  - `reservationId: ReservationId`
  - `customerId: CustomerId`
  - `amount: Money` (Value Object: `amount: BigDecimal, currency: Currency`)
  - `providerType: PaymentProviderType` (`STRIPE`, `PAYPAL`, `UPI`, `RAZORPAY`)
  - `providerReferenceId: Optional[String]` (External gateway charge ID, e.g. `ch_3M...`)
  - `status: PaymentStatus` (`INITIATED`, `PENDING_VERIFICATION`, `SUCCESS`, `FAILED`, `CANCELLED`, `REFUNDED`)
  - `failureReason: Optional[String]`
  - `retryCount: Int`
  - `createdAt: Instant`
  - `completedAt: Optional[Instant]`
- **Methods:**
  - `markInitiated(providerRef: String): Unit`
  - `markSuccess(providerRef: String, completedAt: Instant): Unit`
  - `markFailed(reason: String): Unit`
  - `markPendingVerification(reason: String): Unit` — Triggered when external provider request times out or gives HTTP 5xx.
  - `canRetry(): Boolean` — Returns true if status is `PENDING_VERIFICATION` and `retryCount < MAX_RETRIES`.

#### `Money` (Value Object)
- **Attributes:** `amount: BigDecimal`, `currency: Currency`
- **Invariants:** `amount > 0`, `currency` cannot be null.
- **Methods:** `add(other: Money): Money`, `equals(other: Object): Boolean`

---

### 3.2 Ports / Interfaces (SPI)

```java
public interface IPaymentProviderAdapter {
    PaymentProviderType getProviderType();
    
    // Authorize & capture funds via external PSP API
    GatewayChargeResult processPayment(GatewayChargeRequest request);
    
    // Query external provider for status when network timed out
    GatewayStatusResult queryPaymentStatus(String providerReferenceId, String idempotencyKey);
    
    // Refund captured funds on cancellation/failure compensation
    GatewayRefundResult refundPayment(GatewayRefundRequest request);
}
```

```java
public interface IPaymentProviderFactory {
    IPaymentProviderAdapter getProvider(PaymentProviderType type);
}
```

```java
public interface IPaymentRepository {
    Optional<PaymentTransaction> findById(PaymentTransactionId id);
    Optional<PaymentTransaction> findByIdempotencyKey(IdempotencyKey idempotencyKey);
    Optional<PaymentTransaction> findByProviderReferenceId(String providerReferenceId);
    List<PaymentTransaction> findPendingVerificationTransactions(Instant olderThan, int limit);
    void save(PaymentTransaction transaction);
}
```

```java
public interface ICircuitBreaker {
    <T> T execute(Supplier<T> action, FallbackSupplier<T> fallback);
    CircuitBreakerState getState();
}
```

---

### 3.3 Application Services

#### `PaymentApplicationService`
- **Workflow:**
  1. Validates input DTO and verifies payment idempotency via `IIdempotencyStore`.
  2. Resolves concrete provider adapter using `IPaymentProviderFactory.getProvider(dto.providerType)`.
  3. Creates `PaymentTransaction` aggregate in `INITIATED` status and persists to database.
  4. Invokes external gateway through `ICircuitBreaker` wrapped `IPaymentProviderAdapter.processPayment()`.
  5. **Branching based on outcome:**
     - **Success:** Marks transaction `SUCCESS`, saves state, dispatches `PaymentSucceededEvent(transactionId, orderId, reservationId, amount)`.
     - **Definitive Failure (Card Declined, Insufficient Funds):** Marks transaction `FAILED`, saves state, dispatches `PaymentFailedEvent(transactionId, orderId, reservationId, reason)`.
     - **Timeout / Network Error (504 Gateway Timeout, Connection Refused):** Marks transaction `PENDING_VERIFICATION`, logs for reconciliation worker, returns pending status to client.

#### `PaymentReconciliationService`
- Runs as an asynchronous background worker.
- Queries `IPaymentRepository.findPendingVerificationTransactions(olderThan=30seconds, limit=100)`.
- For each record:
  - Invokes `IPaymentProviderAdapter.queryPaymentStatus(providerRef, idempotencyKey)`.
  - If Gateway returns **Captured/Paid**: updates local status to `SUCCESS` and publishes `PaymentSucceededEvent`.
  - If Gateway returns **Not Found / Cancelled**: updates local status to `FAILED` and publishes `PaymentFailedEvent`.
  - If Gateway is still unreachable: increments `retryCount`, schedules next poll with exponential backoff; triggers manual alert if retry limit exceeded.

---

## 4. Payment Timeout & Ambiguity Resolution Strategy

```
               [PaymentApplicationService]
                           │
                           ▼
          [StripePaymentAdapter.processPayment()]
                           │
           ┌───────────────┴───────────────┐
           │                               │
    HTTP 200 (Success)           HTTP 504 / ReadTimeout
           │                               │
           ▼                               ▼
 [Mark Tx SUCCESS]              [Mark Tx PENDING_VERIFICATION]
           │                               │
 [Publish PaymentSucceededEvent]           ▼
                                [PaymentReconciliationService]
                                (Background Poller / Webhook)
                                           │
                                           ▼
                                [Query Gateway Status API]
                                           │
                                ┌──────────┴──────────┐
                                │                     │
                          Gateway: PAID         Gateway: UNPAID/NOT FOUND
                                │                     │
                                ▼                     ▼
                       [Mark Tx SUCCESS]      [Mark Tx FAILED]
                                │                     │
                       [Publish Succeeded]    [Publish Failed Event]
                                                      │
                                                      ▼
                                            [Inventory Service: Release]
```

---

## 5. Circuit Breaker Integration

To prevent thread exhaustion when an external payment provider suffers from high latency or an outage:
1. **CLOSED State (Normal):** Requests pass directly to `StripePaymentAdapter`.
2. **OPEN State (Trip condition: 50% failure rate over 20 requests):** Adapter immediately throws `GatewayUnavailableException` without waiting for network timeouts.
3. **HALF-OPEN State (After 15s wait):** Trial requests are permitted. If successful, transitions back to CLOSED; if failures continue, transitions to OPEN.
4. **Fallback Handling:** Re-routes transaction to secondary fallback provider (e.g. Razorpay if Stripe is degraded) or returns a clean `503 Service Unavailable` allowing client to retry later without consuming gateway connections.
