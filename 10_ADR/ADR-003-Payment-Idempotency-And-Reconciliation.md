# ADR-003: Multi-Tiered Payment Idempotency and Ambiguous Timeout Reconciliation

## Status: ACCEPTED
**Date**: October 2026  
**Authors**: Member 3 (API & Reliability Engineer)

---

## Context & Problem Statement
Under flash-sale peak load, network timeouts between the client, API gateway, and third-party payment gateway (Stripe/Adyen) occur. Clients aggressively retry `POST /payments`. If idempotency is flawed:
1. Customers may be billed multiple times for a single checkout.
2. An ambiguous timeout could lead to prematurely canceling an order where the customer's card was actually debited.

---

## Decision
We implement a **Three-Tier Idempotency Model** combined with an **Asynchronous Reconciliation Engine**:

1. **Tier 1 (HTTP Idempotency)**: Client supplies `Idempotency-Key` header with SHA-256 body hash. Replays return cached responses without re-executing payment logic.
2. **Tier 2 (Gateway Token Deduplication)**: Gateway transactions use provider-side idempotency keys. Database enforces `provider_transaction_id VARCHAR UNIQUE`.
3. **Ambiguous Timeout State**: If a gateway call times out or returns HTTP 504, the payment status is transitioned to **`RECONCILIATION_REQUIRED`** (NOT failed!).
4. **Reconciliation Worker**: An asynchronous worker polls provider APIs (`GET /v1/charges?idempotency_key=...`) to verify actual bank status.
   - If settled: Emits `PaymentSucceeded` to resume order creation.
   - If never received: Marks payment `FAILED` and releases inventory reservation.

---

## Consequences

### Positive:
- **Zero Double-Billing**: Mathematically impossible to charge a credit card twice under retries.
- **Safe Timeout Handling**: Eliminates race condition between timeout refunds and delayed gateway confirmations.

### Negative / Trade-Offs:
- **Delayed Order Confirmation during Network Splits**: Customers experiencing provider timeouts enter a temporary pending state while reconciliation completes (typically 30–60 seconds).
