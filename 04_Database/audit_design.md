# SALESTORM 2026 | Audit Logging & Compliance Ledger Design

## 1. Compliance & Forensic Requirements

In high-concurrency e-commerce and financial transaction processing, **auditability is mandatory**. When 10,000 customers compete for 100 items, disputes will occur:
- "Why was my reservation canceled?"
- "Did you charge my card twice?"
- "Was inventory released back to the pool at the exact timestamp required?"

The `audit_logs` table serves as an **append-only, immutable forensic ledger** providing complete non-repudiation.

---

## 2. Audit Table Schema & Partitioning Strategy

```sql
CREATE TABLE audit_logs (
    audit_id BIGSERIAL,
    entity_name VARCHAR(64) NOT NULL,
    entity_id VARCHAR(128) NOT NULL,
    action VARCHAR(64) NOT NULL,
    actor VARCHAR(128) NOT NULL,
    state_before JSONB,
    state_after JSONB,
    ip_address VARCHAR(45),
    correlation_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (audit_id, created_at)
) PARTITION BY RANGE (created_at);

-- Monthly partitions for performance and zero-cost archiving
CREATE TABLE audit_logs_y2026m10 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');
```

---

## 3. High-Value Auditable Events

Every high-value domain transition MUST generate a synchronous or outbox-staged audit record:

| Domain | Action | Trigger Point | State Delta Captured |
| :--- | :--- | :--- | :--- |
| **Inventory** | `STOCK_RESERVED` | Successful hold creation | `{available: 100, reserved: 0} -> {available: 99, reserved: 1}` |
| **Inventory** | `STOCK_RELEASED` | Timeout or payment failure | `{available: 0, reserved: 100} -> {available: 1, reserved: 99}` |
| **Inventory** | `STOCK_SOLD` | Order confirmation | `{reserved: 1, sold: 99} -> {reserved: 0, sold: 100}` |
| **Payment** | `PAYMENT_INITIATED` | Checkout submission | Payment intent record created. |
| **Payment** | `PAYMENT_SUCCEEDED` | Gateway webhook callback | Provider TX ID, amount, settled timestamp. |
| **Payment** | `PAYMENT_FAILED` | Gateway decline callback | Provider error code, decline reason. |
| **Order** | `ORDER_CONFIRMED` | Async event processing | Final order snapshot and line items. |
| **Order** | `ORDER_CANCELLED` | Customer or admin action | Cancellation reason and refund trigger. |

---

## 4. Privacy & PCI-DSS SAQ-A Data Protection Rules

To remain compliant with **PCI-DSS** and **GDPR**:
1. **Zero Cardholder Storage**: The audit log NEVER stores Primary Account Numbers (PAN), CVV/CVC codes, card expiration dates, or bank PINs.
2. **PII Masking**: Customer emails and phone numbers in audit payloads are partially masked (`j***@example.com`).
3. **Database Permissions**: The application database user has `INSERT` and `SELECT` privileges only. `UPDATE` and `DELETE` privileges are strictly revoked to prevent tampering.
