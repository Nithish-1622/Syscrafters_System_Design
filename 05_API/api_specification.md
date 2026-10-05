# SALESTORM 2026 | Detailed API Specification & Contract Manual

## 1. Architectural Philosophy

The SALESTORM API follows modern RESTful engineering standards, RFC 7807 Problem Details for errors, and strict idempotency controls via the `Idempotency-Key` HTTP header. 

### Global Headers:
- **`Authorization`**: `Bearer <JWT_TOKEN>` (Required for all authenticated customer actions).
- **`Idempotency-Key`**: UUIDv4 or client-generated unique string (Mandatory on state-mutating requests: `POST /reservations`, `POST /payments`, `POST /orders`).
- **`X-Correlation-Id`**: Distributed tracing correlation token (e.g. `c7a40b92-8051-4e78-9e66-1d120a1f29cb`).
- **`Content-Type`**: `application/json`.
- **`Accept`**: `application/json`, `application/problem+json`.

---

## 2. Core Endpoint Specifications

### 2.1 Inventory & Reservation Service

#### `POST /api/v1/reservations`
- **Purpose**: Atomically claims inventory hold for 5 minutes during checkout.
- **Authentication**: Customer JWT (`BearerAuth`).
- **Authorization**: `customer` role; active account.
- **Request Headers**:
  - `Idempotency-Key: c9d784a1-02e4-4a25-8273-0db2388df632`
  - `X-Correlation-Id: req-8891-bba1`
- **Request Body**:
  ```json
  {
    "product_id": "550e8400-e29b-41d4-a716-446655440000",
    "quantity": 1
  }
  ```
- **Responses**:
  - **`201 Created`**: Reservation created successfully.
    ```json
    {
      "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
      "product_id": "550e8400-e29b-41d4-a716-446655440000",
      "quantity": 1,
      "status": "RESERVED",
      "expires_at": "2026-10-05T10:45:00Z",
      "created_at": "2026-10-05T10:40:00Z"
    }
    ```
  - **`200 OK`**: Duplicate request replayed. Returns cached identical payload.
  - **`409 Conflict` (Out of Stock)**:
    ```json
    {
      "type": "https://errors.salestorm.io/inventory/out-of-stock",
      "title": "Out of Stock",
      "status": 409,
      "code": "INVENTORY_OUT_OF_STOCK",
      "detail": "Requested product is sold out or unavailable.",
      "instance": "/api/v1/reservations",
      "correlation_id": "req-8891-bba1"
    }
    ```
  - **`409 Conflict` (Concurrent Key In-Flight)**:
    - Headers: `Retry-After: 1`
    - Detail: "A request with this idempotency key is currently processing."
  - **`422 Unprocessable Entity`**: Reused idempotency key with different payload.
  - **`429 Too Many Requests`**: Rate limit exceeded (Token bucket limit).

---

### 2.2 Payment Service

#### `POST /api/v1/payments`
- **Purpose**: Initiates a financial charge against an active reservation.
- **Request Body**:
  ```json
  {
    "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
    "amount": 499.00,
    "currency": "USD",
    "payment_method_token": "tok_1N3k09Lkd82"
  }
  ```
- **Responses**:
  - **`201 Created`**: Charge initiated.
    ```json
    {
      "payment_id": "b901726a-992a-4318-8f81-7c98012b1a89",
      "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
      "amount": 499.00,
      "currency": "USD",
      "status": "INITIATED",
      "created_at": "2026-10-05T10:40:05Z"
    }
    ```
  - **`409 Conflict`**: Reservation already paid or reservation expired.

#### `POST /api/v1/payments/webhook`
- **Purpose**: Asynchronous callback from Stripe/Adyen to confirm charge settlement.
- **Authentication**: External HMAC-SHA256 signature (`X-Signature-SHA256`).
- **Idempotency**: Handled via `provider_transaction_id` unique constraint.
- **Responses**:
  - **`200 OK`**: Webhook acknowledged and staged to Transactional Outbox.

---

### 2.3 Order Service

#### `POST /api/v1/orders`
- **Purpose**: Direct client confirmation fallback or synchronous order placement.
- **Request Body**:
  ```json
  {
    "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
    "payment_id": "b901726a-992a-4318-8f81-7c98012b1a89",
    "shipping_address": {
      "street": "100 Market St",
      "city": "San Francisco",
      "state": "CA",
      "postal_code": "94105",
      "country": "USA"
    }
  }
  ```
- **Responses**:
  - **`201 Created`**:
    ```json
    {
      "order_id": "e08471b2-2971-482a-bc91-29174092bba1",
      "order_number": "ORD-20261005-9821",
      "status": "CONFIRMED",
      "total_amount": 499.00,
      "currency": "USD",
      "created_at": "2026-10-05T10:40:10Z"
    }
    ```
  - **`409 Conflict`**: Order already confirmed for this reservation token.

#### `GET /api/v1/orders/{orderId}`
- **Purpose**: Customer queries order fulfillment status.
- **Authorization**: Ownership check (`order.customer_id == jwt.sub`).
