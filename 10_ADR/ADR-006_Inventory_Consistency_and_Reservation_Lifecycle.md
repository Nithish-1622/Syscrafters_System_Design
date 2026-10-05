# ADR-006: Inventory Consistency Model & Reservation Lifecycle

**Status:** Approved  
**Date:** 2026-10-05  
**Author:** Member 1 (System Architect)  
**Deciders:** Core Engineering Team  

---

## 1. Context & Problem Statement
Flash-sale e-commerce presents an inherent tension between **fast stock allocation** and **payment settlement latency**.
- If inventory is only deducted *after* payment succeeds, hundreds of customers will be paying concurrently for the same 100 units, resulting in massive overselling and thousands of forced refunds.
- If inventory is deducted permanently upon clicking "Buy Now", users who abandon checkout, experience payment card failure, or close their browser permanently lock up limited stock, depriving legitimate buyers and hurting business revenue.

The system requires a temporary inventory reservation model that holds stock for a bounded window, releases uncommitted stock automatically, and guarantees that total sold inventory never exceeds physical stock ($S_{\text{sold}} \le 100$).

---

## 2. Options Considered

### Option 1: Permanent Deduction on Click (No Temporary Reservation)
- **Description:** Deduct stock permanently on "Buy Now"; trigger warehouse dispatch once payment clears; reverse stock if payment fails.
- **Pros:** Conceptually simple.
- **Cons:** Abandoned checkouts permanently deplete stock unless manually cleaned up; locks up inventory for hours; high inventory leakage rate.

### Option 2: Payment-First Allocation (Reserve on Payment Success)
- **Description:** Allow all 10,000 customers to submit payments; only the first 100 cleared payments receive inventory; the remaining 9,900 receive automatic refunds.
- **Pros:** Zero stock lockup on abandoned carts.
- **Cons:** **Severe Business Disaster.** Charges thousands of customer cards for goods that are already sold out; burns payment gateway processing fees; triggers customer outrage and credit card chargeback penalties.

### Option 3: Time-Bounded Atomic Lease Reservation (Selected)
- **Description:** Deduct stock atomically at the start of checkout and grant a temporary 300-second (5-minute) lease. If payment succeeds within 300s, finalize the reservation to `SOLD`. If payment fails, times out, or the lease expires, release the stock atomically back to the available pool.
- **Pros:** Guarantees zero overselling; provides customers a protected 5-minute checkout window; automatically recovers abandoned stock for other waiting customers.
- **Cons:** Requires active lease tracking, distributed expiry scheduling, and late-payment refund protection.

---

## 3. Decision
We adopt **Option 3: Time-Bounded Atomic Lease Reservation**.

### State Lifecycle Implementation:
```
AVAILABLE ──(Buy Now)──► RESERVED ──(Start Pay)──► PAYMENT_PENDING ──(Auth)──► CONFIRMED ──► SOLD
   ▲                        │                           │
   │                        ▼                           ▼
   └────────────── (TTL Expired / Cancel) ─────── RELEASED
```

1. **Lease Duration:** Exactly **300 seconds (5 minutes)**.
2. **Atomic Invariant:** The sum of available, reserved, and sold quantities strictly equals total stock at all times:
   $$S_{\text{available}} + S_{\text{reserved}} + S_{\text{sold}} = 100$$
3. **Dual-Tier Expiry Engine:**
   - **Proactive Sweeper:** Background daemon queries Redis Sorted Set `reservations:expiries` every 1,000ms and restores expired stock counters.
   - **Reactive Gate Check:** When a customer attempts payment confirmation, the Payment Service checks `reservation.is_active()`. If expired, payment confirmation is rejected immediately.
4. **Late Payment Safety Protocol:** If a payment authorization somehow clears after lease expiry (due to extreme external bank network delay), the Payment Service detects that the reservation status is `RELEASED` / `EXPIRED`, flags the order as `CANCELLED_TIMED_OUT`, and initiates an **immediate automated refund** to the customer's card. Under no condition is extra stock minted.

---

## 4. Architectural Consequences & Trade-offs

### Positive Consequences:
- **Zero Overselling:** At no point in time can more than 100 active reservations exist.
- **Fair Customer Experience:** Legitimate customers get 5 full minutes to enter CVV, complete 3D-Secure SMS challenges, and authorize funds without being sniped by bots.
- **Self-Healing Stock Reclamation:** Abandoned checkouts are returned to the sale pool within 5 minutes without manual database intervention.

### Negative Consequences / Trade-offs:
- **Timing Edge Cases:** Requires NTP clock synchronization across servers ($\Delta t < 20\text{ ms}$) and synchronized UTC timestamps.
- **Mitigation:** Expiry checks rely on relative lease durations and database-generated `CURRENT_TIMESTAMP` rather than client device clocks.
