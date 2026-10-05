# Inventory Reservation Lifecycle — State Diagram

## 1. Formal State Machine Definition

The **Inventory Reservation Lifecycle** governs the temporary holding and eventual confirmation or release of limited physical stock during a flash sale.

```mermaid
stateDiagram-v2
    [*] --> AVAILABLE : Stock Loaded in Warehouse

    AVAILABLE --> RESERVED : ReserveStockCmd [Stock >= Qty]<br/>/ Decrement Available, Increment Reserved, Set TTL=10m

    AVAILABLE --> SOLD_OUT : Stock == 0

    state RESERVED {
        [*] --> ACTIVE_HOLD : Stamped with expires_at

        ACTIVE_HOLD --> PAYMENT_PENDING : InitiateCheckoutCmd<br/>/ Payment flow started
        
        ACTIVE_HOLD --> EXPIRED : TTL Expiry Sweep [now > expires_at]<br/>/ CAS status to EXPIRED
        
        ACTIVE_HOLD --> RELEASED : CustomerCancelCmd<br/>/ Increment Available, Decrement Reserved
    }

    state PAYMENT_PENDING {
        PAYMENT_PENDING --> CONFIRMED : PaymentSucceededEvent<br/>/ Decrement Reserved, Increment Sold
        
        PAYMENT_PENDING --> RELEASED : PaymentFailedEvent<br/>/ Increment Available, Decrement Reserved
        
        PAYMENT_PENDING --> RELEASED : PaymentTimeoutExpired [TTL Exceeded]<br/>/ Increment Available, Decrement Reserved
    }

    EXPIRED --> RELEASED : ExpiryWorker.releaseStock()<br/>/ Increment Available, Decrement Reserved

    CONFIRMED --> SOLD : OrderFulfilledEvent
    
    RELEASED --> AVAILABLE : Stock Restored [if total > sold]
    
    SOLD --> [*]
```

---

## 2. State Transition & Invariant Rules

| Current State | Trigger / Event | Target State | Invariants & Side Effects | Error / Invalid Transition Handling |
| :--- | :--- | :--- | :--- | :--- |
| `AVAILABLE` | `ReserveStockCmd` | `RESERVED` | $available \ge qty$. Atomic SQL: $available = available - qty, reserved = reserved + qty$. | If $available < qty$, throws `InsufficientStockException` (Returns `422 Unprocessable`). |
| `RESERVED` | `InitiateCheckoutCmd` | `PAYMENT_PENDING` | Validates $now < expires\_at$. Extends lock if in active checkout session. | If $now \ge expires\_at$, transition rejected $\rightarrow$ `ReservationExpiredException`. |
| `RESERVED` | `TTL Expiry Sweep` | `EXPIRED` | Invoked by `ReservationExpiryScheduler`. CAS ensures single worker transitions. | If already `CONFIRMED`, CAS returns 0 rows updated, skipping release. |
| `EXPIRED` | `ReleaseStockJob` | `RELEASED` | Atomic SQL: $available = available + qty, reserved = reserved - qty$. Emits `ReservationReleasedEvent`. | Idempotent; duplicate release attempts prevented by status check. |
| `PAYMENT_PENDING` | `PaymentSucceededEvent` | `CONFIRMED` | Finalizes purchase. Atomic SQL: $reserved = reserved - qty, sold = sold + qty$. | Direct jump from `AVAILABLE` or `EXPIRED` is blocked at domain model. |
| `PAYMENT_PENDING` | `PaymentFailedEvent` | `RELEASED` | Restores stock to `AVAILABLE`. Atomic SQL: $available = available + qty, reserved = reserved - qty$. | Idempotent; cannot be released twice. |
