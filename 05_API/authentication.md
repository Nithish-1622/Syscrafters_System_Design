# SALESTORM 2026 | Authentication Specification

## 1. Multi-Tiered Authentication Strategy

In a high-scale e-commerce platform, no single authentication mechanism fits all boundaries. SALESTORM implements three dedicated authentication tiers:

```
[ Public Internet ]
        │
        ├── Customer Traffic (HTTPS) ───────────► Tier 1: JWT Bearer Tokens (RS256)
        │
        └── Payment Gateway Callbacks ─────────► Tier 2: HMAC-SHA256 Webhook Signatures
        │
[ Private VPC / Mesh ]
        │
        └── Internal Microservices ────────────► Tier 3: mTLS + Short-Lived Service JWTs
```

---

## 2. Tier 1: Customer Authentication (OAuth2 / OIDC JWT)

- **Standard**: RFC 7519 JSON Web Token (JWT) signed with RS256 (asymmetric RSA 4096-bit).
- **Transport**: `Authorization: Bearer <token>` in HTTP request headers.
- **Verification**: Handled at the API Gateway / Edge proxy using cached Public Keys from `/.well-known/jwks.json`. Microservices do not query the identity database per request!

### JWT Claims Payload Example:
```json
{
  "iss": "https://auth.salestorm.io",
  "sub": "4b917c0a-0982-4211-8891-9e283012bb01",
  "aud": "https://api.salestorm.io",
  "exp": 1791196800,
  "iat": 1791193200,
  "jti": "d09a82bb-2018-4721-a182-39821a",
  "role": "customer",
  "email": "customer@example.com",
  "account_status": "ACTIVE"
}
```

---

## 3. Tier 2: External Payment Webhook Authentication (HMAC-SHA256)

External payment gateways (Stripe, Adyen) do not hold customer JWTs. They communicate via signed asynchronous webhooks.

### Verification Protocol:
1. Provider includes header `X-Signature-SHA256: t=1791193205,v1=9a8bc4...`
2. **Replay Protection**: The application extracts timestamp `t`. If `|current_time - t| > 300 seconds`, the webhook is rejected with `HTTP 401 Unauthorized`.
3. **Signature Computation**:
   $$\text{ExpectedSig} = \text{HMAC-SHA256}(\text{WebhookSecret}, t + "." + \text{RawRequestBody})$$
4. **Timing-Safe Comparison**: Signatures are compared using constant-time equality (`crypto.timingSafeEqual`) to prevent timing side-channel attacks.

---

## 4. Tier 3: Internal Service-to-Service Authentication (mTLS & SPIFFE)

For zero-trust internal communication:
1. **Transport Layer**: Mutual TLS (mTLS 1.3) with ephemeral X.509 certificates rotated every 24 hours via SPIFFE/SPIRE.
2. **Application Layer**: Each service signs an internal service token (`X-Service-Token`) declaring caller identity (`iss: inventory-service`, `aud: payment-service`).
3. Services reject all unencrypted or unauthenticated internal RPCs.
