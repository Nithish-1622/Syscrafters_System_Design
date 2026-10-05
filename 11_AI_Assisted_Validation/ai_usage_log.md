# SALESTORM 2026 | AI Usage & Verification Log

## 1. Compliance Statement

In accordance with Hackathon regulations, this document records all AI assistance utilized during the engineering and validation of the SALESTORM database, API, and validation models. All AI-assisted artifacts were subjected to rigorous human engineering review, manual code audits, boundary testing, and empirical verification.

---

## 2. AI Usage Registry

### Item 1: High-Concurrency Simulation Harness
- **Tool / Model**: Gemini 3.8 Flash (High) / Antigravity Agent
- **Engineering Purpose**: Generate a standalone, thread-safe Python concurrency test harness (`simulate_flash_sale.py`) to simulate 10,000 customers, 100 stock units, payment failures, duplicate requests, and a 30-second Order Service outage.
- **Prompt Summary**: "Create a self-contained Python concurrency harness that models atomic conditional SQL updates, idempotency deduplication with SHA-256 hashes, payment failure compensation, and queue buffer retention during an Order Service crash."
- **Generated Artifact**: `11_AI_Assisted_Validation/simulate_flash_sale.py`
- **Human Engineering Modifications**:
  - Corrected duplicate key mapping to ensure replayed requests shared the exact primary `Idempotency-Key` and payload hash to properly exercise the cache-hit logic.
  - Added strict database table check constraints (`CHECK (available_quantity >= 0)`) to the SQLite in-memory test engine to mirror PostgreSQL physical behavior.
  - Added formal assertions verifying the Quantity Conservation Law ($\text{avail} + \text{resv} + \text{sold} = \text{total}$).
- **Validation Performed**: Executed script directly via CLI, verifying 10,000 requests processed, 100 sold units, 0 oversold, 100% orders recovered after outage.

### Item 2: OpenAPI 3.1.0 Specification
- **Tool / Model**: Gemini 3.8 Flash (High)
- **Engineering Purpose**: Generate standard OpenAPI 3.1.0 YAML schema for all SALESTORM endpoints, headers, and RFC 7807 problem details.
- **Generated Artifact**: `05_API/openapi.yaml`
- **Human Modifications**: Added explicit `Idempotency-Key` and `X-Correlation-Id` header references to all mutating endpoints, aligned error response references with RFC 7807 problem details schema.
- **Validation Performed**: YAML syntax validation and cross-reference checks against data dictionary and LLD classes.

### Item 3: PostgreSQL Physical DDL
- **Tool / Model**: Gemini 3.8 Flash (High)
- **Engineering Purpose**: Generate production-grade ANSI SQL / PostgreSQL 15 DDL with UUID primary keys, check constraints, partial indexes, and transactional outbox.
- **Generated Artifact**: `04_Database/schema.sql`
- **Human Modifications**: Added partial indexes on `inventory_reservations` and `transactional_outbox` to optimize worker scans, added strict balance check constraint `available + reserved + sold = total_quantity`.
- **Validation Performed**: DDL syntax and constraint logic audit.
