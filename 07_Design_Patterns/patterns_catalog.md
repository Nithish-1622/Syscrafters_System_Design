# SALESTORM 2026 | Design Patterns Architectural Catalog

## 1. Architectural & Distributed Patterns

| Design Pattern | Category | Where Implemented | Problem Solved |
| :--- | :--- | :--- | :--- |
| **Transactional Outbox** | Distributed Data | Database / Messaging (`transactional_outbox` table) | Eliminates dual-write inconsistency between relational DB commits and message broker publishing. |
| **Choreographed Saga** | Distributed Coordination | Checkout $\to$ Payment $\to$ Order $\to$ Fulfillment | Replaces brittle Two-Phase Commit (2PC) with asynchronous, event-driven compensating transactions. |
| **Idempotent Consumer** | Messaging Reliability | Order Service & Shipment Service event processors | Guarantees safe processing of duplicate at-least-once message deliveries. |
| **Circuit Breaker** | Resilience | Payment Gateway Client & Database Pool Client | Prevents cascading failure during external service outages; fails fast to protect thread pools. |
| **Token Bucket / Sliding Window** | Traffic Shaping | API Gateway / Redis Edge Rate Limiter | Prevents botnet flooding and smooths flash-sale traffic spikes. |

---

## 2. Object-Oriented & Structural Patterns

| Design Pattern | Category | Where Implemented | Problem Solved |
| :--- | :--- | :--- | :--- |
| **Strategy Pattern** | Behavioral | `PaymentGatewayStrategySelector` | Dynamically selects payment gateway (Stripe vs Adyen) based on currency, geography, and real-time health. |
| **Repository Pattern** | Architectural | `IInventoryRepository`, `IOrderRepository` | Decouples domain aggregates from underlying SQL queries and schema details. |
| **Factory Pattern** | Creational | `CloudEventFactory` | Encapsulates generation of standardized CloudEvents 1.0 JSON payloads with valid UUIDs and W3C trace headers. |
| **Decorator Pattern** | Structural | `TracingAndMetricsDecorator` | Wraps API route handlers to automatically inject correlation IDs, latency histograms, and structured logs. |
