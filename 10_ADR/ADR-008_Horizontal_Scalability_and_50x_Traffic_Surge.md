# ADR-008: Horizontal Scalability Architecture & 50× Traffic Surge

**Status:** Approved  
**Date:** 2026-10-05  
**Author:** Member 1 (System Architect)  
**Deciders:** Core Engineering Team  

---

## 1. Context & Problem Statement
The SALESTORM platform must transition smoothly from **steady-state baseline traffic of 10,000 requests/sec** to **peak flash-sale bursts of 500,000 requests/sec** (a 50× increase). 
A system designed purely for steady-state traffic will instantly collapse under a 50× surge due to:
- CPU saturation on stateless compute pods.
- Epoll listener thread and socket exhaustion on API Gateways.
- Connection starvation on databases.
- Backpressure cascading backward into user-facing ingress.

We must formulate an architectural scalability blueprint that defines how every tier expands dynamically and sheds load gracefully.

---

## 2. Options Considered

### Option 1: Vertical Scaling (Bigger Virtual Machines)
- **Description:** Provisioning larger cloud instances (e.g., upgrading from 16 vCPU to 128 vCPU machines) prior to the sale.
- **Pros:** No distributed state orchestration needed; simpler topology.
- **Cons:** Hard hardware ceilings; exponential cloud cost; still suffers from single-lock contention inside database kernels; does not solve the 500,000 req/s network packet processing limit.

### Option 2: Reactive Horizontal Pod Autoscaling (HPA) Alone
- **Description:** Relying entirely on Kubernetes standard HPA based on CPU/Memory metrics.
- **Pros:** Standard container orchestration pattern.
- **Cons:** Container spin-up and JVM/Node warmup takes 45–90 seconds. A flash sale burst happens in $< 2\text{ seconds}$. By the time reactive autoscaling triggers, the flash sale is already over and the system has already crashed.

### Option 3: Scheduled Predictive Pre-Warming + Edge Traffic Shedding + Horizontal Data Partitioning (Selected)
- **Description:** 
  - **Pre-Warming:** Fleet scaled up 15 minutes before the scheduled flash sale start time.
  - **Stateless Auto-Expansion:** Compute tiers expand horizontally (10 $\rightarrow$ 120 pods) across multiple Availability Zones.
  - **CQRS Read Offloading:** Read queries route to 8 read replicas; writes are strictly limited to the primary.
  - **Edge Traffic Shedding:** Leaky bucket rate limiters drop excess non-essential traffic at the gateway edge.
- **Pros:** Zero warmup lag; handles 500k RPS smoothly; protects transactional databases from unmitigated write bursts.
- **Cons:** Incurs cloud infrastructure costs during the pre-warmed window (mitigated by scheduled scale-down 15 minutes after sale close).

---

## 3. Decision
We adopt **Option 3: Scheduled Predictive Pre-Warming + Edge Traffic Shedding + Horizontal Partitioning**.

### Technical Architecture Specifications:
1. **Pre-Sale Scheduled Scale Event ($T - 15\text{ mins}$):**  
   Kubernetes CronJob adjusts HPA `minReplicas`:
   - API Gateway: 10 $\rightarrow$ 120 pods.
   - Inventory Service: 8 $\rightarrow$ 80 pods.
   - Checkout Service: 8 $\rightarrow$ 60 pods.
   - Kafka Partitions: Pre-partitioned to 64 partitions.
2. **Stateless Pods & Zero Session Affinity:**  
   Load balancers use round-robin with least-connections distribution. No state is held in pod local memory, allowing pods to be created or killed without customer session disruption.
3. **Database Concurrency Isolation:**  
   PostgreSQL connection poolers (`PgBouncer`) maintain a hard ceiling of 300 active connections to the primary master. Compute pods can scale to 500 instances without overwhelming database connection limits.
4. **Graceful Degradation / Traffic Shedding:**  
   If ingress reaches 550,000 req/sec ($> 110\%$ of peak capacity), the API Gateway sheds low-priority traffic:
   - Search suggestions, personalized recommendations, and reviews are temporarily disabled (HTTP 200 with empty payload).
   - Core checkout, reservation, and payment flows receive 100% of network and compute resources.

---

## 4. Architectural Consequences & Trade-offs

### Positive Consequences:
- **Resilience to 50× Shock:** The platform absorbs 500,000 requests/sec with zero latency degradation on the core reservation path.
- **Predictable Cost:** Infrastructure scales up only for the defined 30-minute flash-sale window, minimizing operational expenses.
- **Safe Database Operation:** Database CPU stays $< 20\%$ because non-essential queries and excess contention are filtered at the edge.

### Negative Consequences / Trade-offs:
- **Operational Discipline Required:** The business must configure and schedule flash-sale campaigns in advance to allow automated pre-warming triggers to execute.
- **Mitigation:** If an unscheduled flash sale occurs, Edge Token Shedding instantly protects the system by admitting only a safe slice of traffic while reactive HPA spins up supplementary pods.
