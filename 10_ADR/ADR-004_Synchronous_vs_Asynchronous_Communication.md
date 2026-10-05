# ADR-004: Synchronous vs. Asynchronous Inter-Service Communication

**Status:** Approved  
**Date:** 2026-10-05  
**Author:** Member 1 (System Architect)  
**Deciders:** Core Engineering Team  

---

## 1. Context & Problem Statement
In distributed microservice architectures, choosing between synchronous (REST / gRPC) and asynchronous (Message Broker / Event Streaming) protocols determines system latency, consistency, fault isolation, and user experience. 
Two dangerous architectural extremes exist:
- **Synchronous Anti-Pattern ("Distributed Monolith"):** Chaining synchronous HTTP calls from Gateway $\rightarrow$ Checkout $\rightarrow$ Inventory $\rightarrow$ Payment $\rightarrow$ Order $\rightarrow$ Warehouse $\rightarrow$ Notification. A failure or latency spike in any single downstream service causes cascading timeouts and aborts the entire user transaction.
- **Asynchronous Anti-Pattern ("Event-Driven Everything"):** Making inventory reservation asynchronous via message queues. The user clicks "Buy Now", sees a spinner, and receives an email 20 minutes later saying: *"Sorry, your request was queued, but stock was already gone."* This creates severe user frustration and poor competitive positioning.

We must define an explicit, scientifically defended communication boundary across all 12 pipeline stages.

---

## 2. Options Considered

### Option 1: 100% Synchronous Call Chains (REST / gRPC Everywhere)
- **Description:** Every business workflow is executed via blocking RPCs from the initial user click to order confirmation and notification.
- **Pros:** Immediate end-to-end feedback; straightforward error handling in a single call stack.
- **Cons:** High coupling; cumulative latency (sum of all downstream response times); catastrophic failure cascading (e.g., if Order Service crashes for 30s, all upstream payments fail).

### Option 2: 100% Asynchronous Event Choreography (Events Everywhere)
- **Description:** All user interactions immediately return `202 Accepted` and are dispatched as events onto a message broker.
- **Pros:** Infinite initial write absorption; zero synchronous downstream coupling.
- **Cons:** Awful user experience for scarce inventory; users cannot know if they secured stock; complex compensating transactions when reservations fail asynchronously.

### Option 3: Bounded Hybrid Paradigm — Synchronous for Scarcity, Asynchronous for Abundance (Selected)
- **Description:** 
  - **Synchronous:** Product details, cart mutations, atomic inventory reservation, and payment authorization.
  - **Asynchronous:** Post-payment order generation, inventory commitment (`SOLD`), warehouse fulfillment, shipment tracking, and customer notifications.
- **Pros:** Immediate, deterministic feedback on stock allocation ($< 150\text{ ms}$); payment is verified before screen exit; complete fault isolation for post-payment pipelines (e.g., Order Service outages do not break payments).
- **Cons:** Requires eventual consistency management, Transactional Outbox pattern, and idempotent consumer workers.

---

## 3. Decision
We adopt **Option 3: Bounded Hybrid Paradigm (Synchronous Scarcity + Asynchronous Abundance)**.

### Architectural Breakdown:
1. **Synchronous Boundary:**
   - `Client → Product Service` (REST/HTTP): Immediate product viewing.
   - `Checkout → Inventory Service` (gRPC): Immediate deterministic reservation confirmation or fast-fail rejection.
   - `Checkout → Payment Service` (HTTPS): Direct gateway charge authorization and 3D-Secure handling.
2. **Asynchronous Boundary:**
   - `Payment Service → Order Service` (Kafka): Emits `PaymentSuccessfulEvent`. Order creation is decoupled.
   - `Order Service → Shipment Service` (Kafka): Fulfillment manifest generation.
   - `System Events → Notification Service` (Kafka): Non-blocking SMS/Email alerts.
   - `Reservation Sweeper → Inventory Service` (Delayed Queue): Stock lease expiration releases.

---

## 4. Architectural Consequences & Trade-offs

### Positive Consequences:
- **Resilience to Downstream Crashes:** In the official hackathon test case where the **Order Service is down for 30 seconds**, upstream payments continue to succeed without interruption. Messages buffer safely in Kafka and process upon recovery.
- **Low Latency on Critical Path:** Eliminates unnecessary downstream serialization; the user is done as soon as payment is authorized.
- **Zero Overselling:** The synchronous reservation boundary ensures that stock balance is verified and reserved before any payment call is initiated.

### Negative Consequences / Trade-offs:
- **Eventual Consistency Window:** There is an average latency of 500–2,000ms between payment settlement and order database persistence. 
- **Mitigation:** The checkout UI transitions to a pending state: *"Payment Confirmed! Finalizing your order..."*, connected to a live WebSocket channel that pushes the completed order ID as soon as the Order Service consumes the event.
