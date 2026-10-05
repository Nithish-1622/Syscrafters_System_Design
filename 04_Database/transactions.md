# SALESTORM 2026 | Transaction Boundaries & Consistency Architecture

## 1. Architectural Strategy: Avoiding Distributed Two-Phase Commit (2PC)

A frequent pitfall in distributed systems design is attempting to wrap cross-service operations (Inventory Reservation + Payment Processing + Order Creation) in a single distributed database transaction (2PC).

### Why 2PC is Rejected for SALESTORM:
1. **Extreme Lock Holding Duration**: Payment gateway network calls take between 500ms to 5,000ms. Holding database locks on inventory rows while waiting for a bank gateway locks out other concurrent shoppers, destroying throughput.
2. **Coordinator Single Point of Failure**: If the transaction coordinator crashes during the prepare phase, distributed participants remain locked indefinitely.
3. **Availability Collapse**: By the CAP theorem, distributed transactions sacrifice availability to maintain consistency across partitions ($A \to 0$ as $N \to \infty$).

### SALESTORM Solution: Autonomous Local ACID + Choreographed Saga with Transactional Outbox
Every service maintains **strict local ACID transactions** within its bounded database. Cross-boundary coordination is achieved via **asynchronous domain events** emitted through a **Transactional Outbox**.

```
[ Checkout Request ]
         │
         ▼
┌───────────────────────────────────────────────┐
│ LOCAL TX 1: INVENTORY SERVICE                │
│ 1. Atomic decrement `available_quantity`      │
│ 2. Increment `reserved_quantity`              │
│ 3. Insert `inventory_reservations`            │
│ 4. Insert Outbox `ReservationCreated`         │
│ 5. COMMIT (Duration: < 3ms)                   │
└───────────────────────────────────────────────┘
         │
         ▼ (Async Event / Client Handoff)
┌───────────────────────────────────────────────┐
│ LOCAL TX 2: PAYMENT SERVICE                  │
│ 1. Initiate charge with external gateway      │
│ 2. On Webhook: Insert/Update `payments`       │
│ 3. Insert Outbox `PaymentSucceeded`           │
│ 4. COMMIT (Duration: < 5ms)                   │
└───────────────────────────────────────────────┘
         │
         ▼ (Async Message Broker: SQS / Kafka)
┌───────────────────────────────────────────────┐
│ LOCAL TX 3: ORDER SERVICE                     │
│ 1. Idempotency deduplication check            │
│ 2. Insert `orders` and `order_items`          │
│ 3. Update reservation status to `CONFIRMED`   │
│ 4. Insert Outbox `OrderConfirmed`             │
│ 5. COMMIT (Duration: < 4ms)                   │
└───────────────────────────────────────────────┘
```

---

## 2. Local ACID Isolation Levels

We configure the database isolation level to **`READ COMMITTED`** paired with **Atomic Conditional SQL Updates**.

### Why Not `SERIALIZABLE`?
Under 10,000 concurrent requests competing for 100 items on a single inventory row, `SERIALIZABLE` isolation generates an overwhelming storm of serialization failures (PostgreSQL error `40001: could not serialize access due to read/write dependencies among transactions`). The application would be forced to retry hundreds of thousands of transactions, causing CPU thrashing and connection pool exhaustion.

### Why `READ COMMITTED` + Atomic Conditional Updates Works:
In `READ COMMITTED`, every row-level `UPDATE ... WHERE available_quantity >= :qty` acquires an exclusive row write lock. Subsequent updates queue sequentially. When each update obtains the lock, it re-evaluates the `WHERE` clause against the newly committed row state. If `available_quantity` has dropped below the requested quantity, 0 rows are updated, and the transaction cleanly rolls back without serialization aborts!

---

## 3. Transaction Boundary Specifications

### 3.1 Reservation Transaction (Inventory Service)
- **Initiator**: Checkout API (`POST /api/v1/reservations`)
- **Isolation Level**: `READ COMMITTED`
- **Steps**:
  ```sql
  BEGIN;
  
  -- 1. Check idempotency record
  INSERT INTO idempotency_records (idempotency_key, scope, request_hash, status, expires_at)
  VALUES (:idempotencyKey, 'RESERVATION', :hash, 'IN_PROGRESS', NOW() + INTERVAL '24 hours');

  -- 2. Atomic conditional stock reservation
  UPDATE inventory
  SET available_quantity = available_quantity - :qty,
      reserved_quantity  = reserved_quantity + :qty,
      version            = version + 1,
      updated_at         = CURRENT_TIMESTAMP
  WHERE product_id = :productId 
    AND available_quantity >= :qty
  RETURNING inventory_id;

  -- If 0 rows updated -> RAISE EXCEPTION 'OUT_OF_STOCK';

  -- 3. Create reservation record
  INSERT INTO inventory_reservations (
      reservation_id, inventory_id, customer_id, quantity, 
      status, idempotency_key, expires_at
  ) VALUES (
      :reservationId, :inventoryId, :customerId, :qty, 
      'RESERVED', :idempotencyKey, NOW() + INTERVAL '5 minutes'
  );

  -- 4. Emit Transactional Outbox Event
  INSERT INTO transactional_outbox (
      aggregate_type, aggregate_id, event_type, payload, correlation_id
  ) VALUES (
      'RESERVATION', :reservationId, 'ReservationCreated', :payloadJson, :correlationId
  );

  -- 5. Mark idempotency complete
  UPDATE idempotency_records 
  SET status = 'COMPLETED', response_code = 201, response_body = :responseJson
  WHERE idempotency_key = :idempotencyKey;

  COMMIT;
  ```
- **Guarantees**: Either the reservation is recorded, stock decremented, and outbox event staged, or nothing changes.

---

### 3.2 Payment Webhook Transaction (Payment Service)
- **Initiator**: Payment Provider Callback (`POST /api/v1/payments/webhook`)
- **Steps**:
  ```sql
  BEGIN;

  -- 1. Deduplicate provider transaction
  INSERT INTO payments (
      payment_id, reservation_id, customer_id, amount, currency, 
      payment_method, provider, provider_transaction_id, idempotency_key, status
  ) VALUES (
      :paymentId, :reservationId, :customerId, :amount, :currency, 
      :method, :provider, :providerTxId, :idempotencyKey, 'SUCCEEDED'
  )
  ON CONFLICT (provider_transaction_id) DO NOTHING;

  -- If conflict occurred, this is a duplicate webhook -> COMMIT and return 200 OK

  -- 2. Stage Outbox Event for Order Fulfillment
  INSERT INTO transactional_outbox (
      aggregate_type, aggregate_id, event_type, payload, correlation_id
  ) VALUES (
      'PAYMENT', :paymentId, 'PaymentSucceeded', :payloadJson, :correlationId
  );

  COMMIT;
  ```

---

### 3.3 Order Creation & Confirmation Transaction (Order Service)
- **Initiator**: Message Consumer consuming `PaymentSucceeded`
- **Steps**:
  ```sql
  BEGIN;

  -- 1. Check message deduplication
  INSERT INTO idempotency_records (idempotency_key, scope, request_hash, status, expires_at)
  VALUES (:eventId, 'EVENT_CONSUMER', :hash, 'IN_PROGRESS', NOW() + INTERVAL '7 days');

  -- 2. Insert Order
  INSERT INTO orders (
      order_id, order_number, customer_id, reservation_id, 
      status, total_amount, currency, shipping_address_json, billing_address_json
  ) VALUES (
      :orderId, :orderNumber, :customerId, :reservationId, 
      'CONFIRMED', :amount, :currency, :shippingJson, :billingJson
  );

  -- 3. Insert Order Items
  INSERT INTO order_items (order_item_id, order_id, product_id, quantity, unit_price, total_price)
  VALUES (:itemId, :orderId, :productId, :qty, :unitPrice, :totalPrice);

  -- 4. Mark reservation as CONFIRMED / SOLD
  UPDATE inventory_reservations
  SET status = 'CONFIRMED', updated_at = CURRENT_TIMESTAMP
  WHERE reservation_id = :reservationId AND status = 'RESERVED';

  -- 5. Deduct from reserved_quantity and increment sold_quantity
  UPDATE inventory
  SET reserved_quantity = reserved_quantity - :qty,
      sold_quantity     = sold_quantity + :qty,
      updated_at        = CURRENT_TIMESTAMP
  WHERE inventory_id = :inventoryId;

  -- 6. Stage OrderConfirmed Outbox event for shipment & notification
  INSERT INTO transactional_outbox (
      aggregate_type, aggregate_id, event_type, payload, correlation_id
  ) VALUES (
      'ORDER', :orderId, 'OrderConfirmed', :orderPayloadJson, :correlationId
  );

  -- 7. Complete consumer idempotency
  UPDATE idempotency_records SET status = 'COMPLETED' WHERE idempotency_key = :eventId;

  COMMIT;
  ```

---

### 3.4 Compensating Transaction: Payment Failure / Expiry Release
- **Trigger**: Payment Gateway returns `FAILED` or Background Reaper detects `expires_at < NOW()`.
- **Steps**:
  ```sql
  BEGIN;

  -- 1. Transition reservation status
  UPDATE inventory_reservations
  SET status = 'RELEASED', updated_at = CURRENT_TIMESTAMP
  WHERE reservation_id = :reservationId 
    AND status IN ('RESERVED', 'PAYMENT_PENDING')
  RETURNING inventory_id, quantity;

  -- If row returned:
  -- 2. Return reserved stock back to available pool
  UPDATE inventory
  SET available_quantity = available_quantity + :qty,
      reserved_quantity  = reserved_quantity - :qty,
      updated_at         = CURRENT_TIMESTAMP
  WHERE inventory_id = :inventoryId;

  -- 3. Emit ReservationReleased event
  INSERT INTO transactional_outbox (
      aggregate_type, aggregate_id, event_type, payload, correlation_id
  ) VALUES (
      'RESERVATION', :reservationId, 'ReservationReleased', :releasePayload, :correlationId
  );

  COMMIT;
  ```
- **Invariance Guarantee**: If the reservation was already confirmed, the `UPDATE ... WHERE status IN ('RESERVED', 'PAYMENT_PENDING')` affects 0 rows, preventing stock duplication.
