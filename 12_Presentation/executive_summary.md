# SALESTORM 2026 | Hackathon Presentation: Executive Summary

## 1. Challenge & Core Engineering Invariant

SALESTORM is a high-scale flash-sale e-commerce platform facing extreme burst traffic:
- **Normal Load**: 10,000 requests/sec
- **Flash-Sale Burst**: Up to 500,000 requests/sec
- **Practical Validation Scenario**: 10,000 concurrent customers competing for exactly **100 stock units**.

### The Central Assertion:
$$\text{Under all failure and concurrency conditions:}$$
$$\mathbf{\text{Successful Sales} \le \text{Initial Available Stock (100 units)}}$$
$$\mathbf{\text{Overselling Violations} \equiv 0}$$

---

## 2. Key Architectural Deliverables (Member 3 Ownership)

1. **Relational Database Design (`04_Database/`)**:
   - Production PostgreSQL 15 DDL with 14 core tables, declarative `CHECK` constraints, and partial indexes.
   - Atomic conditional SQL update (`UPDATE inventory SET available = available - 1 WHERE id = :id AND available >= 1`) providing mathematical non-overselling guarantees at engine level.
   - Transactional Outbox pattern eliminating distributed dual-write inconsistencies.
2. **API & Event Contracts (`05_API/`)**:
   - Fully compliant OpenAPI 3.1.0 specification with RFC 7807 Problem Details error models.
   - Three-tier idempotency protocol utilizing the `Idempotency-Key` header with SHA-256 payload hashing.
   - CloudEvents 1.0 asynchronous contracts strictly segregating commands from events.
3. **Security & Observability Architecture (`09_Security_Observability/`)**:
   - Zero-trust security model: PCI-DSS SAQ-A compliant tokenized payments, JWT/mTLS authentication, and Redis sliding-window rate limiting.
   - Prometheus alerting rules with P1-P4 severities and executable incident runbooks.
   - Distributed tracing via W3C Trace Context propagating seamlessly across HTTP and message brokers.
4. **Empirical AI-Assisted Validation (`11_AI_Assisted_Validation/`)**:
   - Executed thread-safe Python simulation (`simulate_flash_sale.py`) subjecting the model to 10,000 concurrent requests, 5% payment failure, 2% duplicate requests, and a 30-second Order Service crash.
   - **Empirical Result**: Exactly 100 units sold, 0 oversold, 100% of buffered orders recovered after outage, all invariants passed.
