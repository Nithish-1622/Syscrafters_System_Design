# SALESTORM 2026 | Security Audit Logging & Non-Repudiation

## 1. Scope & Forensic Mandate

Security audit logs record **who did what, when, from where, and with what outcome**. Unlike general operational logs, audit logs are legally binding forensic records used during fraud investigations, PCI compliance reviews, and financial reconciliations.

---

## 2. Audit Record Data Contract

Every auditable action is serialized according to this canonical schema:

```json
{
  "audit_id": 9812401,
  "timestamp": "2026-10-05T10:40:02.182Z",
  "actor": {
    "type": "CUSTOMER",
    "id": "4b917c0a-0982-4211-8891-9e283012bb01",
    "ip_address": "198.51.100.42",
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
  },
  "action": "INVENTORY_RESERVED",
  "entity": {
    "type": "INVENTORY_RESERVATION",
    "id": "71a82f34-1189-498c-8c01-8b273891c944"
  },
  "correlation_id": "c7a40b92-8051-4e78-9e66-1d120a1f29cb",
  "state_delta": {
    "before": { "available_quantity": 100, "reserved_quantity": 0 },
    "after": { "available_quantity": 99, "reserved_quantity": 1 }
  },
  "result": "SUCCESS"
}
```

---

## 3. PII & Sensitive Data Redaction Rules

Audit logs are strictly filtered before persistence:
1. **Financial Scrubbing**: Card numbers, CVVs, and bank account numbers are rejected at the logging interceptor. If detected, they are replaced with `[REDACTED_PCI]`.
2. **Email Masking**: User emails are masked to show only first char and domain (`j***@example.com`).
3. **Password / Token Exclusion**: Authorization headers and passwords are stripped automatically.

---

## 4. Tamper Resistance & Retention Policy

1. **WORM Storage**: Audit logs are streamed to append-only, Write Once Read Many (WORM) cloud object storage with Object Lock enabled in Compliance Mode.
2. **Retention Rules**:
   - Financial & Payment Audit Records: **7 Years** (Regulatory requirement).
   - Inventory Reservation Logs: **1 Year**.
   - Admin Access Trails: **3 Years**.
