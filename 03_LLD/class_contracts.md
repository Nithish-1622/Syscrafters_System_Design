# SALESTORM 2026 | Low-Level Design (LLD) Class Contracts & Interfaces

## 1. Domain Interfaces & Repository Contracts

This document formalizes the object-oriented contracts, interfaces, and state machines established by Member 2 and implemented physically by Member 3.

```mermaid
classDiagram
    class IInventoryRepository {
        <<interface>>
        +reserveAtomic(productId: UUID, quantity: int, idempotencyKey: string): ReservationResult
        +releaseHold(reservationId: UUID, reason: string): boolean
        +confirmSale(reservationId: UUID): boolean
        +getSnapshot(productId: UUID): InventorySnapshot
    }

    class IPaymentGateway {
        <<interface>>
        +authorizeCharge(token: string, amount: Decimal, currency: string, idempotencyKey: string): PaymentGatewayResponse
        +verifyWebhookSignature(payload: string, signature: string, timestamp: long): boolean
        +queryTransactionStatus(providerTxId: string): PaymentGatewayResponse
    }

    class IOrderRepository {
        <<interface>>
        +createOrderFromReservation(reservationId: UUID, paymentId: UUID, address: Address): Order
        +getOrderById(orderId: UUID): Order
        +updateStatus(orderId: UUID, status: OrderStatus): void
    }

    class IIdempotencyStore {
        <<interface>>
        +acquireLock(key: string, scope: string, hash: string, ttl: Duration): LockStatus
        +recordResponse(key: string, code: int, body: string): void
        +getResponse(key: string): CachedResponse
    }

    class IEventPublisher {
        <<interface>>
        +publishToOutbox(event: CloudEvent): void
        +dispatchPendingEvents(): int
    }
```

---

## 2. Domain State Machines

### 2.1 Inventory Reservation State Machine
```mermaid
stateDiagram-v2
    [*] --> RESERVED: Atomic Reservation Created
    RESERVED --> PAYMENT_PENDING: Customer Lands on Payment Screen
    PAYMENT_PENDING --> CONFIRMED: Payment Succeeded
    CONFIRMED --> SOLD: Order Fulfilled
    
    PAYMENT_PENDING --> PAYMENT_FAILED: Card Declined
    PAYMENT_FAILED --> RELEASED: Compensating Release (Stock Restored)
    
    RESERVED --> EXPIRED: 5-Minute TTL Elapsed
    EXPIRED --> RELEASED: Reaper Job Restores Stock
    RELEASED --> [*]
    SOLD --> [*]
```

### 2.2 Payment State Machine
```mermaid
stateDiagram-v2
    [*] --> INITIATED: Customer Submits Payment
    INITIATED --> PROCESSING: Dispatched to Gateway
    PROCESSING --> SUCCEEDED: Gateway 200 / Webhook Approved
    PROCESSING --> FAILED: Gateway Decline / Insufficient Funds
    PROCESSING --> TIMED_OUT: Network Socket Timeout
    TIMED_OUT --> RECONCILIATION_REQUIRED: Provider Poller Triggered
    RECONCILIATION_REQUIRED --> SUCCEEDED: Poller Discovers Charge Settled
    RECONCILIATION_REQUIRED --> FAILED: Poller Confirms No Charge
    SUCCEEDED --> [*]
    FAILED --> [*]
```

### 2.3 Order Lifecycle State Machine
```mermaid
stateDiagram-v2
    [*] --> CREATED: Event Consumed
    CREATED --> CONFIRMED: Reservation Linked
    CONFIRMED --> PROCESSING: Pick & Pack in Warehouse
    PROCESSING --> SHIPPED: Carrier Dispatched
    SHIPPED --> OUT_FOR_DELIVERY: Final Mile Scan
    OUT_FOR_DELIVERY --> DELIVERED: Customer Signature Received
    CONFIRMED --> CANCELLED: Order Cancellation
    DELIVERED --> [*]
    CANCELLED --> [*]
```
