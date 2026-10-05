# SALESTORM 2026 | Security Architecture & Threat Model (STRIDE)

## 1. Executive Summary & Defense-in-Depth

The SALESTORM security architecture adheres to the **Zero-Trust Principle**: never trust, always verify. Under flash-sale conditions where 500,000 requests/sec arrive at the edge, the system is a prime target for automated scalper bots, credential stuffing, DDoS attacks, race condition exploits, and financial replay attacks.

```
[ EDGE PERIMETER ]
  - Cloudflare / AWS WAF (DDoS mitigation, geo-fencing, bot management)
  - TLS 1.3 Termination, Strict Transport Security (HSTS)
  - Rate Limiting (Token Bucket / Redis Sliding Window)
         │
         ▼
[ API GATEWAY ]
  - JWT Token Authentication & Signature Validation
  - RFC 7807 Input Validation & Payload Size Limits (max 64KB)
  - Idempotency Key De-duplication Store
         │
         ▼
[ APPLICATION SERVICE MESH ]
  - Mutual TLS (mTLS) with SPIFFE/SPIRE Identity Certificates
  - Role-Based & Resource-Level Ownership Authorization (RBAC/ABAC)
  - PCI-DSS SAQ-A Compliant Tokenized Payment Processing
         │
         ▼
[ PERSISTENCE & DATA STORAGE ]
  - AES-256 Encryption at Rest (KMS managed keys)
  - Least-Privilege Database Roles (Revoked DDL/DROP/DELETE)
  - Append-Only Partitioned Audit Trails
```

---

## 2. STRIDE Threat Model & Mitigations

| STRIDE Category | Threat Description | Attack Vector in Flash Sale | Architectural Countermeasure |
| :--- | :--- | :--- | :--- |
| **Spoofing** | Attacker impersonates legitimate customer or internal microservice. | Replaying stolen session tokens or forging internal service headers. | RS256 signed JWTs with short expiry (15m); mTLS with X.509 certs for internal RPCs. |
| **Tampering** | Modifying request payload (e.g., changing price from $499 to $1). | Parameter tampering in transit. | TLS 1.3 encryption; server-side catalog price lookup (client price is never trusted). |
| **Repudiation** | Customer claims they never authorized a payment or reservation. | Chargeback disputes after flash sale. | Immutable, append-only `audit_logs` capturing IP, timestamp, actor ID, and correlation ID. |
| **Information Disclosure** | Leakage of PII, internal architecture, or database details. | Verbose stack traces in error responses; credit card leaks. | RFC 7807 standardized errors; PCI-DSS SAQ-A zero-storage of PAN/CVV; log redaction filters. |
| **Denial of Service** | Botnet floods inventory reservation endpoint with 500,000 req/sec. | Resource starvation; database connection pool exhaustion. | Edge WAF challenge, Redis token bucket rate limiting, Redis Lua pre-allocation filter. |
| **Elevation of Privilege** | Normal customer accesses administrative stock replenishment. | Parameter tampering; privilege escalation via modified role claims. | Cryptographically signed JWT claims verified at gateway; strict RBAC guards in application code. |
