# SALESTORM 2026 | Rate Limiting & Abuse Protection Architecture

## 1. Scale Context: 10,000 Normal vs 500,000 Flash-Sale Requests/Sec

Under normal conditions, SALESTORM handles ~10,000 req/sec across catalog and cart browsing. During a limited-stock flash sale (100 units), traffic spikes by **50× to 500,000 req/sec**. 

If rate limiting is applied naively (e.g. strict per-IP blocks), legitimate shoppers behind cellular carrier NATs (Carrier-Grade NAT) will be falsely blocked, while distributed botnets with 50,000 IP addresses will bypass the filter.

SALESTORM implements **Multi-Tiered Adaptive Rate Limiting & Traffic Shaping**:

```
[ Flash Sale Traffic: 500,000 req/sec ]
                   │
                   ▼
┌────────────────────────────────────────────────────────┐
│ TIER 1: EDGE IP-LEVEL RATE LIMITING (WAF / Cloudflare) │
│ - Token Bucket: Max 100 req/sec per IP                 │
│ - Blocks aggressive scrapers and volumetric DDoS       │
└────────────────────────────────────────────────────────┘
                   │ (Passed: 150,000 req/sec)
                   ▼
┌────────────────────────────────────────────────────────┐
│ TIER 2: VIRTUAL WAITING ROOM (Queue-IT / Ingress FIFO) │
│ - Absorbs traffic shock; assigns cryptographically     │
│   signed queue tickets. Admits target: 20,000 req/sec  │
└────────────────────────────────────────────────────────┘
                   │ (Passed: 20,000 req/sec)
                   ▼
┌────────────────────────────────────────────────────────┐
│ TIER 3: PER-ACCOUNT RATE LIMITING (Redis Cluster)      │
│ - Sliding Window: Max 2 reservation attempts / 10s     │
│ - Enforces anti-scalper policy (1 item per human)      │
└────────────────────────────────────────────────────────┘
                   │ (Passed: 10,000 req/sec)
                   ▼
┌────────────────────────────────────────────────────────┐
│ TIER 4: IN-MEMORY REDIS LUA PRE-ALLOCATION GATE        │
│ - Gates DB access to exactly available stock units     │
└────────────────────────────────────────────────────────┘
```

---

## 2. Sliding Window Counter Algorithm (Redis Cluster)

For per-account reservation limits, SALESTORM utilizes the **Redis Sliding Window Log** via an atomic Lua script:

```lua
-- KEYS[1]: User rate limit key (e.g., "ratelimit:cust-123:reservation")
-- ARGV[1]: Current Unix Timestamp (milliseconds)
-- ARGV[2]: Window Size (e.g., 10000ms = 10s)
-- ARGV[3]: Maximum Allowed Requests (e.g., 2)

local current_time = tonumber(ARGV[1])
local window_start = current_time - tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])

-- Remove timestamps outside the sliding window
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', window_start)

-- Count remaining requests in the active window
local current_count = redis.call('ZCARD', KEYS[1])

if current_count < max_requests then
    -- Record this request timestamp
    redis.call('ZADD', KEYS[1], current_time, current_time)
    redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
    return 1 -- ALLOWED
else
    return 0 -- RATE LIMITED
end
```

---

## 3. Rate Limit Response Headers

When a client makes a request, the API Gateway returns standard rate limit headers:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
X-RateLimit-Limit: 2
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1791193215
Retry-After: 8

{
  "type": "https://errors.salestorm.io/rate-limit-exceeded",
  "title": "Too Many Requests",
  "status": 429,
  "code": "RATE_LIMIT_EXCEEDED",
  "detail": "Reservation quota exceeded. Please wait 8 seconds before retrying.",
  "instance": "/api/v1/reservations",
  "correlation_id": "req-9912-bb22"
}
```
