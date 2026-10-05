# SALESTORM 2026 | Input Validation & Parameter Sanitization

## 1. Zero-Trust Validation Principles

All untrusted input arriving across the network boundary must undergo strict validation before triggering business operations.

### Key Tenets:
1. **Reject Unknown Fields (Disallow Mass Assignment)**: JSON parsers are configured with strict schema enforcement (`additionalProperties: false`). Any unexpected payload attribute triggers immediate rejection.
2. **Fixed-Point Financial Math**: Monetary amounts are accepted as fixed-point decimal strings or integers in smallest currency units (cents) to eliminate binary IEEE-754 floating-point inaccuracies.
3. **Anti-Hoarding Quantity Guards**: Flash-sale reservations enforce `1 <= quantity <= 2` units per checkout attempt.

---

## 2. Input Validation Matrix

| Field | Target Entity | Validation Rule / Regex | Failure HTTP Status | Error Detail |
| :--- | :--- | :--- | :--- | :--- |
| `product_id` | Reservation / Order | RFC 4122 UUID v4 regex: `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` | `400 Bad Request` | "product_id must be a valid UUIDv4" |
| `quantity` | Reservation | Integer: `1 <= quantity <= 2` | `400 Bad Request` | "Quantity must be between 1 and 2 units" |
| `amount` | Payment | Fixed-point numeric: `amount > 0.00` and `amount <= 50000.00` | `400 Bad Request` | "Payment amount must be greater than zero" |
| `currency` | Payment / Order | ISO 4217 standard 3-letter code: `^[A-Z]{3}$` (Whitelisted: `USD`, `EUR`, `GBP`) | `400 Bad Request` | "Unsupported currency code" |
| `idempotency_key`| Ingress Header | ASCII string: `^[A-Za-z0-9\-_]{16,128}$` | `400 Bad Request` | "Idempotency-Key must be 16-128 chars" |
| `postal_code` | Shipping Address | Alphanumeric string: `^[A-Za-z0-9 \-]{3,10}$` | `400 Bad Request` | "Invalid postal code format" |
| `phone_number`| Customer Profile | ITU E.164 format: `^\+[1-9]\d{1,14}$` | `400 Bad Request` | "Phone must follow E.164 format" |

---

## 3. Defense Against Parameter Pollution & SQL Injection

Even though SALESTORM employs **parameterized queries exclusively** (eliminating SQL injection risks at the driver level), the validation layer sanitizes strings:
- Stripping control characters (`\0`, `\r`, `\x1a`).
- Enforcing UTF-8 encoding integrity.
- Sanitizing rich-text description fields via OWASP AntiSamy / DOMPurify.
