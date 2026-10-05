# SALESTORM 2026 | API Security & Edge Hardening

## 1. Transport Layer Security (TLS 1.3)

All inbound connections require **TLS 1.3** with Perfect Forward Secrecy (PFS). Legacy protocols (SSLv3, TLS 1.0, TLS 1.1) are rejected at the edge gateway.

### Approved Cipher Suites:
- `TLS_AES_256_GCM_SHA384`
- `TLS_CHACHA20_POLY1305_SHA256`
- `TLS_AES_128_GCM_SHA256`

---

## 2. Mandatory HTTP Security Headers

Every API response emitted by the edge gateway includes:

| Header Name | Configured Value | Security Purpose |
| :--- | :--- | :--- |
| **`Strict-Transport-Security`** | `max-age=63072000; includeSubDomains; preload` | Forces HTTPS for 2 years; prevents SSL stripping. |
| **`X-Content-Type-Options`** | `nosniff` | Disables MIME type sniffing by browsers. |
| **`X-Frame-Options`** | `DENY` | Prevents Clickjacking attacks in IFRAMEs. |
| **`Content-Security-Policy`** | `default-src 'none'; frame-ancestors 'none';` | Restricts script execution and embedding. |
| **`Cache-Control`** | `no-store, no-cache, must-revalidate` | Prevents intermediate proxies from caching sensitive order/reservation data. |

---

## 3. Cross-Origin Resource Sharing (CORS) Policy

SALESTORM strictly prohibits wildcard CORS (`Access-Control-Allow-Origin: *`) on stateful endpoints:
- **Allowed Origins**: `https://www.salestorm.io`, `https://checkout.salestorm.io`
- **Allowed Methods**: `GET, POST, OPTIONS`
- **Allowed Headers**: `Authorization, Content-Type, Idempotency-Key, X-Correlation-Id`
- **Max Age**: `86400` (24-hour preflight cache).

---

## 4. Edge WAF & Request Size Enforcement

1. **Maximum Payload Size**: API Gateway enforces a strict **64 KB request body limit**. Any request exceeding 64 KB is dropped immediately with `HTTP 413 Payload Too Large`, preventing memory allocation denial of service.
2. **WAF Managed Rule Sets**:
   - OWASP Core Rule Set (CRS 3.3) for SQL Injection and Cross-Site Scripting (XSS).
   - Known Bad Inputs / Botnet signatures.
   - IP Reputation rate throttling on abnormal bursts.
