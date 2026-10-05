# SALESTORM 2026 | Payment Security & PCI-DSS SAQ-A Compliance

## 1. Compliance Architecture: PCI-DSS SAQ-A Scope

The most secure payment design is one where **sensitive cardholder data never touches the merchant's servers**. SALESTORM implements the **PCI-DSS Self-Assessment Questionnaire A (SAQ-A)** model.

```
[ Customer Browser / Mobile App ]
      │
      ├── 1. Card data entered inside Payment Provider IFRAME (Stripe/Adyen)
      │      (PAN, CVV, Expiry transmitted DIRECTLY to Gateway)
      │
      ▼
[ Payment Gateway Provider ]
      │
      ├── 2. Validates card & returns single-use token: `tok_1N3k09Lkd82`
      │
      ▼
[ Customer App sends `tok_...` to SALESTORM Backend ]
      │
      ▼
[ SALESTORM Payment Service ]
      │
      └── 3. Charges token via Gateway Server-to-Server API
```

---

## 2. Data Storage Invariants (What Is Stored vs What Is NEVER Stored)

| Data Category | Specific Attribute | Storage Policy | Justification |
| :--- | :--- | :--- | :--- |
| **Cardholder Data (CHD)** | Primary Account Number (PAN) | **NEVER STORED** | Violates SAQ-A; severe regulatory liability. |
| **Sensitive Auth Data (SAD)** | CVV / CVC / Security Code | **NEVER STORED** | Strictly prohibited by PCI-DSS Rule 3.2. |
| **Sensitive Auth Data (SAD)** | PIN / PIN Blocks | **NEVER STORED** | Strictly prohibited by PCI-DSS Rule 3.2. |
| **Payment Token** | `payment_method_token` | Ephemeral (in-memory only)| Used once to trigger charge, then discarded. |
| **Provider Reference** | `provider_transaction_id` | **STORED** (Indexed) | Idempotent reconciliation and audit trail. |
| **Masked Metadata** | Card Brand (`VISA`), Last 4 digits | **STORED** | Customer receipt & order history display. |

---

## 3. Webhook Integrity & Replay Mitigation

Payment gateway callbacks (`POST /api/v1/payments/webhook`) communicate financial settlement asynchronously.

### Security Defenses:
1. **IP Whitelisting**: Edge gateway rejects callbacks outside published payment gateway CIDR blocks.
2. **HMAC-SHA256 Verification**: Computes signature over `timestamp + '.' + raw_body` using secret key.
3. **5-Minute Anti-Replay Window**: Drops any webhook where `|now - timestamp| > 300` seconds.
4. **Idempotent DB Insertion**: `ON CONFLICT (provider_transaction_id) DO NOTHING` prevents duplicate balances.
