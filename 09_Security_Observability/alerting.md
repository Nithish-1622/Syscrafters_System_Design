# SALESTORM 2026 | Alerting Rules, SLOs & Incident Runbooks

## 1. Service Level Objectives (SLOs) & Service Level Indicators (SLIs)

| Service Boundary | SLI (Metric) | SLO Target | Error Budget (Monthly) |
| :--- | :--- | :--- | :--- |
| **Inventory Reservation**| Latency: p99 duration for `POST /reservations` | < 100 ms | 1% of requests |
| **Inventory Invariant** | Integrity: Overselling occurrences | **0 (Zero Tolerance)** | 0% |
| **Checkout API** | Availability: Successful HTTP responses (excl. 409 Out of Stock)| >= 99.95% | 21.6 minutes downtime |
| **Payment Pipeline** | Reliability: Webhook-to-Order lag | < 5.0 seconds | 0.1% of transactions |
| **Order Consumer** | DLQ Ingestion: Poison messages routed to DLQ | 0 unhandled | Immediate P1 triage |

---

## 2. Authoritative Prometheus Alert Rules

```yaml
groups:
  - name: salestorm_critical_alerts
    rules:
      # P1 CRITICAL: INVENTORY OVERSELLING DETECTED
      - alert: InventoryOversellingDetected
        expr: salestorm_inventory_available_gauge < 0 or (salestorm_inventory_sold_gauge + salestorm_inventory_reserved_gauge > salestorm_inventory_total_gauge)
        for: 0m
        labels:
          severity: P1-CRITICAL
        annotations:
          summary: "CRITICAL: Physical inventory balance invariant violated!"
          description: "Inventory for product {{ $labels.product_id }} has oversold. Immediate escalation required."
          runbook_url: "https://wiki.salestorm.io/ops/runbooks/inventory-oversold"

      # P1 CRITICAL: DEAD LETTER QUEUE (DLQ) GROWTH
      - alert: DeadLetterQueueNotEmpty
        expr: increase(salestorm_dlq_messages_total[1m]) > 0
        for: 1m
        labels:
          severity: P1-CRITICAL
        annotations:
          summary: "Messages are failing into the Dead Letter Queue"
          description: "Queue {{ $labels.queue_name }} has received {{ $value }} poison messages."
          runbook_url: "https://wiki.salestorm.io/ops/runbooks/dlq-triage"

      # P1 CRITICAL: PAYMENT CIRCUIT BREAKER TRIPPED
      - alert: PaymentGatewayCircuitBreakerOpen
        expr: salestorm_circuit_breaker_state{dependency="payment_gateway"} == 2
        for: 30s
        labels:
          severity: P1-CRITICAL
        annotations:
          summary: "Payment Gateway Circuit Breaker is OPEN"
          description: "External payment provider is failing. Traffic is being shed to prevent cascade."
          runbook_url: "https://wiki.salestorm.io/ops/runbooks/payment-circuit-breaker"

      # P2 HIGH: DATABASE CONNECTION POOL SATURATION
      - alert: DatabasePoolExhaustionWarning
        expr: (salestorm_db_connection_pool_active / salestorm_db_connection_pool_max) > 0.85
        for: 2m
        labels:
          severity: P2-HIGH
        annotations:
          summary: "Database connection pool usage above 85%"
          description: "Service {{ $labels.service }} is nearing connection exhaustion."
          runbook_url: "https://wiki.salestorm.io/ops/runbooks/db-pool-scaling"

      # P2 HIGH: PAYMENT GATEWAY TIMEOUT SPIKE
      - alert: PaymentGatewayTimeoutSpike
        expr: rate(salestorm_payment_attempts_total{status="TIMEOUT"}[5m]) / rate(salestorm_payment_attempts_total[5m]) > 0.05
        for: 2m
        labels:
          severity: P2-HIGH
        annotations:
          summary: "Payment timeout rate exceeds 5%"
          description: "External payment gateway is experiencing elevated latency."
```

---

## 3. Incident Response Runbooks

### Runbook 1: `InventoryOversellingDetected` (P1)
1. **Immediate Action**: Trigger Edge WAF kill-switch to block all incoming `POST /api/v1/reservations` calls for the affected product.
2. **Execute Database Forensic Audit**:
   ```sql
   SELECT * FROM inventory WHERE product_id = :id;
   SELECT * FROM inventory_reservations WHERE inventory_id = :invId AND status IN ('RESERVED', 'CONFIRMED');
   ```
3. **Trace Audit Log**: Identify anomalous transactions via `correlation_id` in `audit_logs`.
4. **Resolution**: If an application bug bypassed guards, identify the latest reservation, mark as canceled, and issue immediate customer refund notification.

### Runbook 2: `DeadLetterQueueNotEmpty` (P1)
1. Inspect payload of the DLQ message using the administrative CLI:
   `salestorm-cli dlq inspect --queue order-fulfillment-dlq --limit 1`
2. Determine error cause: schema mismatch, poison payload, or downstream DB lock timeout.
3. If downstream transient issue has recovered, execute replay script:
   `salestorm-cli dlq replay --queue order-fulfillment-dlq --all`
