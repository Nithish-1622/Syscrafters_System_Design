# SALESTORM — Official Architecture Diagrams Specification

**Document Version:** 1.0.0  
**Status:** Approved Architecture Baseline  
**Lead Author:** Member 1 (System Architect + Concurrency, Inventory & Scalability Lead)  
**Target Audience:** Core Engineering Team (Members 2, 3, 4), Technical Jury, Operations  

---

## Architectural Diagram Index

This document provides the canonical set of 8 system architecture diagrams required by the SALESTORM Hackathon Brief:

1. **[Diagram 1: System Context Diagram (C4 Level 1)](#diagram-1-system-context-diagram-c4-level-1)**
2. **[Diagram 2: High-Level Architecture Diagram](#diagram-2-high-level-architecture-diagram)**
3. **[Diagram 3: Container / Service Diagram (C4 Level 2)](#diagram-3-container--service-diagram-c4-level-2)**
4. **[Diagram 4: Component-Level Architecture for Critical Flow (C4 Level 3)](#diagram-4-component-level-architecture-for-critical-flow-c4-level-3)**
5. **[Diagram 5: Logical Deployment & Infrastructure Topology](#diagram-5-logical-deployment--infrastructure-topology)**
6. **[Diagram 6: High-Traffic Request Flow (10,000 Contenders)](#diagram-6-high-traffic-request-flow-10000-contenders)**
7. **[Diagram 7: Inventory Concurrency & Last-Unit Serialization](#diagram-7-inventory-concurrency--last-unit-serialization)**
8. **[Diagram 8: Failure Handling & Order Recovery Architecture](#diagram-8-failure-handling--order-recovery-architecture)**

---

## Diagram 1: System Context Diagram (C4 Level 1)

The System Context diagram illustrates how SALESTORM fits into its external environment, interacting with customers, warehouse operators, and third-party SaaS providers without line collisions or overlapping text.

```mermaid
flowchart TB
    subgraph Actors ["1. Users & Personas"]
        direction LR
        Customer["👤 Flash-Sale Customer<br/><b>10,000 Concurrent Buyers</b><br/>Mobile App & Web Browser"]
        Operator["👷 Warehouse Operator<br/><b>Logistics & Dispatch</b><br/>Internal Admin Portal"]
    end

    subgraph Boundary ["2. SALESTORM Enterprise Platform Boundary"]
        Core["⚡ SALESTORM E-Commerce Core Engine<br/>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━<br/>• Sub-5ms Atomic Inventory Reservation Engine<br/>• Real-Time Flash-Sale Catalog & Traffic Gate<br/>• Idempotent Payment & Outbox Orchestrator<br/>• Event-Driven Order State Machine & Fulfillment"]
    end

    subgraph ExternalSaaS ["3. External Partner Ecosystem (Third-Party SaaS)"]
        direction LR
        PayGW["💳 Payment Gateway<br/><b>Stripe / Adyen</b><br/>Tokenized Charges & 3DS"]
        Carrier["🚚 Logistics Carrier<br/><b>FedEx / DHL</b><br/>Waybills & Tracking"]
        Comms["📲 Comms Provider<br/><b>Twilio / SendGrid</b><br/>SMS, Push & Email Alerts"]
    end

    Customer ==>|"HTTPS / TLS 1.3<br/>10k Concurrent Buy-Now"| Core
    Operator ==>|"Internal HTTPS<br/>Inventory & Restock"| Core

    Core -->|"REST API / Webhooks<br/>Auth & Charge"| PayGW
    Core -->|"REST API<br/>Manifest Dispatch"| Carrier
    Core -->|"Async REST<br/>Transactional Alerts"| Comms

    classDef actorStyle fill:#1e3a8a,stroke:#3b82f6,stroke-width:2px,color:#ffffff;
    classDef coreStyle fill:#065f46,stroke:#10b981,stroke-width:2px,color:#ffffff;
    classDef extStyle fill:#374151,stroke:#9ca3af,stroke-width:2px,color:#ffffff;

    class Customer,Operator actorStyle;
    class Core coreStyle;
    class PayGW,Carrier,Comms extStyle;
```

---

## Diagram 2: High-Level Architecture Diagram

The High-Level Architecture depicts the overall logical system topology, showcasing ingress security, caching tiers, microservice boundaries, synchronous vs. asynchronous paths, and transactional storage.

```mermaid
flowchart TB
    subgraph IngressTier ["1. Ingress & Edge Protection Tier"]
        Users["👥 10,000 Flash-Sale Clients"] -->|"HTTPS / TLS 1.3"| CDN["🛡️ Edge CDN / WAF<br/>DDoS Mitigation & Bot Shield"]
        CDN -->|"Scrubbed Traffic"| ALB["⚖️ Application Load Balancer (ALB)<br/>SSL Termination & Health Checks"]
        ALB -->|"HTTP/2 Forward"| APIGW["🚪 API Gateway Cluster<br/>JWT Auth, Token Bucket Rate Limiting"]
    end

    subgraph SyncTier ["2. Synchronous Scarcity & Checkout Domain"]
        APIGW -->|"Product Read"| ProdSvc["📦 Product Service<br/>Catalog & Stock Cache"]
        APIGW -->|"Express Buy-Now"| CheckSvc["⚡ Checkout Service<br/>Session Orchestrator"]
        
        CheckSvc -->|"gRPC Call"| InvSvc["🎯 Inventory Service<br/>Atomic Lua Engine"]
        CheckSvc -->|"REST / HTTPS"| PaySvc["💳 Payment Service<br/>Idempotent Processor"]
    end

    subgraph FastTier ["3. In-Memory Contention Arbiter"]
        InvSvc <-->|"Atomic Lua Script<br/>DECRBY stock"| RedisInv[("⚡ Redis 7.x Cluster<br/>Stock Shards & 300s Leases")]
        ProdSvc <-->|"Read-Through"| RedisCat[("⚡ Redis Catalog Cache")]
    end

    subgraph AsyncTier ["4. Durable Event Bus (Decoupling Tier)"]
        InvSvc -.->|"Outbox: StockReserved"| Broker{{"📬 Distributed Event Bus<br/>Kafka / Persistent Outbox Stream"}}
        PaySvc -.->|"Outbox: PaymentSuccessful"| Broker
        
        Broker ==>|"Event Stream"| OrdSvc["📋 Order Service<br/>Idempotent Consumer"]
        Broker ==>|"Event Stream"| ShipSvc["🚚 Shipment Service<br/>Batch Logistics"]
        Broker ==>|"Event Stream"| NotifSvc["🔔 Notification Service<br/>Multi-channel Push"]
    end

    subgraph StorageTier ["5. ACID Relational Databases (Private Subnets)"]
        InvSvc --- DB_Inv[("💾 Inventory DB<br/>PostgreSQL 16")]
        PaySvc --- DB_Pay[("💾 Payment DB<br/>PostgreSQL 16")]
        OrdSvc --- DB_Ord[("💾 Order DB<br/>PostgreSQL 16")]
    end

    subgraph ExtTier ["6. External Enterprise Services"]
        PaySvc <-->|"PCI Token Charge"| ExtPay["💳 Stripe / Adyen<br/>(Max 2,000 TPS)"]
        ShipSvc <-->|"Carrier API"| ExtShip["🚚 FedEx / DHL"]
        NotifSvc -->|"Webhooks"| ExtNotif["📲 Twilio / SendGrid"]
    end

    classDef ingressStyle fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef syncStyle fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#f8fafc;
    classDef storageStyle fill:#312e81,stroke:#818cf8,stroke-width:2px,color:#f8fafc;
    classDef asyncStyle fill:#78350f,stroke:#fbbf24,stroke-width:2px,color:#f8fafc;
    classDef extStyle fill:#374151,stroke:#9ca3af,stroke-width:2px,color:#f8fafc;

    class Users,CDN,ALB,APIGW ingressStyle;
    class ProdSvc,CheckSvc,InvSvc,PaySvc syncStyle;
    class RedisInv,RedisCat,DB_Inv,DB_Pay,DB_Ord storageStyle;
    class Broker,OrdSvc,ShipSvc,NotifSvc asyncStyle;
    class ExtPay,ExtShip,ExtNotif extStyle;
```

---

## Diagram 3: Container / Service Diagram (C4 Level 2)

This diagram details the containerized microservices, their runtime communication protocols, and their private encapsulated datastores arranged in distinct, non-overlapping architectural layers.

```mermaid
flowchart TB
    subgraph ClientLayer ["Layer 1: Client Applications & Presentation"]
        direction LR
        MobileApp["📱 Mobile App<br/>(iOS / Android Native)"]
        WebApp["💻 Web Storefront<br/>(Next.js / React SPA)"]
    end

    subgraph GatewayLayer ["Layer 2: Edge & API Gateway Container"]
        APIGW["🚪 API Gateway Container<br/>[Envoy / FastAPI Ingress Proxy]<br/>• TLS 1.3 Termination • JWT Token Validation<br/>• Per-IP Rate Limiting (Token Bucket) • Request Routing"]
    end

    subgraph SyncServiceLayer ["Layer 3: Core Containerized Microservices (Stateless)"]
        direction LR
        InvContainer["🎯 Inventory Service<br/>[Docker / FastAPI]<br/>• Atomic Reservation<br/>• Lua Engine Driver<br/>• Outbox Event Producer"]
        CheckContainer["⚡ Checkout Service<br/>[Docker / FastAPI]<br/>• Cart Aggregation<br/>• Checkout Session<br/>• Flow Orchestrator"]
        PayContainer["💳 Payment Service<br/>[Docker / FastAPI]<br/>• Idempotency Engine<br/>• Gateway Integration<br/>• Outbox Event Producer"]
    end

    subgraph InMemAndQueueLayer ["Layer 4: In-Memory Arbiter & Event Bus"]
        direction LR
        RedisContainer[("⚡ Distributed In-Memory Cache<br/>[Docker / Redis 7.x Alpine]<br/>• Atomic Lua Stock Decrement<br/>• 300-Second Lease TTL Manager<br/>• Read-Through Catalog Cache")]
        QueueContainer{{"📬 High-Throughput Event Streaming Bus<br/>[Docker / Apache Kafka or Async Broker]<br/>• Topic: payment-events (Partitions 0..3)<br/>• Topic: order-events (Partitions 0..3)<br/>• Topic: inventory-events"}}
    end

    subgraph AsyncServiceLayer ["Layer 5: Asynchronous Consumer Microservices"]
        direction LR
        OrdContainer["📋 Order Service<br/>[Docker / FastAPI & Worker]<br/>• Idempotent Inbox Consumer<br/>• Order State Machine (CONFIRMED)<br/>• Fulfillment Dispatch Trigger"]
        ShipContainer["🚚 Shipment Service<br/>[Docker Worker]<br/>• Waybill Generator<br/>• Carrier Manifest Batcher"]
        NotifContainer["🔔 Notification Service<br/>[Docker Worker]<br/>• SMS / WhatsApp Relay<br/>• Email Receipt Dispatcher"]
    end

    subgraph DatabaseLayer ["Layer 6: Isolated Relational Datastores (ACID Persistence)"]
        direction LR
        InvDB[("💾 Inventory Datastore<br/>[PostgreSQL 16]<br/>• inventory_items<br/>• reservations (TTL)<br/>• inventory_outbox")]
        PayDB[("💾 Payment Datastore<br/>[PostgreSQL 16]<br/>• payment_records<br/>• idempotency_keys<br/>• payment_outbox")]
        OrdDB[("💾 Order Datastore<br/>[PostgreSQL 16]<br/>• customer_orders<br/>• order_line_items<br/>• processed_inbox")]
    end

    %% Layer Connections - Clean, Vertical, Labelled
    MobileApp & WebApp -->|"HTTPS / REST API"| APIGW

    APIGW -->|"POST /reserve"| InvContainer
    APIGW -->|"POST /checkout"| CheckContainer
    APIGW -->|"POST /payments"| PayContainer

    CheckContainer -->|"Internal gRPC / REST"| InvContainer
    CheckContainer -->|"Internal gRPC / REST"| PayContainer

    InvContainer <==>|"RESP Protocol<br/>EVALSHA Atomic Lua"| RedisContainer
    InvContainer -->|"SQL / Transactional Outbox"| InvDB

    PayContainer -->|"SQL / ACID Insert"| PayDB
    PayContainer -.->|"Emit PaymentSuccessful"| QueueContainer

    QueueContainer ==>|"Subscribe: PaymentSuccessful"| OrdContainer
    QueueContainer ==>|"Subscribe: OrderCreated"| ShipContainer
    QueueContainer ==>|"Subscribe: SystemEvents"| NotifContainer

    OrdContainer -->|"SQL / Idempotent Commit"| OrdDB

    classDef client fill:#1e293b,stroke:#64748b,stroke-width:2px,color:#f8fafc;
    classDef gw fill:#0f172a,stroke:#0284c7,stroke-width:2px,color:#f8fafc;
    classDef sync fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#f8fafc;
    classDef mid fill:#312e81,stroke:#6366f1,stroke-width:2px,color:#f8fafc;
    classDef async fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#f8fafc;
    classDef db fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#f8fafc;

    class MobileApp,WebApp client;
    class APIGW gw;
    class InvContainer,CheckContainer,PayContainer sync;
    class RedisContainer,QueueContainer mid;
    class OrdContainer,ShipContainer,NotifContainer async;
    class InvDB,PayDB,OrdDB db;
```

---

## Diagram 4: Component-Level Architecture for Critical Flow (C4 Level 3)

Zooming inside the **Inventory Service** and **Payment-to-Order Pipeline** to highlight internal components, thread pools, and data boundaries.

```mermaid
flowchart LR
    subgraph InventoryService ["Inventory Service Boundary"]
        ResController["Reservation Controller\n(gRPC / REST)"]
        IdempFilter["Idempotency Filter\n(Token Check)"]
        LuaEngine["Atomic Lua Script Runner\n(Single-Threaded Arbiter)"]
        LeaseManager["Reservation Lease Manager\n(300s TTL Tracker)"]
        InvOutbox["Transactional Outbox Writer\n(SQL Insert)"]
    end

    subgraph PaymentOrderPipeline ["Payment to Order Ingestion Boundary"]
        PayWebhook["Payment Webhook Handler\n(HMAC Verification)"]
        PayTxManager["Payment Transaction Manager\n(Idempotent Commit)"]
        EventPublisher["Outbox CDC / Relayer\n(Debezium / Poller)"]
        OrdConsumer["Order Event Consumer\n(At-Least-Once Consumer)"]
        InboxGuard["Idempotent Inbox Guard\n(Duplicate Message Filter)"]
        OrdProcessor["Order Aggregate Factory\n(State Engine)"]
    end

    ResController --> IdempFilter
    IdempFilter --> LuaEngine
    LuaEngine --> LeaseManager
    LeaseManager --> InvOutbox

    PayWebhook --> PayTxManager
    PayTxManager --> EventPublisher
    EventPublisher -->|Kafka Topic| OrdConsumer
    OrdConsumer --> InboxGuard
    InboxGuard --> OrdProcessor
```

---

## Diagram 5: Logical Deployment & Infrastructure Topology

This topology represents a cloud-agnostic, multi-Availability Zone (AZ) production deployment, structured specifically for Member 4 to map into AWS.

```mermaid
flowchart TB
    subgraph PublicEdge ["Edge & Content Delivery Network"]
        Clients["Worldwide Customers"] --> Anycast["Anycast DNS / Edge CDN PoPs"]
        Anycast --> WAF["Cloud WAF & DDoS Shield"]
    end

    subgraph RegionalIngress ["Multi-AZ Ingress Layer"]
        WAF --> ExtLB["Public Application Load Balancer (ALB)"]
        ExtLB --> APIGateway1["API Gateway Pod (AZ-A)"]
        ExtLB --> APIGateway2["API Gateway Pod (AZ-B)"]
        ExtLB --> APIGateway3["API Gateway Pod (AZ-C)"]
    end

    subgraph AppMeshTier ["Kubernetes Stateless Microservices Cluster"]
        APIGateway1 & APIGateway2 & APIGateway3 --> SvcMesh["Service Mesh (mTLS & Envoy Sidecars)"]
        
        subgraph AZ_A ["Availability Zone A"]
            InvSvc_A["Inventory Pod A"]
            CheckSvc_A["Checkout Pod A"]
            PaySvc_A["Payment Pod A"]
            OrdSvc_A["Order Consumer A"]
        end

        subgraph AZ_B ["Availability Zone B"]
            InvSvc_B["Inventory Pod B"]
            CheckSvc_B["Checkout Pod B"]
            PaySvc_B["Payment Pod B"]
            OrdSvc_B["Order Consumer B"]
        end

        SvcMesh --> AZ_A & AZ_B
    end

    subgraph DataTier ["High-Availability Data & State Tier"]
        subgraph RedisCluster ["In-Memory Distributed Cluster"]
            RedisMaster["Redis Primary (Shard 1 - Writes)"]
            RedisReplica["Redis Replica (AZ-B - Reads/Failover)"]
            RedisMaster -.->|In-Memory Sync| RedisReplica
        end

        subgraph KafkaCluster ["Durable Partitioned Log Cluster"]
            KafkaBroker1["Broker Node 1 (AZ-A)"]
            KafkaBroker2["Broker Node 2 (AZ-B)"]
            KafkaBroker3["Broker Node 3 (AZ-C)"]
        end

        subgraph PostgreSQLCluster ["ACID Transactional Relational Tier"]
            PgMaster[("PostgreSQL Primary (AZ-A - Writes)")]
            PgStandby[("PostgreSQL Standby (AZ-B - Sync Rep)")]
            PgPool["PgBouncer Connection Pooler Cluster"]
            PgMaster -.->|Synchronous WAL Streaming| PgStandby
            PgPool --> PgMaster
        end
    end

    AZ_A & AZ_B --> RedisMaster
    AZ_A & AZ_B --> KafkaBroker1 & KafkaBroker2
    AZ_A & AZ_B --> PgPool
```

---

## Diagram 6: High-Traffic Request Flow (10,000 Contenders)

A comprehensive sequence walkthrough showing what happens when 10,000 users hit "Buy Now" at $t = 0$.

```mermaid
sequenceDiagram
    autonumber
    actor Fast100 as Customers 1-100 (First Mover)
    actor Excess9900 as Customers 101-10,000
    participant GW as API Gateway Tier
    participant CS as Checkout Service
    participant IS as Inventory Service
    participant Redis as Redis Lua Engine (stock=100)
    participant DB as PostgreSQL Inventory DB
    participant Pay as Payment Service

    Note over Fast100, Excess9900: t = 0ms: 10,000 Concurrent Requests Hit Ingress

    par 10,000 Simultaneous Buy Now Requests
        Fast100->>GW: POST /api/v1/buy-now (IdempotencyKey, SKU_X)
        Excess9900->>GW: POST /api/v1/buy-now (IdempotencyKey, SKU_X)
    end

    GW->>GW: Rate Limiting & JWT Claims Validation
    GW->>CS: Forward Validated Requests
    CS->>IS: gRPC reserveStock(SKU_X, qty=1, lease=300s)

    Note over IS, Redis: Single-Threaded Atomic Serialization Window (t = 40ms to 90ms)

    loop First 100 Requests
        IS->>Redis: EVALSHA lua_reserve(stock:item:X, 1, res_id)
        Redis-->>IS: Return 1 (SUCCESS, stock: 100 -> 0)
        IS->>DB: INSERT reservation (status='RESERVED', expires_at=now+300s)
        IS-->>CS: Reservation Granted (reservation_id, expires_at)
        CS-->>Fast100: HTTP 200 OK (Proceed to Payment Screen)
    end

    loop Remaining 9,900 Requests
        IS->>Redis: EVALSHA lua_reserve(stock:item:X, 1, res_id)
        Redis-->>IS: Return 0 (OUT OF STOCK, stock <= 0)
        IS-->>CS: Out of Stock Signal
        CS-->>Excess9900: HTTP 409 Conflict ("Flash Sale Sold Out")
    end

    Note over Fast100, Pay: 100 Successful Users Proceed to Payment within 300s Window
    Fast100->>Pay: POST /api/v1/payments/authorize (reservation_id, card_token)
```

---

## Diagram 7: Inventory Concurrency & Last-Unit Serialization

The exact microscopic timeline demonstrating deterministic tie-breaking when two concurrent requests arrive for the final remaining unit ($N = 1$).

```mermaid
sequenceDiagram
    autonumber
    actor UserA as Customer A (Arrives t = 100.001ms)
    actor UserB as Customer B (Arrives t = 100.002ms)
    participant Net as Network Multiplexer
    participant RedisQueue as Redis Command Buffer
    participant LuaVM as Redis Lua Execution VM
    participant Store as Memory Keyspace (stock=1)

    UserA->>Net: Send Request A (Buy 1 Unit)
    UserB->>Net: Send Request B (Buy 1 Unit)

    Net->>RedisQueue: Enqueue Command A
    Net->>RedisQueue: Enqueue Command B (1 millisecond later)

    Note over RedisQueue, LuaVM: Redis Single-Threaded Event Loop Pulls Next Command

    RedisQueue->>LuaVM: Execute Script for Command A
    activate LuaVM
    LuaVM->>Store: GET stock:item:X -> Returns 1
    Note over LuaVM: Condition check: 1 >= 1 (TRUE)
    LuaVM->>Store: DECRBY stock:item:X 1 -> Stock becomes 0
    LuaVM->>Store: HSET active_reservations res_A lease_data
    LuaVM-->>UserA: RETURN 1 (SUCCESS - Unit Reserved!)
    deactivate LuaVM

    Note over RedisQueue, LuaVM: Redis Pulls Next Command from Queue

    RedisQueue->>LuaVM: Execute Script for Command B
    activate LuaVM
    LuaVM->>Store: GET stock:item:X -> Returns 0
    Note over LuaVM: Condition check: 0 >= 1 (FALSE)
    LuaVM-->>UserB: RETURN 0 (FAILED - Sold Out!)
    deactivate LuaVM

    Note over UserA, UserB: Zero Race Condition, Zero Overselling, Deterministic Result
```

---

## Diagram 8: Failure Handling & Order Recovery Architecture

Demonstrating the exact architecture solving the critical test scenario: **Payment succeeds, but Order Service is crashed/unavailable for 30 seconds**.

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer
    participant PaySvc as Payment Service
    participant PayDB as Payment DB & Outbox
    participant Broker as Kafka Broker (Durable Log)
    participant OrdSvc as Order Service (CRASHED for 30s)
    participant OrdDB as Order Database
    participant Recon as Reconciliation Worker

    Customer->>PaySvc: Submit Payment (reservation_id, payment_token)
    PaySvc->>PaySvc: Authorize with External Gateway -> SUCCESS

    Note over PaySvc, PayDB: Atomic Transaction: Payment Record + Transactional Outbox
    PaySvc->>PayDB: BEGIN TRANSACTION<br/>UPDATE payment SET status='PAID'<br/>INSERT INTO outbox_events ('PaymentSuccessfulEvent')<br/>COMMIT TRANSACTION
    PaySvc-->>Customer: HTTP 200 OK ("Payment Successful! Generating Order...")

    PayDB->>Broker: Outbox Relayer publishes PaymentSuccessfulEvent to Topic
    Note over Broker: Event durably persisted across 3 replicated broker disks

    Note over OrdSvc: [CRASH EVENT]: Pod OOM / Hardware Failure! Unavailable for 30 seconds.

    Broker--xOrdSvc: Attempt Delivery (Fails - Consumer Unreachable)
    Note over Broker: Event is NOT lost! Offset pointer remains uncommitted.

    Note over OrdSvc: t = 30s: Kubernetes Auto-Heals Pod. Order Service Restarts & Health OK.

    OrdSvc->>Broker: Reconnect to Consumer Group & Poll Uncommitted Offsets
    Broker->>OrdSvc: Deliver Retained PaymentSuccessfulEvent

    Note over OrdSvc, OrdDB: Idempotent Order Creation via Inbox Pattern
    OrdSvc->>OrdDB: BEGIN TRANSACTION<br/>INSERT INTO processed_inbox (event_id) VALUES ('evt_123')<br/>INSERT INTO orders (order_id, status='CONFIRMED', reservation_id)<br/>COMMIT TRANSACTION

    OrdSvc->>Broker: Commit Consumer Offset (ACK)
    OrdSvc->>Broker: Publish OrderCreatedEvent (Fulfillment & Notifications continue)

    opt Secondary Safety Net (If Broker Partitioned)
        Recon->>PayDB: Query unfulfilled payments older than 60s
        Recon->>OrdSvc: Direct REST/gRPC idempotent order reconciliation
    end

    Note over Customer, OrdSvc: Result: 100% Data Integrity, Zero Lost Orders, Zero Erroneous Refunds
```

---

*End of 03_Architecture_Diagrams.md — Authoritative Visual Architecture Specification.*
