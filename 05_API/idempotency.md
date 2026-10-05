# SALESTORM 2026 | HTTP API Idempotency Protocol

## 1. Specification Overview

During high-concurrency flash sales, mobile clients and browsers frequently retry POST requests when network latency causes connection timeouts. Without strict API idempotency, network retries result in duplicate reservations, multiple credit card charges, and duplicate orders.

SALESTORM adopts the **IETF Draft: The Idempotency-Key HTTP Header Field**.

---

## 2. Idempotency Flow Protocol

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant Gateway as API Gateway / App
    participant IdemStore as Idempotency Store (DB/Redis)
    participant Core as Domain Service

    Client->>Gateway: POST /api/v1/reservations<br/>[Header: Idempotency-Key: uuid-1]<br/>[Body: {product_id: P1, qty: 1}]
    
    Gateway->>Gateway: Compute SHA-256 Hash of Normalized Body
    Gateway->>IdemStore: ATOMIC INSERT (key, hash, 'IN_PROGRESS', TTL 24h)
    
    alt Lock Acquired (First Time Seeing Key)
        IdemStore-->>Gateway: Lock Granted (1 row affected)
        Gateway->>Core: Execute Reservation Transaction
        Core-->>Gateway: Reservation Created (res-981)
        Gateway->>IdemStore: UPDATE SET status='COMPLETED', code=201, body={...}
        Gateway-->>Client: HTTP 201 Created [Body: {reservation_id: res-981}]
    else Key Exists: Status == 'IN_PROGRESS' (Concurrent Duplicate)
        IdemStore-->>Gateway: Key Exists (IN_PROGRESS)
        Gateway-->>Client: HTTP 409 Conflict [Retry-After: 1s, Code: IDEMPOTENCY_KEY_IN_FLIGHT]
    else Key Exists: Status == 'COMPLETED' AND Hash Matches (Safe Network Retry)
        IdemStore-->>Gateway: Key Exists (Cached Response Available)
        Gateway-->>Client: HTTP 200 OK [Cached Response Body Replayed]
    else Key Exists: Payload Hash MISMATCH (Key Misuse)
        IdemStore-->>Gateway: Key Exists (Hash differs)
        Gateway-->>Client: HTTP 422 Unprocessable Entity [Code: IDEMPOTENCY_KEY_REUSE_MISMATCH]
    end
```

---

## 3. Client Header Guidelines

1. **Header Name**: `Idempotency-Key` (Case-insensitive per HTTP/1.1 and HTTP/2).
2. **Format**: Standard UUID v4 (e.g., `8f9b2d8e-3a1b-4f9e-9d2a-1c8f3b4e5a6d`) or cryptographic random string (min 16 chars, max 128 chars).
3. **Scope**: Idempotency keys are scoped to the authenticated customer ID and target endpoint (`customer_id + method + path + key`). A customer cannot collide with another customer's key.
4. **Retention**: Keys are held for **24 hours**. Clients retrying after 24 hours are treated as issuing a new request.
