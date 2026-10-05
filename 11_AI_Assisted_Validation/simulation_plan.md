# SALESTORM 2026 | Simulation & Verification Plan

## 1. Objective & Hypothesis

The objective of the SALESTORM validation harness is to provide **mathematical and empirical proof** that the system architecture, database model, API contracts, and event pipelines satisfy all correctness invariants under extreme concurrent load and failure scenarios.

### Central Invariant Hypothesis:
$$\text{Under 10,000 concurrent requests competing for 100 stock units:}$$
$$\text{Final Sold Quantity} \le 100$$
$$\text{Oversold Units} \equiv 0$$
$$\text{Duplicate Business Transactions} \equiv 0$$

---

## 2. Test Scenarios & Parameters

| Parameter | Value | Description |
| :--- | :--- | :--- |
| **Initial Stock** | 100 units | Total physical items available in inventory. |
| **Concurrent Contenders** | 10,000 requests | Arriving concurrently to simulate a flash-sale burst. |
| **Payment Success Rate** | 95% | Probability that payment provider approves charge. |
| **Payment Failure Rate** | 5% | Probability that charge is declined (insufficient funds, fraud). |
| **Duplicate Request Rate**| 2% | Replaying identical `Idempotency-Key` and request payload. |
| **Order Service Outage** | 30.0 seconds (scaled) | Simulated downstream service crash/partition while messages buffer in queue. |
| **Reservation TTL** | 5.0 seconds (simulation scale)| Unpaid reservations automatically expire and restore stock. |

---

## 3. Seven Mandatory Verification Scenarios

1. **Scenario 1: Happy Path Purchase**: Request -> Inventory Reservation -> Payment Succeeded -> Order Created & Confirmed -> Stock Sold.
2. **Scenario 2: Payment Failure & Compensation**: Request -> Reservation -> Payment Fails (5%) -> Reservation Released -> Stock returned to available pool for subsequent shoppers.
3. **Scenario 3: Duplicate Request Idempotency**: 2% duplicate requests send identical `Idempotency-Key`. Replayed request receives original cached response without double-decrementing stock.
4. **Scenario 4: Downstream Order Service Outage**: Payment succeeds; Order Service crashes for 30s. Messages persist in durable queue buffer. Upon recovery, consumer drains backlog and confirms all orders without dropping transactions.
5. **Scenario 5: Zero Inventory Boundary Race**: At unit 100, remaining stock hits 0. All subsequent 9,900 requests are rejected with `HTTP 409 Out of Stock`.
6. **Scenario 6: Database Recovery**: Transient connection failure handled via exponential backoff retries.
7. **Scenario 7: Gateway Timeout & Reconciliation**: Timed-out payments flagged as `RECONCILIATION_REQUIRED` without creating duplicate charges.

---

## 4. Invariant Assertions to Verify

- [x] **Assertion 1 (No Overselling)**: `sold_quantity <= initial_stock (100)`.
- [x] **Assertion 2 (Stock Conservation)**: `available_quantity + reserved_quantity + sold_quantity == initial_stock (100)`.
- [x] **Assertion 3 (Idempotency Uniqueness)**: Duplicate requests result in 0 extra reservations or orders.
- [x] **Assertion 4 (Zero Order Loss)**: `total_successful_payments == total_confirmed_orders`.
- [x] **Assertion 5 (Reservation Integrity)**: Every failed payment has its reserved unit returned to the available pool or sold to another customer.
