# SALESTORM 2026 | Secrets Management & Key Lifecycle Architecture

## 1. Zero-Secret Invariant

No secret, cryptographic key, database password, or API credential may ever appear in:
1. Source code repositories or commit histories.
2. Container images or static configuration files.
3. Application logs, error messages, or monitoring metrics.
4. Client-facing API responses.

---

## 2. Dynamic Secret Architecture (Logical Model)

SALESTORM specifies a centralized, cloud-agnostic **Secrets Management Engine** (e.g. HashiCorp Vault or AWS Secrets Manager):

```
┌────────────────────────────────────────────────────────┐
│ SECRETS MANAGER / KEY MANAGEMENT SERVICE (KMS)         │
│ - Hardware Security Module (HSM) Level 3 backed        │
│ - Centralized policy enforcement & access logging      │
└────────────────────────────────────────────────────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
┌─────────────────────────┐ ┌─────────────────────────┐
│ IAM Role-Based Auth     │ │ Dynamic DB Credentials  │
│ (Instance Profile/mTLS) │ │ (Short-lived, auto-rot) │
└─────────────────────────┘ └─────────────────────────┘
             │                           │
             └─────────────┬─────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ APPLICATION CONTAINER RUNTIME                          │
│ - Credentials injected via RAM / ephemeral tmpfs mount │
│ - Never written to persistent storage                  │
└────────────────────────────────────────────────────────┘
```

---

## 3. Secret Rotation Policies

| Secret Class | Rotation Frequency | Rotation Mechanism | Impact on Running Services |
| :--- | :--- | :--- | :--- |
| **Database Credentials** | Every 30 days | Dual-user automated rotation (User A -> User B -> drop User A). | Zero downtime; connection pools gracefully swap users. |
| **JWT RS256 Signing Key** | Every 14 days | JWKS Key Rollover: New `kid` published 24h prior to signing switch. | Zero downtime; verifying services support overlapping `kid`. |
| **Payment Gateway Secrets**| Every 90 days | Dual-secret grace window with payment provider. | Zero downtime. |
| **Internal mTLS Certs** | Every 24 hours | Automated SPIFFE/SPIRE CA rotation. | Handled automatically by service mesh proxy. |

---

## 4. Pre-Commit & CI/CD Pipeline Scanning

All code submissions are automatically screened by automated scanners (`TruffleHog`, `git-secrets`, and GitHub Secret Scanning) configured with blocking pre-commit and PR validation gates. Any detected token aborts the build immediately.
