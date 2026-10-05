# SALESTORM 2026 | Observability Metrics Architecture (Prometheus Specification)

## 1. Metrics Framework: 4 Golden Signals & RED Method

To monitor system health across the 500,000 req/sec flash-sale peak, SALESTORM defines Prometheus-compatible metrics organized around the **Four Golden Signals** (Latency, Traffic, Errors, Saturation) and the **RED Method** (Rate, Errors, Duration).

```
                      ┌──────────────────────────────────────────────┐
                      │            THE 4 GOLDEN SIGNALS              │
                      ├──────────────────┬───────────────────────────┤
                      │ 1. TRAFFIC       │ Request Rate (req/sec)    │
                      │ 2. LATENCY       │ p50, p95, p99 Latency     │
                      │ 3. ERRORS        │ 4xx, 5xx, Out-of-Stock    │
                      │ 4. SATURATION    │ DB Pools, CPU, DLQ Depth  │
                      └──────────────────┴───────────────────────────┘
```

---

## 2. Authoritative Metrics Catalog

### 2.1 Ingress & Edge Metrics
| Metric Name | Type | Labels | Description & Purpose |
| :--- | :--- | :--- | :--- |
| `salestorm_http_requests_total` | Counter | `method`, `endpoint`, `status` | Request rate; tracks traffic surges up to 500k req/sec. |
| `salestorm_http_request_duration_seconds`| Histogram | `method`, `endpoint` | End-to-end API response time; captures p95 and p99 SLA. |
| `salestorm_rate_limit_rejections_total` | Counter | `endpoint`, `tier` | Rate-limited requests; tracks bot or abusive traffic drops. |

---

### 2.2 Inventory & Reservation Metrics
| Metric Name | Type | Labels | Description & Purpose |
| :--- | :--- | :--- | :--- |
| `salestorm_inventory_available_gauge` | Gauge | `product_id` | Real-time available units. Critical check for zero oversell. |
| `salestorm_inventory_reserved_gauge` | Gauge | `product_id` | Currently held units awaiting payment completion. |
| `salestorm_inventory_sold_gauge` | Gauge | `product_id` | Final confirmed purchases; must never exceed initial stock. |
| `salestorm_reservation_requests_total`| Counter | `product_id`, `outcome` | `outcome`: `SUCCESS`, `OUT_OF_STOCK`, `IN_FLIGHT_CONFLICT`. |
| `salestorm_reservation_expired_total` | Counter | `product_id` | Count of reservations expired and returned to available stock. |

---

### 2.3 Payment & Settlement Metrics
| Metric Name | Type | Labels | Description & Purpose |
| :--- | :--- | :--- | :--- |
| `salestorm_payment_attempts_total` | Counter | `provider`, `status` | `status`: `SUCCESS`, `DECLINED`, `TIMEOUT`, `ERROR`. |
| `salestorm_payment_latency_seconds` | Histogram | `provider` | External gateway call duration; triggers circuit breaker. |
| `salestorm_payment_reconciliation_total`| Counter | `reason` | Payments flagged for offline operator/script reconciliation. |

---

### 2.4 Asynchronous Messaging & Fulfillment Metrics
| Metric Name | Type | Labels | Description & Purpose |
| :--- | :--- | :--- | :--- |
| `salestorm_queue_depth_messages` | Gauge | `queue_name` | Backlog in SQS/Kafka. Spikes indicate consumer slowdown. |
| `salestorm_dlq_messages_total` | Counter | `queue_name` | Poison messages in Dead-Letter Queue. Must trigger P1 alert! |
| `salestorm_consumer_lag_seconds` | Gauge | `consumer_group` | Time delay between event publication and consumption. |

---

### 2.5 Reliability & Infrastructure Saturation Metrics
| Metric Name | Type | Labels | Description & Purpose |
| :--- | :--- | :--- | :--- |
| `salestorm_db_connection_pool_active` | Gauge | `service`, `pool` | Active DB connections. Detects connection exhaustion. |
| `salestorm_circuit_breaker_state` | Gauge | `service`, `dependency` | `0` = CLOSED (Healthy), `1` = HALF_OPEN, `2` = OPEN (Tripped). |
| `salestorm_idempotency_cache_hits_total`| Counter | `endpoint` | Replayed duplicate requests; validates safe retries. |
