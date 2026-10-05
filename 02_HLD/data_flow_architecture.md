# SALESTORM 2026 | High-Level Data Flow & Service Integration Architecture

## 1. End-to-End System Data Flow

This document details the cross-service data flow, transactional boundaries, and event pipelines connecting Member 1's High-Level Architecture with Member 3's persistence, API, and event contracts.

```mermaid
sequenceDiagram
    autonumber
    actor Customer
    participant Edge as Edge Gateway / WAF
    participant Redis as Redis In-Memory Gate
    participant InvSvc as Inventory Service
    participant PaySvc as Payment Service
    participant Gateway as External Payment Gateway
    participant Broker as Durable Message Broker (SQS)
    participant OrdSvc as Order Service
    participant ShipSvc as Shipment Service

    Customer->>Edge: POST /api/v1/reservations [Idempotency-Key]
    Edge->>Redis: Atomic Lua Pre-Allocation Check
    alt Stock Available in Redis
        Redis-->>Edge: Token Granted
        Edge->>InvSvc: POST /reservations
        InvSvc->>InvSvc: Atomic SQL: UPDATE inventory SET available = available - 1 WHERE available >= 1
        InvSvc-->>Edge: Reservation Created (Status: RESERVED, TTL: 5m)
        Edge-->>Customer: HTTP 201 Created [reservation_id]
    else Out of Stock
        Redis-->>Edge: Rejection (-1)
        Edge-->>Customer: HTTP 409 Conflict (Out of Stock)
    end

    Customer->>Edge: POST /api/v1/payments [payment_token, reservation_id]
    Edge->>PaySvc: Initiate Payment
    PaySvc->>Gateway: Server-to-Server Charge Authorization
    Gateway-->>PaySvc: Charge Approved [provider_tx_id]
    PaySvc->>PaySvc: DB TX: Insert payment (SUCCEEDED) + Insert Outbox (PaymentSucceeded)
    PaySvc-->>Edge: Payment Approved
    Edge-->>Customer: HTTP 201 Created

    PaySvc->>Broker: Dispatch PaymentSucceeded Event (via Outbox Relay)
    
    Note over Broker,OrdSvc: If Order Service is OFFLINE (e.g. 30s outage),<br/>messages buffer durably in broker queue!
    
    Broker->>OrdSvc: Deliver PaymentSucceeded Message
    OrdSvc->>OrdSvc: Idempotency Check + DB TX: Insert order & items, Mark reservation CONFIRMED
    OrdSvc->>Broker: Acknowledge Message (ACK)
    OrdSvc->>Broker: Emit OrderConfirmed Event
    Broker->>ShipSvc: Deliver OrderConfirmed
    ShipSvc->>ShipSvc: Create Shipment & Dispatch Tracking
```

---

## 2. Bounded Context Integration Contract

| Source Context | Target Context | Integration Pattern | Data Passed | Failure Handling |
| :--- | :--- | :--- | :--- | :--- |
| **Ingress Gateway** | **Inventory Service** | Synchronous REST | `product_id`, `quantity`, `idempotency_key` | Fail-fast with HTTP 409 Out of Stock. |
| **Checkout Frontend** | **Payment Service** | Synchronous REST | `reservation_id`, `token`, `amount` | Circuit breaker tripped on gateway timeout. |
| **Payment Service** | **Order Service** | Asynchronous Event (`PaymentSucceeded`) | `payment_id`, `reservation_id`, `amount`, `customer_id` | Buffered in durable queue; retried with exponential backoff. |
| **Order Service** | **Inventory Service** | Asynchronous Event (`OrderConfirmed`) | `reservation_id`, `product_id`, `quantity` | Converts held stock to permanently sold. |
| **Payment Service** | **Inventory Service** | Asynchronous Event (`PaymentFailed`) | `reservation_id`, `reason` | Releases held reservation back to available inventory. |
