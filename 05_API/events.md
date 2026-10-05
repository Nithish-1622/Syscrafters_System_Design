# SALESTORM 2026 | Asynchronous Event & Command Contracts

## 1. Commands vs Events: The Fundamental Distinction

In event-driven architectures, conflating commands and events causes severe coupling and architectural erosion:

| Concept | Semantics | Intent | Coupling | Example |
| :--- | :--- | :--- | :--- | :--- |
| **COMMAND** | "Please perform this action." | Directed to exactly **one** handler. Can be rejected if validation fails. | Direct intent coupling. | `InitiatePayment`, `ReleaseReservation` |
| **EVENT** | "This business fact has occurred." | Broadcast to **zero or more** subscribers. Cannot be rejected (the past cannot be undone). | Decoupled; subscribers react autonomously. | `PaymentSucceeded`, `ReservationExpired` |

---

## 2. Event Envelope Standard: CloudEvents 1.0 Compliant

All asynchronous messages across SALESTORM comply with the CNCF **CloudEvents v1.0** JSON specification.

### Canonical Envelope Schema:
```json
{
  "specversion": "1.0",
  "id": "uuid-v4 (Unique event ID for deduplication)",
  "source": "/services/payment-service",
  "type": "io.salestorm.payment.succeeded",
  "datacontenttype": "application/json",
  "time": "2026-10-05T10:40:06Z",
  "correlationid": "c7a40b92-8051-4e78-9e66-1d120a1f29cb",
  "data": { ... }
}
```

---

## 3. Complete Domain Event Catalog

### 3.1 Event: `ReservationCreated`
- **Producer**: Inventory & Reservation Service
- **Consumers**: Notification Service, Analytics
- **Payload (`data`)**:
  ```json
  {
    "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
    "customer_id": "4b917c0a-0982-4211-8891-9e283012bb01",
    "product_id": "550e8400-e29b-41d4-a716-446655440000",
    "quantity": 1,
    "expires_at": "2026-10-05T10:45:00Z"
  }
  ```

### 3.2 Event: `ReservationReleased`
- **Producer**: Inventory & Reservation Service (or Expiry Reaper)
- **Consumers**: Notification Service, Analytics
- **Reason**: Cart abandonment, user cancellation, or payment decline.
- **Payload (`data`)**:
  ```json
  {
    "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
    "inventory_id": "inv-001",
    "quantity_restored": 1,
    "reason": "PAYMENT_FAILED"
  }
  ```

### 3.3 Event: `PaymentSucceeded` (CRITICAL EVENT)
- **Producer**: Payment Service (via Transactional Outbox)
- **Consumers**: Order Service (Creates Order), Notification Service
- **Payload (`data`)**:
  ```json
  {
    "payment_id": "b901726a-992a-4318-8f81-7c98012b1a89",
    "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
    "customer_id": "4b917c0a-0982-4211-8891-9e283012bb01",
    "amount": 499.00,
    "currency": "USD",
    "provider": "STRIPE",
    "provider_transaction_id": "ch_3N4x9kLjd012",
    "settled_at": "2026-10-05T10:40:05Z"
  }
  ```

### 3.4 Event: `PaymentFailed`
- **Producer**: Payment Service
- **Consumers**: Inventory Service (Triggers Compensating Release), Notification Service
- **Payload (`data`)**:
  ```json
  {
    "payment_id": "b901726a-992a-4318-8f81-7c98012b1a89",
    "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
    "customer_id": "4b917c0a-0982-4211-8891-9e283012bb01",
    "decline_code": "INSUFFICIENT_FUNDS"
  }
  ```

### 3.5 Event: `OrderConfirmed`
- **Producer**: Order Service
- **Consumers**: Inventory Service (Transitions `reserved_quantity` to `sold_quantity`), Shipment Service, Notification Service
- **Payload (`data`)**:
  ```json
  {
    "order_id": "e08471b2-2971-482a-bc91-29174092bba1",
    "order_number": "ORD-20261005-9821",
    "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
    "customer_id": "4b917c0a-0982-4211-8891-9e283012bb01",
    "items": [
      { "product_id": "550e8400-...", "quantity": 1, "unit_price": 499.00 }
    ],
    "total_amount": 499.00,
    "confirmed_at": "2026-10-05T10:40:10Z"
  }
  ```

---

## 4. Message Reliability & Poison Message Strategy

```
[ Message Broker Topic ]
           │
           ▼
┌───────────────────────────────┐
│ Consumer Worker               │
│ - Reads message               │
│ - Idempotency Check           │
└───────────────────────────────┘
           │
      ┌────┴────────────────┐
   Success               Exception
      │                     │
      ▼                     ▼
[ Acknowledge ACK ]    ┌─────────────────────────────────┐
                       │ Retry Worker (Exponential       │
                       │ Backoff + Full Jitter)          │
                       │ Attempts: 1, 2, 3               │
                       └─────────────────────────────────┘
                                    │
                               Exhausted (3 Retries)
                                    ▼
                       ┌─────────────────────────────────┐
                       │ Dead-Letter Queue (DLQ)         │
                       │ + P1 Prometheus Alert           │
                       │ + Manual / Scripted Replay Tool │
                       └─────────────────────────────────┘
```

1. **At-Least-Once Delivery**: Network partitions or worker crashes may cause messages to be re-delivered. Consumers guarantee idempotency using the message `id`.
2. **Exponential Backoff**: Transient errors are retried with delays: $t = \min(60, 2^{\text{attempt}} \times 1\text{s}) \times \text{rand}(0, 1)$.
3. **Dead Letter Queue (DLQ)**: After 3 failed attempts, poison messages are diverted to a designated DLQ topic with original error metadata preserved for offline inspection.
