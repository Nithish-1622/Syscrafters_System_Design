# SALESTORM 2026 | Authentication Architecture

## 1. Authentication Mechanisms

SALESTORM decouples authentication across three boundaries:
1. **Public Edge (Customer Auth)**: OAuth 2.0 / OpenID Connect (OIDC) JWT tokens.
2. **Payment Ingress (External Webhooks)**: Cryptographic HMAC-SHA256 signatures with timestamp anti-replay validation.
3. **Internal VPC Mesh (Inter-Service)**: Mutual TLS (mTLS) with SPIFFE/SPIRE X.509 identity certificates.

---

## 2. Customer Authentication Lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant Client as Web/Mobile Client
    participant Auth as Identity Provider (Cognito/Keycloak)
    participant Gateway as API Gateway / Kong
    participant Service as Internal Microservice

    Client->>Auth: POST /oauth/token (credentials)
    Auth-->>Client: Access Token (RS256 JWT, 15-min TTL) + Refresh Token (7-day TTL)
    
    Client->>Gateway: POST /api/v1/reservations [Authorization: Bearer <JWT>]
    Note over Gateway: Gateway verifies signature against cached JWKS.<br/>Extracts customer_id, roles, account status.
    
    alt Signature Valid & Token Not Expired
        Gateway->>Service: Forward request with injected header:<br/>X-User-Id: cust-123<br/>X-User-Role: customer
        Service-->>Gateway: HTTP 201 Created
        Gateway-->>Client: HTTP 201 Created
    else Signature Invalid or Expired
        Gateway-->>Client: HTTP 401 Unauthorized [RFC 7807 Problem Details]
    end
```

---

## 3. Webhook Authentication (Payment Providers)

External payment gateways (Stripe, Adyen) do not support OAuth. Webhooks are authenticated using symmetric HMAC-SHA256 signatures:
- **Header**: `X-Signature-SHA256: t=1791193205,v1=9a8bc4...`
- **Replay Protection Window**: 300 seconds.
- **Timing Safe Check**: Verification uses constant-time string comparison to prevent side-channel timing attacks.
