# ADR-007: Caching Architecture & Single-SKU Hotspot Mitigation

**Status:** Approved  
**Date:** 2026-10-05  
**Author:** Member 1 (System Architect)  
**Deciders:** Core Engineering Team  

---

## 1. Context & Problem Statement
Flash sales generate an extreme **Pareto distribution (99/1 rule)**: $99\%$ of the 500,000 requests/sec are directed at less than $1\%$ of the product catalog (the promotional flash-sale SKU). 
This creates severe hotspot challenges:
- **Cache Stampede (Thundering Herd):** When a cache key expires, thousands of concurrent cache misses hit the origin database simultaneously.
- **Single-Key In-Memory Bottleneck:** While distributed caches scale well across millions of keys, 500,000 requests targeting a **single key** (e.g., `stock:SKU_X`) route to a single cache node, saturating its single CPU core and network socket buffer.
- **Cache Invalidation Latency:** Showing stale "In Stock" indicators when inventory is already zero leads to useless upstream traffic and poor user experience.

We need a multi-layer caching and hotspot mitigation strategy.

---

## 2. Options Considered

### Option 1: Simple Cache-Aside on Origin Database
- **Description:** Application checks Redis; if cache miss, queries PostgreSQL and sets Redis with 60-second TTL.
- **Pros:** Standard pattern; simple to implement.
- **Cons:** Catastrophic cache stampede under flash sales; single Redis node hosting the flash SKU saturates; cache-aside does not protect write paths.

### Option 2: Pure Local In-Memory Process Caching (Go sync.Map / Guava)
- **Description:** Each API Gateway pod caches product data and stock counters in its local application memory.
- **Pros:** Zero network hops; millions of reads per second.
- **Cons:** Inability to synchronize atomic writes across 100 gateway pods; leads to inconsistent reservation counts and massive overselling.

### Option 3: Multi-Tiered Hierarchical Caching + Virtual Key Sharding (Selected)
- **Description:** 
  - **Tier 1 (Edge CDN):** Micro-caches product catalog and availability flags at global CDN PoPs for 500ms.
  - **Tier 2 (Gateway In-Memory Token Gate):** Local gateway boolean flag: `is_sold_out: SKU_X` updated via event pub/sub.
  - **Tier 3 (Redis Cluster with Virtual Stock Sharding):** Distributes flash-sale inventory across multiple Redis shards using sub-keys (`stock:SKU_X:shard:1` ... `stock:SKU_X:shard:10`).
- **Pros:** Shields origin databases from 99.9% of traffic; eliminates single-core Redis saturation; enables scaling to 500,000 req/sec.
- **Cons:** Slightly higher orchestration complexity to aggregate sub-shard balances.

---

## 3. Decision
We adopt **Option 3: Multi-Tiered Hierarchical Caching + Virtual Key Sharding**.

### Technical Mechanics:
1. **Edge Micro-Caching (CDN):**  
   Catalog reads carry `Cache-Control: public, max-age=1, stale-while-revalidate=5`. Edge CDN collapses 100,000 reads/sec into 1 request/sec to origin.
2. **Virtual Stock Sharding for High Concurrency SKUs:**  
   When a flash sale exceeds 50,000 req/sec, inventory is partitioned into $K = 10$ virtual sub-buckets:
   - `stock:item:X:0` = 10 units
   - `stock:item:X:1` = 10 units
   - ...
   - `stock:item:X:9` = 10 units  
   A user request routes to `shard = hash(user_id) % 10`. This distributes the 500k contention across 10 separate Redis primary nodes, guaranteeing no single core exceeds 50,000 ops/sec.
3. **Gateway Fast-Fail In-Memory Flag:**  
   When all sub-shards reach 0, the Inventory Service broadcasts a Redis Pub/Sub event: `SKU_DEPLETED(SKU_X)`. Every API Gateway updates a local atomic boolean flag. Future requests for `SKU_X` are rejected directly at the gateway with `409 Conflict` in $< 1\text{ ms}$ without network traversal.

---

## 4. Architectural Consequences & Trade-offs

### Positive Consequences:
- **Linear Scaling Under Hotspots:** Virtual sharding breaks the single-key serialization ceiling, allowing the system to scale smoothly to 500,000 req/sec.
- **Zero Origin Database Load:** PostgreSQL runs at $< 15\%$ CPU load during peak flash sales.
- **Stampede Immunity:** Edge micro-caching prevents thundering herd spikes during catalog browsing.

### Negative Consequences / Trade-offs:
- **Sub-bucket Imbalance Risk:** If requests are unevenly distributed, shard #1 might hit 0 while shard #2 still has 2 units remaining.
- **Mitigation:** The reservation client includes an automated single fallback hop: if `shard[hash % 10]` is empty, it attempts `shard[(hash + 1) % 10]` once before failing.
