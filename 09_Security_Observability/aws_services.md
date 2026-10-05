# SALESTORM 2026 — Comprehensive AWS Services Architecture & Reference Guide

**Document:** `09_Security_Observability/aws_services.md`  
**Project:** SALESTORM 2026 (Distributed High-Concurrency Flash Sale Architecture)  
**Target Region:** AWS `ap-south-1` (Mumbai)  
**Environment:** Production Cloud Deployment  

---

## 🏗️ Architectural Topology Overview

The SALESTORM AWS infrastructure is engineered for **sub-millisecond latency, zero-overselling guarantees, high availability across multiple availability zones (AZs), and automated horizontal scalability** under extreme flash sale traffic surges.

```
                                      AWS Cloud (Region: ap-south-1)
 ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │  Amazon VPC (10.0.0.0/16)                                                                              │
 │                                                                                                        │
 │   Internet Gateway (salestorm-igw)                                                                     │
 │         │                                                                                              │
 │   ┌─────▼──────────────────────────────────────────────────────────────────────────────────────────┐   │
 │   │ Public Subnets (ap-south-1a: 10.0.1.0/24 | ap-south-1b: 10.0.2.0/24)                           │   │
 │   │                                                                                                │   │
 │   │    ┌──────────────────────────────────────────────────────────────────────────────┐            │   │
 │   │    │ Application Load Balancer (salestorm-alb) — Port 80 (HTTP)                   │            │   │
 │   │    └───────────────────────┬───────────────────────────────┬──────────────────────┘            │   │
 │   │                            │                               │                                   │   │
 │   │    ┌───────────────────────▼───────┐               ┌───────▼──────────────────────┐            │   │
 │   │    │ ECS Task Replica 1 (Fargate)  │               │ ECS Task Replica 2 (Fargate) │            │   │
 │   │    │ Container: salestorm-api:8080 │               │ Container: salestorm-api:8080│            │   │
 │   │    └───────────────┬───────────────┘               └───────────────┬──────────────┘            │   │
 │   └────────────────────┼───────────────────────────────────────────────┼───────────────────────────┘   │
 │                        │                                               │                               │
 │   ┌────────────────────┼───────────────────────────────────────────────┼───────────────────────────┐   │
 │   │ Private Subnets (ap-south-1a: 10.0.10.0/24 | ap-south-1b: 10.0.11.0/24)                        │   │
 │   │                    │                                               │                           │   │
 │   │         ┌──────────▼───────────────────────────────────────────────▼──────────┐                │   │
 │   │         │                                                                     │                │   │
 │   │         │  ┌──────────────────────────────┐   ┌────────────────────────────┐  │                │   │
 │   │         │  │ Amazon RDS (PostgreSQL 16)   │   │ Amazon ElastiCache (Redis) │  │                │   │
 │   │         │  │ Relational persistence,      │   │ In-memory inventory atomic │  │                │   │
 │   │         │  │ orders, transactions & audit │   │ decrement & TTL leases     │  │                │   │
 │   │         │  │ Port 5432                    │   │ Port 6379                  │  │                │   │
 │   │         │  └──────────────────────────────┘   └────────────────────────────┘  │                │   │
 │   │         └─────────────────────────────────────────────────────────────────────┘                │   │
 │   └────────────────────────────────────────────────────────────────────────────────────────────────┘   │
 └────────────────────────────────────────────────────────────────────────────────────────────────────────┘
          │                                 │                                 │
 ┌────────▼──────────────┐        ┌─────────▼─────────────┐        ┌──────────▼───────────────┐
 │ Amazon ECR            │        │ AWS Secrets Manager   │        │ Amazon CloudWatch + SNS  │
 │ Immutable container   │        │ Centralized dynamic   │        │ Centralized telemetry,   │
 │ image registry        │        │ credential lifecycle  │        │ real-time alarm alerts   │
 └───────────────────────┘        └───────────────────────┘        └──────────────────────────┘
```

---

## 📋 Comprehensive Catalog of AWS Services Used

---

### 1. Amazon Virtual Private Cloud (Amazon VPC) & Networking Components
* **Service Category:** Networking & Content Delivery

#### What is it?
Amazon VPC lets you provision a logically isolated section of the AWS Cloud where you can launch AWS resources in a virtual network that you define. It provides complete control over IP address ranges, subnets, route tables, network gateways, and network access policies.

#### Why is it used in SALESTORM?
* **Network Isolation:** Isolates database (`RDS PostgreSQL`) and in-memory cache (`ElastiCache Redis`) from public internet access.
* **Multi-AZ Fault Tolerance:** Spread across two Availability Zones (`ap-south-1a` and `ap-south-1b`) so that the failure of a physical data center does not bring down the application.
* **Subnet Segmentation:**
  * `salestorm-public-1a` (`10.0.1.0/24`) & `salestorm-public-1b` (`10.0.2.0/24`): Host the internet-facing Load Balancer and public container ENIs.
  * `salestorm-private-1a` (`10.0.10.0/24`) & `salestorm-private-1b` (`10.0.11.0/24`): Host database and cache clusters with zero public route access.
* **Internet Gateway (`salestorm-igw`):** Connects VPC public subnets to the internet to receive client traffic and access AWS service APIs (ECR, Secrets Manager).
* **Route Tables (`salestorm-public-rt`):** Directs inbound and outbound public internet traffic (`0.0.0.0/0`) through the Internet Gateway.

---

### 2. AWS Security Groups (Stateful Virtual Firewalls)
* **Service Category:** Security, Identity, & Compliance

#### What is it?
Security Groups act as virtual firewalls at the instance/ENI level to control inbound and outbound traffic using explicit allow-rules.

#### Why is it used in SALESTORM?
Enforces the **Principle of Least Privilege (PoLP)** and zero-trust perimeter security between microservice layers:
1. **`salestorm-alb-sg` (ALB Security Group):**
   * Ingress: Allows HTTP (Port 80) and HTTPS (Port 443) from anywhere (`0.0.0.0/0`).
2. **`salestorm-ecs-sg` (ECS Fargate Security Group):**
   * Ingress: Accepts traffic **only** on port `8080` originating from `salestorm-alb-sg`. Direct public internet access to the containers is blocked.
   * Egress: Allows outbound HTTPS (Port 443) to communicate with ECR, Secrets Manager, and CloudWatch.
3. **`salestorm-rds-sg` (Database Security Group):**
   * Ingress: Accepts PostgreSQL traffic (Port 5432) **strictly** from `salestorm-ecs-sg`. The database cannot be reached from outside the VPC.
4. **`salestorm-redis-sg` (Redis Security Group):**
   * Ingress: Accepts Redis traffic (Port 6379) **strictly** from `salestorm-ecs-sg`.

---

### 3. Amazon Elastic Container Registry (Amazon ECR)
* **Service Category:** Containers

#### What is it?
Amazon ECR is a fully managed, high-performance container image registry that makes it easy to store, manage, share, and deploy Docker container images.

#### Why is it used in SALESTORM?
* **Immutable Artifact Deployment:** Stores the compiled production Docker image (`salestorm:latest`) containing the FastAPI application, dependencies, and database migrations.
* **High-Speed Fargate Ingestion:** Provides high-bandwidth, authenticated image pulling directly to ECS tasks within the same AWS region (`ap-south-1`).
* **Vulnerability Scanning (`scanOnPush=true`):** Automatically analyzes uploaded container images for OS package vulnerabilities and CVEs upon upload.

---

### 4. AWS Identity and Access Management (IAM)
* **Service Category:** Security, Identity, & Compliance

#### What is it?
AWS IAM is a web service that helps you securely control access to AWS resources. It provides fine-grained authorization, service roles, and access credentials.

#### Why is it used in SALESTORM?
* **`salestorm-ecs-execution-role`:**
  * Assumed by the AWS ECS Agent during container initialization.
  * Granted `AmazonECSTaskExecutionRolePolicy` to authenticate with ECR, pull container layers, and write logs to CloudWatch.
  * Granted `SecretsManagerReadWrite` to decrypt and retrieve database and cache credentials at runtime without exposing keys in plaintext.
* **`salestorm-ecs-task-role`:**
  * Assumed by the running FastAPI application container itself for any direct AWS SDK calls.
* **`AWSServiceRoleForECS`:**
  * System-linked role allowing ECS to coordinate VPC Elastic Network Interfaces (ENIs) and Application Load Balancer target registrations on behalf of the customer.

---

### 5. AWS Secrets Manager
* **Service Category:** Security, Identity, & Compliance

#### What is it?
AWS Secrets Manager is a secure credential storage service that protects secrets needed to access applications, APIs, and databases. It offers encryption at rest via AWS KMS and automated credential lifecycle management.

#### Why is it used in SALESTORM?
* **Zero-Secret Invariant:** Eliminates hardcoded credentials from Git repositories, Dockerfiles, and environment files.
* **Runtime Secret Injection:** 
  * `salestorm/database-url`: Stores the production PostgreSQL connection URI with master credentials.
  * `salestorm/redis-url`: Stores the ElastiCache Redis endpoint.
* **Dynamic Resolution:** During task bootstrap, ECS securely resolves the Secret ARNs directly into memory variables inside the container.

---

### 6. Amazon Relational Database Service (Amazon RDS — PostgreSQL 16)
* **Service Category:** Databases

#### What is it?
Amazon RDS is a managed relational database service that automates provisioning, patching, backup recovery, failure detection, and storage scaling.

#### Why is it used in SALESTORM?
* **ACID Compliance & Strong Consistency:** Guaranteed data integrity for financial orders, payment receipts, customer records, and reservation audit logs.
* **Engine:** PostgreSQL 16 on `db.t3.micro` with `gp2` SSD storage.
* **Private Subnet Placement:** Provisioned via `salestorm-db-subnet-group` spanning private subnets across `ap-south-1a` and `ap-south-1b`.
* **Reliability:** Automated automated maintenance and recovery with zero public internet exposure.

---

### 7. Amazon ElastiCache (Redis 7)
* **Service Category:** Databases / In-Memory Caching

#### What is it?
Amazon ElastiCache is a fully managed, in-memory caching service compatible with Redis. It delivers sub-millisecond response times for read/write operations.

#### Why is it used in SALESTORM?
* **Flash Sale Inventory Locking:** Acts as the high-throughput, low-latency front-line defense for flash sale stock.
* **Atomic Decrements (`DECR` / Lua Scripts):** Decrements inventory atomically at microsecond speeds, mathematically eliminating race conditions and overselling.
* **TTL Lease Expiration:** Implements temporary 5-minute reservation locks (`RESERVATION_LEASE_SECONDS=300`). If a user reserves an item but fails to complete payment, the stock automatically releases back into the pool.
* **Cluster Configuration:** Redis 7.0 engine on `cache.t3.micro` provisioned across `salestorm-redis-subnet`.

---

### 8. Application Load Balancer (ALB) & Elastic Load Balancing (ELBV2)
* **Service Category:** Networking & Content Delivery

#### What is it?
Application Load Balancers operate at Layer 7 (Application Layer) of the OSI model. They inspect HTTP/HTTPS headers, route traffic intelligently across target groups, and conduct continuous health monitoring.

#### Why is it used in SALESTORM?
* **Public Gateway:** Acts as the single entry point for all client web and mobile traffic (`salestorm-alb`).
* **High Availability Across AZs:** Distributes requests evenly between containers running in `ap-south-1a` and `ap-south-1b`.
* **Automated Health Checking:** Probes `/health` every 30 seconds. If an ECS container crashes or fails to respond, the ALB immediately stops routing traffic to that replica and redirects to healthy instances.
* **Zero-Downtime Rolling Deployments:** Coordinates with ECS during software updates to drain existing connections before cutting over to new container versions.

---

### 9. Amazon Elastic Container Service (Amazon ECS — Fargate Launch Type)
* **Service Category:** Containers / Serverless Compute

#### What is it?
Amazon ECS is a fully managed container orchestration service. When run with AWS Fargate, it becomes serverless compute: you deploy containers without provisioning, configuring, or scaling virtual machines.

#### Why is it used in SALESTORM?
* **Serverless Execution:** Eliminates EC2 instance management, OS patching, and host-level security maintenance.
* **Declarative Task Definitions (`salestorm-api`):** Defines CPU (0.5 vCPU), Memory (1024 MB), port mappings (`8080`), logging drivers, health probes, and Secrets Manager mappings.
* **Service Reliability (`salestorm-api-service`):** Maintains a desired count of 2 concurrent container replicas across distinct availability zones.
* **Native VPC Networking (`awsvpc`):** Every Fargate task gets its own dedicated Elastic Network Interface (ENI) and private IP within the VPC subnet.

---

### 10. Amazon CloudWatch (Logs, Metrics, Alarms)
* **Service Category:** Management & Governance

#### What is it?
Amazon CloudWatch provides unified monitoring and observability for AWS resources and applications. It collects logs, system metrics, and triggers automated remediation alarms.

#### Why is it used in SALESTORM?
* **Centralized Container Logging:** ECS tasks stream JSON logs to `/ecs/salestorm-api` in real time using the `awslogs` driver.
* **Correlation ID Tracing:** Every HTTP request log contains an `X-Correlation-ID` header, enabling end-to-end request tracing across distributed containers.
* **Metric Alarms:**
  1. `SALESTORM-HighCPU`: Alarms if ECS cluster average CPU utilization exceeds **80%** over 5 minutes.
  2. `SALESTORM-High5xxErrors`: Alarms if ALB records more than **10 HTTP 5xx server errors** in 60 seconds.
  3. `SALESTORM-LowDBStorage`: Alarms if RDS PostgreSQL free storage drops below **5 GB**.

---

### 11. Amazon Simple Notification Service (Amazon SNS)
* **Service Category:** Application Integration

#### What is it?
Amazon SNS is a managed publish/subscribe messaging service that facilitates message delivery to end-user endpoints like email, SMS, mobile push, and AWS Lambda functions.

#### Why is it used in SALESTORM?
* **Incident Alerting (`salestorm-alerts`):** Connects directly as the notification target (`--alarm-actions`) for all CloudWatch metric alarms.
* **Real-time DevOps Notifications:** Dispatches incident alerts directly to team on-call emails (`nithish.s.1622@gmail.com`) within seconds of an anomaly or outage.

---

### 12. AWS Application Auto Scaling
* **Service Category:** Management & Governance / Compute

#### What is it?
Application Auto Scaling enables automatic resource scaling for services like Amazon ECS tasks, DynamoDB tables, and Aurora replicas based on custom or predefined metric targets.

#### Why is it used in SALESTORM?
* **Handling Flash Sale Surges:** Normal web traffic runs on 2 baseline Fargate containers. When a flash sale goes live, thousands of concurrent requests arrive simultaneously.
* **Target Tracking Scaling Policy (`salestorm-cpu-scale-out`):**
  * Target Metric: `ECSServiceAverageCPUUtilization = 60.0%`.
  * Dynamic Range: **Minimum 2 containers, Maximum 20 containers**.
  * Scale-Out Cooldown: 60 seconds (rapid ramp-up when traffic spikes).
  * Scale-In Cooldown: 300 seconds (smooth ramp-down to prevent thrashing).

---

## 📊 Summary Comparison: Local vs. AWS Cloud Infrastructure

| Capability / Tier | Local Docker Compose Setup | AWS Cloud Architecture (SALESTORM 2026) | Key Architectural Advantage |
| :--- | :--- | :--- | :--- |
| **Compute / Orchestration** | Local `docker-compose up` | **Amazon ECS Fargate (Serverless)** | Zero server management, multi-AZ high availability |
| **Image Distribution** | Local image cache | **Amazon ECR** | Immutable image versioning with CVE vulnerability scanning |
| **Relational Storage** | Local `postgres:16` container | **Amazon RDS PostgreSQL 16 (gp2 SSD)** | Automated backups, multi-AZ resilience, managed patching |
| **In-Memory Cache** | Local `redis:7` container | **Amazon ElastiCache Redis 7** | Sub-millisecond atomic inventory lock & lease expiry |
| **Traffic Routing & Ingress** | Direct localhost port access | **Application Load Balancer (ALB)** | Layer 7 routing, health checks, zero-downtime rolling deploys |
| **Secrets & Keys** | Plaintext `.env` files | **AWS Secrets Manager + IAM** | Zero-secret invariant, KMS encryption, dynamic runtime injection |
| **Network Security** | Bridge network | **Amazon VPC + Security Groups** | Multi-tier subnet isolation and stateful virtual firewalls |
| **Observability & Alerts** | Terminal stdout/stderr | **CloudWatch Logs & Metrics + SNS** | Distributed tracing (`X-Correlation-ID`) & automated incident emails |
| **Scalability** | Fixed single container | **AWS Application Auto Scaling** | Automated scaling from 2 up to 20 containers on CPU spikes |
