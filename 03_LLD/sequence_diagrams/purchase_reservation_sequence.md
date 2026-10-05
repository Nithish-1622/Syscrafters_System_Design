# Purchase & Reservation Sequence Diagram

## 1. Concurrency Scenario: 10,000 Concurrent Requests for 100 Units

This sequence diagram depicts what happens when 10,000 clients simultaneously trigger "Buy Now". It shows the exact flow through API Gateway, Idempotency Guard, Atomic SQL Contention, Reservation Creation, and Alternative Branches (Success, Sold Out, Duplicate Request).

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer Client
    participant APIGW as API Gateway / Rate Limiter
    participant Ctrl as InventoryController
    participant IdemStore as Redis Idempotency Store
    participant AppSvc as ReservationApplicationService
    participant DB as PostgreSQL (Inventory DB)
    participant Broker as Kafka (Event Broker)

    Customer->>APIGW: POST /api/v1/reservations (Header: Idempotency-Key=KEY-123)
    APIGW->>Ctrl: Forward Validated Request
    
    %% Step 1: Idempotency Check
    Ctrl->>IdemStore: SETNX lock:KEY-123 (TTL=15min)
    alt Duplicate Request (Key already completed)
        IdemStore-->>Ctrl: Key Exists (Cached Response Data)
        Ctrl-->>Customer: 200 OK (Cached ReservationDTO)
    else Duplicate Request (Key in-flight)
        IdemStore-->>Ctrl: Lock Already Held
        Ctrl-->>Customer: 409 Conflict ("Request currently in progress")
    else New Request (Lock Acquired)
        IdemStore-->>Ctrl: Lock OK (Acquired)
        
        %% Step 2: Atomic DB Decrement
        Ctrl->>AppSvc: createReservation(productId, qty=1, userId)
        AppSvc->>DB: UPDATE inventory SET available_quantity = available_quantity - 1, reserved_quantity = reserved_quantity + 1 WHERE product_id = 'PROD-100' AND available_quantity >= 1
        
        alt Success (Rows Affected == 1, Units 1 to 100)
            DB-->>AppSvc: 1 Row Updated
            AppSvc->>DB: INSERT INTO inventory_reservations (id, product_id, status='RESERVED', expires_at=NOW()+10min)
            DB-->>AppSvc: Reservation Record Saved
            
            AppSvc->>Broker: Publish "InventoryReservedEvent" (Topic: inventory.events)
            AppSvc->>IdemStore: Store Completed Result(KEY-123, ReservationDTO)
            AppSvc-->>Ctrl: ReservationResult(SUCCESS, ReservationDTO)
            Ctrl-->>Customer: 201 Created { reservationId: "RES-999", expiresAt: "10:10:00Z" }
            
        else Sold Out (Rows Affected == 0, 101st to 10,000th Request)
            DB-->>AppSvc: 0 Rows Updated (Stock Exhausted)
            AppSvc->>IdemStore: Store Completed Result(KEY-123, OutOfStockDTO)
            AppSvc->>Broker: Publish "InventorySoldOutEvent" (Topic: inventory.events)
            AppSvc-->>Ctrl: ReservationResult(SOLD_OUT)
            Ctrl-->>Customer: 422 Unprocessable Entity { error: "SOLD_OUT", message: "Item is out of stock" }
        end
    end
```

---

## 2. Key Decision Points & Invariants Verified

1. **Deterministic Concurrency Serialization:**
   - The database engine serializes write locks on the single `inventory` row for `PROD-100`.
   - The conditional predicate `AND available_quantity >= 1` is evaluated inside the engine's row lock.
   - Exactly **100 requests** receive `rows_affected = 1` and proceed to create reservations.
   - The remaining **9,900 requests** receive `rows_affected = 0` and are immediately returned as Sold Out without data corruption.

2. **Idempotency Protection:**
   - If a customer double-clicks "Buy Now" or the network drops the first response, the second request encounters `SETNX lock:KEY-123` $\rightarrow$ returns existing result without decrementing inventory twice.

3. **Temporary Hold Security:**
   - Active reservations are stamped with `expires_at = NOW() + 10min`. If not confirmed by payment, the `ReservationExpiryScheduler` safely returns the unit to `available_quantity`.
