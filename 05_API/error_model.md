# SALESTORM 2026 | Error Model Specification (RFC 7807 Compliant)

## 1. Error Design Principles

SALESTORM implements **RFC 7807 (Problem Details for HTTP APIs)**. All error responses across all microservices return `Content-Type: application/problem+json` with consistent, machine-readable domain error codes and distributed correlation IDs.

### Security Non-Negotiables:
1. **Zero Stack Trace Leaks**: Internal stack traces, raw SQL queries, database hostnames, or library versions are NEVER returned in API error payloads.
2. **Correlation Tracking**: Every error payload includes a `correlation_id` matching server-side structured logs, allowing support and SREs to investigate without exposing secrets to callers.

---

## 2. Standard Schema & Domain Error Registry

### Schema Definition:
```json
{
  "type": "string (URI referencing public error documentation)",
  "title": "string (Human-readable summary of problem)",
  "status": "integer (HTTP status code)",
  "code": "string (Stable machine-readable error code)",
  "detail": "string (Human-readable explanation specific to this occurrence)",
  "instance": "string (URI of resource request)",
  "correlation_id": "string (Distributed trace/request ID)",
  "invalid_params": [
    {
      "name": "string (Field name)",
      "reason": "string (Validation error description)"
    }
  ]
}
```

---

## 3. Authoritative Domain Error Code Catalog

| Error Code | HTTP Status | Domain | Scenario / Meaning |
| :--- | :--- | :--- | :--- |
| **`INVENTORY_OUT_OF_STOCK`** | `409 Conflict` | Inventory | Available stock is 0 or less than requested quantity. |
| **`RESERVATION_EXPIRED`** | `409 Conflict` | Reservation | Customer attempted to pay after the 5-minute TTL elapsed. |
| **`RESERVATION_ALREADY_CONFIRMED`** | `409 Conflict` | Reservation | Reservation has already been converted into an order. |
| **`IDEMPOTENCY_KEY_IN_FLIGHT`** | `409 Conflict` | Ingress | A concurrent request with this exact key is currently executing (`Retry-After: 1`). |
| **`IDEMPOTENCY_KEY_REUSE_MISMATCH`** | `422 Unprocessable`| Ingress | Key was previously used with a different request body. |
| **`PAYMENT_DECLINED`** | `400 Bad Request` | Payment | Card declined by issuing bank (insufficient funds, fraud alert). |
| **`PAYMENT_GATEWAY_TIMEOUT`** | `504 Gateway Timeout`| Payment | Payment provider did not respond within deadline (reconciliation triggered). |
| **`RATE_LIMIT_EXCEEDED`** | `429 Too Many Requests`| Gateway | Client exceeded allowed token bucket request quota. |
| **`VALIDATION_FAILED`** | `400 Bad Request` | Ingress | Input syntax invalid or bounds checks failed. |
| **`AUTHENTICATION_REQUIRED`** | `401 Unauthorized` | Auth | Missing or expired JWT token. |
| **`ACCESS_DENIED`** | `403 Forbidden` | Auth | User does not own the requested resource. |
| **`DEPENDENCY_UNAVAILABLE`** | `503 Service Unavailable`| Infrastructure| Downstream circuit breaker is OPEN. |

---

## 4. Concrete Error Response Examples

### Out of Stock Example (HTTP 409):
```json
{
  "type": "https://errors.salestorm.io/inventory/out-of-stock",
  "title": "Out of Stock",
  "status": 409,
  "code": "INVENTORY_OUT_OF_STOCK",
  "detail": "Flash sale stock for this item has been completely reserved.",
  "instance": "/api/v1/reservations",
  "correlation_id": "req-9812-4019"
}
```

### Validation Failure Example (HTTP 400):
```json
{
  "type": "https://errors.salestorm.io/validation-error",
  "title": "Validation Failed",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "detail": "The request body failed structural schema validation.",
  "instance": "/api/v1/reservations",
  "correlation_id": "req-1102-aa77",
  "invalid_params": [
    {
      "name": "quantity",
      "reason": "Must be between 1 and 2 units per customer."
    }
  ]
}
```
