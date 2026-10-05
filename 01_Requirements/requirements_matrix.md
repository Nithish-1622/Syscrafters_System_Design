# SALESTORM 2026 | Requirements & Scale Specification

## 1. Official Business Requirements

SALESTORM is a high-scale e-commerce flash-sale system engineered for high-concurrency burst traffic.

### Core Business Flow:
$$\text{Customer} \to \text{Product Discovery} \to \text{Cart} \to \text{Inventory Check} \to \text{Inventory Reservation} \to \text{Checkout} \to \text{Payment} \to \text{Order} \to \text{Fulfilment} \to \text{Shipment} \to \text{Notification} \to \text{Delivery Tracking}$$

---

## 2. Scale & Performance Targets

| Metric | Target Specification | Design Implication |
| :--- | :--- | :--- |
| **Normal Traffic** | 10,000 requests/sec | CDN caching, read replicas, standard connection pooling. |
| **Flash-Sale Burst** | **Up to 500,000 requests/sec** | Virtual waiting room, Redis token pre-allocation gate, atomic DB updates. |
| **Reservation Latency** | p99 < 100 ms | In-memory gate, local single-row latching. |
| **Stock Contention Target** | 10,000 users for 100 units | Mathematical non-overselling guarantee ($\text{sold} \le 100$). |
| **Payment Success Rate** | 95% approved | 5% declined; triggers compensating stock release. |
| **Duplicate Requests** | 2% traffic | Handled idempotently via `Idempotency-Key` header. |
| **Order Service Outage** | 30.0 seconds resilience | Durable message queue buffering with zero message loss. |

---

## 3. Functional Requirements Checklist

- [x] **FR-1 (Prevent Overselling)**: Under concurrent load, never confirm more sales than initial physical inventory.
- [x] **FR-2 (Temporary Holds)**: Reserve inventory during checkout with a 5-minute TTL.
- [x] **FR-3 (Auto-Release on Expiry/Failure)**: Return unpurchased stock back to the available pool.
- [x] **FR-4 (Payment Safety)**: Eliminate duplicate charges via provider tokens and idempotency keys.
- [x] **FR-5 (Resilient Order Processing)**: Decouple payment from order generation via durable async messaging.
- [x] **FR-6 (Security & Observability)**: Zero plaintext cardholder data, full Prometheus metrics, and W3C distributed tracing.
