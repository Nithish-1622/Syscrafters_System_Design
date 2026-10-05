# SALESTORM 2026 | High-Performance Structured Logging Specification

## 1. JSON Logging Format & Standard Fields

All microservices emit logs in newline-delimited JSON (`ndjson`) to `stdout`. Logs are collected by fluentbit / cloud agents and ingested into centralized log aggregators (e.g., OpenSearch / AWS CloudWatch).

### Mandatory Canonical JSON Log Schema:
```json
{
  "timestamp": "2026-10-05T10:40:02.185Z",
  "service": "inventory-service",
  "level": "INFO",
  "message": "Inventory reservation confirmed",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "correlation_id": "c7a40b92-8051-4e78-9e66-1d120a1f29cb",
  "customer_id": "4b917c0a-0982-4211-8891-9e283012bb01",
  "reservation_id": "71a82f34-1189-498c-8c01-8b273891c944",
  "product_id": "550e8400-e29b-41d4-a716-446655440000",
  "available_quantity": 99,
  "reserved_quantity": 1,
  "duration_ms": 2.41,
  "status_code": 201
}
```

---

## 2. Log Levels & Usage Guidelines

| Level | When to Use | Production Sampling |
| :--- | :--- | :--- |
| **`DEBUG`** | Detailed payload inspection, local development only. | 0% in Production (Disabled). |
| **`INFO`** | State transitions: `ReservationCreated`, `PaymentSucceeded`, `OrderConfirmed`. | 100% of Mutations; 1% of Catalog Reads. |
| **`WARN`** | Recoverable anomalies: Rate limit hits, out of stock, reservation expiry, idempotent retry. | 100% Logged. |
| **`ERROR`** | Unrecoverable failures: DB connection loss, payment gateway timeout, DLQ message drops. | 100% Logged (Triggers alerts). |
| **`FATAL`** | Service crash, startup configuration failure, unhandled panic. | 100% Logged. |

---

## 3. Automated Redaction Filter (Sanitization Rules)

Log appenders intercept all dictionary keys before serialization:
- Keys matching `(?i)(password|secret|token|authorization|pan|cvv|card_number)` are replaced with `[REDACTED]`.
- Email addresses are masked to `u***@domain.com`.
- Full request bodies are NEVER logged on public ingress endpoints.
