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

The System Context diagram illustrates how SALESTORM fits into its external environment, interacting with customers, warehouse operators, and third-party SaaS providers.

```mermaid
C4Context
    title System Context Diagram (C4 Level 1) - SALESTORM Flash-Sale Platform

    Person(customer, "Customer", "Flash-sale buyer accessing platform via Mobile App or Web Browser")
    Person(operator, "Warehouse Operator", "Logistics personnel managing stock fulfillment and dispatch")

    Enterprise_Boundary(salestorm_boundary, "SALESTORM Enterprise Platform") {
        System(salestorm, "SALESTORM E-Commerce Core", "Handles catalog browsing, atomic reservations, payments, order lifecycle, and fulfillment")
    }

    System_Ext(payment_gateway, "Payment Gateway (Stripe/Adyen)", "Processes credit cards, UPI, digital wallets, and 3D Secure authentication")
    System_Ext(shipping_carrier, "Logistics & Carrier Partner (FedEx/DHL)", "Generates waybills, manifests, and real-time delivery tracking events")
    System_Ext(comms_gateway, "Notification Providers (Twilio/SendGrid)", "Dispatches SMS, OTP, Push notifications, and confirmation emails")

    Rel(customer, salestorm, "Browses products, places 10,000 concurrent Buy Now requests, completes payment", "HTTPS / TLS 1.3")
    Rel(operator, salestorm, "Updates physical inventory, manages pack & dispatch queues", "HTTPS / Internal Portal")
    Rel(salestorm, payment_gateway, "Initiates charges, authorizes payments, verifies webhooks", "HTTPS / REST API")
    Rel(salestorm, shipping_carrier, "Dispatches shipment manifests, fetches tracking milestones", "HTTPS / REST API")
    Rel(salestorm, comms_gateway, "Sends transactional SMS, WhatsApp, and email alerts", "HTTPS / REST API")
```

---

## Diagram 2: High-Level Architecture Diagram

The High-Level Architecture depicts the overall logical system topology, showcasing ingress security, caching tiers, microservice boundaries, synchronous vs. asynchronous paths, and transactional storage.

```mermaid
flowchart TB
    subgraph Ingress ["1. Ingress & Edge Protection Tier"]
        Users["10,000 Flash-Sale Clients"] -->|"HTTPS / TLS 1.3"| CDN["Edge CDN / WAF (DDoS & Bot Mitigation)"]
        CDN -->|"Scrubbed Traffic"| ALB["Application Load Balancer (ALB)"]
        ALB -->|"HTTP/2 Multiplexed"| APIGW["API Gateway Cluster (Auth, Rate Limiting, Routing)"]
    end

    subgraph SyncServices ["2. Synchronous Scarcity & Checkout Domain"]
        APIGW -->|"Read Query"| ProdSvc["Product Service"]
        APIGW -->|"Express Buy Now"| CheckSvc["Checkout Service"]
        APIGW -->|"Direct Cart Ops"| CartSvc["Cart Service"]

        CheckSvc -->|"gRPC Atomic Reserve"| InvSvc["Inventory Service"]
        CheckSvc -->|"HTTPS Authorize"| PaySvc["Payment Service"]
    end

    subgraph FastStorage ["3. In-Memory Contention Arbiter"]
        InvSvc <-->|"Atomic Lua Decrement"| RedisInv[("Redis Cluster\n(Stock Shards + Leases)")]
        ProdSvc <-->|"Read-Through Cache"| RedisCat[("Redis Catalog Cache")]
        CartSvc <-->|"Session Hash"| RedisCart[("Redis Cart Store")]
    end

    subgraph AsyncPipeline ["4. Asynchronous Event Pipeline (Durable Decoupling)"]
        PaySvc -->|"Outbox Emit: PaymentSuccessful"| MsgBroker{{"Distributed Message Broker\n(Kafka / Event Log)"}}
        InvSvc -->|"Outbox Emit: StockReserved"| MsgBroker
        
        MsgBroker -->|"Consumer: At-Least-Once"| OrdSvc["Order Service"]
        MsgBroker -->|"Consumer: Delivery Events"| ShipSvc["Shipment Service"]
        MsgBroker -->|"Consumer: Multi-Channel"| NotifSvc["Notification Service"]
    end

    subgraph DurableStorage ["5. Persistent ACID Datastores (RDBMS)"]
        InvSvc --- DB_Inv[("PostgreSQL\nInventory DB")]
        PaySvc --- DB_Pay[("PostgreSQL\nPayment DB")]
        OrdSvc --- DB_Ord[("PostgreSQL\nOrder DB")]
        ShipSvc --- DB_Ship[("PostgreSQL\nShipment DB")]
    end

    subgraph External ["6. External Enterprise Gateways"]
        PaySvc <-->|"PCI Tokenized Charge"| ExtPay["Payment Gateway\n(Max 2,000 TPS)"]
        ShipSvc <-->|"API Manifest"| ExtShip["Carrier API"]
        NotifSvc -->|"SMTP / SMS API"| ExtNotif["Notification Provider"]
    end

    classDef ingress fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef sync fill:#e8f5e9,stroke:#388e3c,stroke-width:2px;
    classDef async fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef storage fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
    classDef external fill:#eceff1,stroke:#607d8b,stroke-width:2px;

    class Users,CDN,ALB,APIGW ingress;
    class ProdSvc,CheckSvc,CartSvc,InvSvc,PaySvc sync;
    class MsgBroker,OrdSvc,ShipSvc,NotifSvc async;
    class RedisInv,RedisCat,RedisCart,DB_Inv,DB_Pay,DB_Ord,DB_Ship storage;
    class ExtPay,ExtShip,ExtNotif external;
```

---

## Diagram 3: Container / Service Diagram (C4 Level 2)

This diagram details the containerized microservices, their runtime communication protocols, and their private encapsulated datastores.

```mermaid
C4Container
    title Container Diagram (C4 Level 2) - Microservice Architecture & Protocols

    Person(user, "User Mobile/Web App", "Interacts via REST APIs and WebSocket push channels")

    Container(api_gw, "API Gateway Cluster", "Envoy / Go Gateway", "Performs JWT validation, rate-limiting, CORS, and TLS termination")

    Container(prod_svc, "Product Service", "Node.js / Go", "Serves catalog metadata and cached stock indicators")
    Container(inv_svc, "Inventory Service", "Java / Spring Boot", "Executes atomic reservation engine and lease tracking")
    Container(check_svc, "Checkout Service", "Go / gRPC", "Orchestrates order context and checkout sessions")
    Container(pay_svc, "Payment Service", "Go / Java", "Integrates with payment processors and guarantees payment idempotency")
    Container(ord_svc, "Order Service", "Java / Spring Boot", "Maintains canonical immutable order records and state lifecycle")
    Container(ship_svc, "Shipment Service", "Python / Go", "Handles logistics batching, carrier manifest generation, and tracking")
    Container(notif_svc, "Notification Service", "Node.js Worker", "Dispatches transactional emails, push notifications, and SMS")

    ContainerDb(redis_cluster, "Distributed Cache / Redis Cluster", "Redis 7.x", "In-memory atomic Lua scripts, active leases, sorted sets")
    ContainerDb(inv_db, "Inventory Database", "PostgreSQL 16", "ACID storage for stock balances, reservation logs, outbox")
    ContainerDb(pay_db, "Payment Database", "PostgreSQL 16", "PCI-compliant transaction audit log, idempotency keys")
    ContainerDb(ord_db, "Order Database", "PostgreSQL 16", "Canonical order aggregates, line items, order history")

    ContainerQueue(kafka, "Message Broker", "Apache Kafka / Durable Log", "High-throughput partitioned event streaming bus")

    Rel(user, api_gw, "API Calls", "HTTPS / JSON")
    Rel(api_gw, prod_svc, "Catalog requests", "HTTP/REST")
    Rel(api_gw, check_svc, "Buy Now / Checkout", "HTTP/REST")
    Rel(check_svc, inv_svc, "Reserve stock", "gRPC / Protobuf")
    Rel(check_svc, pay_svc, "Initiate payment", "gRPC / Protobuf")

    Rel(inv_svc, redis_cluster, "Atomic decrement / lease check", "RESP Protocol")
    Rel(inv_svc, inv_db, "Persist confirmed reservations", "JDBC / SQL")
    Rel(pay_svc, pay_db, "Record transaction states", "JDBC / SQL")
    Rel(pay_svc, kafka, "Publish: PaymentSuccessfulEvent", "TCP / Kafka Protocol")
    Rel(ord_svc, kafka, "Subscribe: PaymentSuccessfulEvent", "TCP / Kafka Protocol")
    Rel(ord_svc, ord_db, "Persist confirmed order", "JDBC / SQL")
    Rel(ord_svc, kafka, "Publish: OrderCreatedEvent", "TCP / Kafka Protocol")
    Rel(ship_svc, kafka, "Subscribe: OrderCreatedEvent", "TCP / Kafka Protocol")
    Rel(notif_svc, kafka, "Subscribe: System Events", "TCP / Kafka Protocol")
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
