# SALESTORM 2026 — AWS Cloud Deployment Guide
## Developer 4: Security, Observability & Cloud Infrastructure

**Document Version:** 1.0.0  
**Author:** Member 1 (System Architect) — For Dev4 Handoff  
**Target:** Host SALESTORM FastAPI + PostgreSQL + Redis on AWS using Docker  
**Estimated Time:** 3–4 hours (first-time setup)

---

## 📐 Architecture You Will Deploy

```
                        ┌─────────────────────────────────────────────┐
                        │              AWS Cloud (ap-south-1)          │
                        │                                              │
  Internet              │   ┌─────────────────────────────────────┐   │
     │                  │   │         VPC (10.0.0.0/16)           │   │
     ▼                  │   │                                     │   │
┌─────────┐             │   │  Public Subnets                     │   │
│  Client │ ──HTTPS──►  │   │  ┌──────────────────────────┐      │   │
└─────────┘             │   │  │  Application Load Balancer│      │   │
                        │   │  └────────────┬─────────────┘      │   │
                        │   │               │                     │   │
                        │   │  Private Subnets                    │   │
                        │   │  ┌────────────▼─────────────┐      │   │
                        │   │  │   ECS Fargate (API)       │      │   │
                        │   │  │   salestorm-api container │      │   │
                        │   │  └────────┬─────────┬────────┘      │   │
                        │   │           │         │                │   │
                        │   │  ┌────────▼──┐  ┌──▼────────────┐  │   │
                        │   │  │  Amazon   │  │   Amazon      │  │   │
                        │   │  │    RDS    │  │ ElastiCache   │  │   │
                        │   │  │(PostgreSQL│  │   (Redis)     │  │   │
                        │   │  │  db.t3.m) │  │  cache.t3.m   │  │   │
                        │   │  └───────────┘  └───────────────┘  │   │
                        │   └─────────────────────────────────────┘   │
                        │                                              │
                        │   ┌───────────┐  ┌─────────────────────┐   │
                        │   │    ECR    │  │   Secrets Manager   │   │
                        │   │ (Docker   │  │  (DB/Redis creds)   │   │
                        │   │  Images)  │  └─────────────────────┘   │
                        │   └───────────┘                             │
                        │                                             │
                        │   ┌─────────────────────────────────────┐   │
                        │   │   CloudWatch (Logs + Metrics + Alerts│   │
                        │   └─────────────────────────────────────┘   │
                        └─────────────────────────────────────────────┘
```

### AWS Services Used
| Service | Purpose | Replaces (local) |
|---------|---------|------------------|
| **Amazon ECR** | Docker image registry | Docker Hub |
| **Amazon ECS Fargate** | Run containers (serverless) | `docker-compose up` |
| **Amazon RDS (PostgreSQL 16)** | Managed database | Local postgres container |
| **Amazon ElastiCache (Redis 7)** | Managed Redis cache | Local redis container |
| **Application Load Balancer** | HTTPS routing, health checks | Direct port access |
| **AWS Secrets Manager** | Store DB/Redis credentials | `.env` file |
| **Amazon CloudWatch** | Logs, metrics, alerts | Console/terminal |
| **AWS VPC + Security Groups** | Network isolation | Docker network |

---

## 📋 PREREQUISITES CHECKLIST

Before starting, make sure you have:

- [ ] **AWS Account** with billing enabled (Free tier works for testing)
- [ ] **AWS CLI v2** installed on your machine
- [ ] **Docker Desktop** running on your machine
- [ ] **Git** (to clone/push the project)
- [ ] **IAM User** with `AdministratorAccess` (for the hackathon — not for production)

### Install AWS CLI (if not installed)
```bash
# Windows (PowerShell as Admin)
winget install Amazon.AWSCLI

# Verify
aws --version
# Expected: aws-cli/2.x.x
```

---

## PHASE 1 — AWS ACCOUNT SETUP & IAM

### Step 1.1 — Configure AWS CLI Credentials

```bash
aws configure
# AWS Access Key ID:     [Your Access Key from IAM Console]
# AWS Secret Access Key: [Your Secret Key from IAM Console]
# Default region name:   ap-south-1      <- Mumbai (closest for India)
# Default output format: json
```

**Verify connection:**
```bash
aws sts get-caller-identity
# Should return your Account ID, UserId, and ARN
```

### Step 1.2 — Set Key Variables (run these in PowerShell — reuse throughout)

```powershell
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)
$AWS_REGION = "ap-south-1"
$APP_NAME = "salestorm"
$ECR_REPO = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$APP_NAME"

Write-Host "Account: $AWS_ACCOUNT_ID"
Write-Host "ECR Repo: $ECR_REPO"
```

---

## PHASE 2 — PUSH DOCKER IMAGE TO AMAZON ECR

### Step 2.1 — Create an ECR Repository

```bash
aws ecr create-repository `
  --repository-name salestorm `
  --region ap-south-1 `
  --image-scanning-configuration scanOnPush=true
```

### Step 2.2 — Build the Docker Image

```powershell
# Navigate to the project root
cd D:\Syscrafters_System_Design

# Build the image (uses existing Dockerfile)
docker build -t salestorm:latest .

# Verify image was built
docker images | findstr salestorm
```

### Step 2.3 — Log in to ECR

```powershell
aws ecr get-login-password --region ap-south-1 | `
  docker login --username AWS `
  --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com"
# Expected: Login Succeeded
```

### Step 2.4 — Tag and Push the Image

```powershell
docker tag salestorm:latest "$ECR_REPO:latest"
docker push "$ECR_REPO:latest"

# Verify in ECR
aws ecr list-images --repository-name salestorm --region ap-south-1
```

> **Tip:** Future pushes after code changes — repeat steps 2.2 to 2.4. The `latest` tag auto-updates.

---

## PHASE 3 — NETWORKING: VPC & SECURITY GROUPS

### Step 3.1 — Create the VPC

```bash
aws ec2 create-vpc `
  --cidr-block 10.0.0.0/16 `
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=salestorm-vpc}]'

$VPC_ID = (aws ec2 describe-vpcs --filters "Name=tag:Name,Values=salestorm-vpc" `
  --query "Vpcs[0].VpcId" --output text)
Write-Host "VPC ID: $VPC_ID"
```

### Step 3.2 — Create Subnets (2 Public + 2 Private)

```bash
# Public Subnet 1 (AZ: ap-south-1a) - For ALB
aws ec2 create-subnet --vpc-id $VPC_ID `
  --cidr-block 10.0.1.0/24 --availability-zone ap-south-1a `
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=salestorm-public-1a}]'

# Public Subnet 2 (AZ: ap-south-1b) - ALB needs 2 AZs
aws ec2 create-subnet --vpc-id $VPC_ID `
  --cidr-block 10.0.2.0/24 --availability-zone ap-south-1b `
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=salestorm-public-1b}]'

# Private Subnet 1 (AZ: ap-south-1a) - For ECS + RDS + Redis
aws ec2 create-subnet --vpc-id $VPC_ID `
  --cidr-block 10.0.10.0/24 --availability-zone ap-south-1a `
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=salestorm-private-1a}]'

# Private Subnet 2 (AZ: ap-south-1b) - For RDS Multi-AZ standby
aws ec2 create-subnet --vpc-id $VPC_ID `
  --cidr-block 10.0.11.0/24 --availability-zone ap-south-1b `
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=salestorm-private-1b}]'
```

### Step 3.3 — Internet Gateway (for ALB public access)

```bash
aws ec2 create-internet-gateway `
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=salestorm-igw}]'

$IGW_ID = (aws ec2 describe-internet-gateways `
  --filters "Name=tag:Name,Values=salestorm-igw" `
  --query "InternetGateways[0].InternetGatewayId" --output text)

aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID

# Create and attach route table for public subnets
aws ec2 create-route-table --vpc-id $VPC_ID `
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=salestorm-public-rt}]'

$RT_ID = (aws ec2 describe-route-tables `
  --filters "Name=tag:Name,Values=salestorm-public-rt" `
  --query "RouteTables[0].RouteTableId" --output text)

aws ec2 create-route --route-table-id $RT_ID `
  --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW_ID
```

### Step 3.4 — Create Security Groups

```bash
# --- SG 1: ALB (accepts HTTP/HTTPS from internet) ---
aws ec2 create-security-group `
  --group-name salestorm-alb-sg `
  --description "SALESTORM ALB" --vpc-id $VPC_ID

$ALB_SG = (aws ec2 describe-security-groups `
  --filters "Name=group-name,Values=salestorm-alb-sg" `
  --query "SecurityGroups[0].GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $ALB_SG --protocol tcp --port 443 --cidr 0.0.0.0/0

# --- SG 2: ECS Tasks (accepts from ALB only on port 8080) ---
aws ec2 create-security-group `
  --group-name salestorm-ecs-sg `
  --description "SALESTORM ECS Tasks" --vpc-id $VPC_ID

$ECS_SG = (aws ec2 describe-security-groups `
  --filters "Name=group-name,Values=salestorm-ecs-sg" `
  --query "SecurityGroups[0].GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id $ECS_SG `
  --protocol tcp --port 8080 --source-group $ALB_SG

# --- SG 3: RDS (accepts from ECS only on port 5432) ---
aws ec2 create-security-group `
  --group-name salestorm-rds-sg `
  --description "SALESTORM RDS" --vpc-id $VPC_ID

$RDS_SG = (aws ec2 describe-security-groups `
  --filters "Name=group-name,Values=salestorm-rds-sg" `
  --query "SecurityGroups[0].GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id $RDS_SG `
  --protocol tcp --port 5432 --source-group $ECS_SG

# --- SG 4: ElastiCache (accepts from ECS only on port 6379) ---
aws ec2 create-security-group `
  --group-name salestorm-redis-sg `
  --description "SALESTORM Redis" --vpc-id $VPC_ID

$REDIS_SG = (aws ec2 describe-security-groups `
  --filters "Name=group-name,Values=salestorm-redis-sg" `
  --query "SecurityGroups[0].GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id $REDIS_SG `
  --protocol tcp --port 6379 --source-group $ECS_SG
```

---

## PHASE 4 — DATABASE: AMAZON RDS (PostgreSQL 16)

### Step 4.1 — Create RDS Subnet Group

```bash
$PRIV_SUBNET_1 = (aws ec2 describe-subnets `
  --filters "Name=tag:Name,Values=salestorm-private-1a" `
  --query "Subnets[0].SubnetId" --output text)
$PRIV_SUBNET_2 = (aws ec2 describe-subnets `
  --filters "Name=tag:Name,Values=salestorm-private-1b" `
  --query "Subnets[0].SubnetId" --output text)

aws rds create-db-subnet-group `
  --db-subnet-group-name salestorm-db-subnet-group `
  --db-subnet-group-description "SALESTORM RDS Subnet Group" `
  --subnet-ids $PRIV_SUBNET_1 $PRIV_SUBNET_2
```

### Step 4.2 — Create RDS PostgreSQL Instance

```bash
aws rds create-db-instance `
  --db-instance-identifier salestorm-postgres `
  --db-instance-class db.t3.micro `
  --engine postgres `
  --engine-version 16.3 `
  --master-username salestorm_user `
  --master-user-password "SalestormDB@2026!" `
  --db-name salestorm_db `
  --db-subnet-group-name salestorm-db-subnet-group `
  --vpc-security-group-ids $RDS_SG `
  --storage-type gp3 `
  --allocated-storage 20 `
  --no-publicly-accessible `
  --backup-retention-period 7 `
  --deletion-protection `
  --tags Key=Project,Value=SALESTORM
```

> **Note:** RDS takes 5–10 minutes to become available. Check status:
> ```bash
> aws rds describe-db-instances `
>   --db-instance-identifier salestorm-postgres `
>   --query "DBInstances[0].DBInstanceStatus"
> ```

### Step 4.3 — Get the RDS Endpoint

```powershell
$RDS_ENDPOINT = (aws rds describe-db-instances `
  --db-instance-identifier salestorm-postgres `
  --query "DBInstances[0].Endpoint.Address" --output text)
Write-Host "RDS Endpoint: $RDS_ENDPOINT"
# DATABASE_URL = postgresql://salestorm_user:SalestormDB@2026!@$RDS_ENDPOINT:5432/salestorm_db
```

---

## PHASE 5 — CACHE: AMAZON ELASTICACHE (Redis 7)

### Step 5.1 — Create ElastiCache Subnet Group

```bash
aws elasticache create-cache-subnet-group `
  --cache-subnet-group-name salestorm-redis-subnet `
  --cache-subnet-group-description "SALESTORM Redis Subnet Group" `
  --subnet-ids $PRIV_SUBNET_1 $PRIV_SUBNET_2
```

### Step 5.2 — Create Redis Cluster

```bash
aws elasticache create-cache-cluster `
  --cache-cluster-id salestorm-redis `
  --cache-node-type cache.t3.micro `
  --engine redis `
  --engine-version 7.0 `
  --num-cache-nodes 1 `
  --cache-subnet-group-name salestorm-redis-subnet `
  --security-group-ids $REDIS_SG `
  --tags Key=Project,Value=SALESTORM
```

### Step 5.3 — Get the Redis Endpoint

```powershell
$REDIS_ENDPOINT = (aws elasticache describe-cache-clusters `
  --cache-cluster-id salestorm-redis `
  --show-cache-node-info `
  --query "CacheClusters[0].CacheNodes[0].Endpoint.Address" --output text)
Write-Host "Redis Endpoint: $REDIS_ENDPOINT"
# REDIS_URL = redis://$REDIS_ENDPOINT:6379/0
```

---

## PHASE 6 — SECRETS MANAGER (Secure Credential Storage)

> **Important:** Never hardcode credentials in ECS task definitions directly. Always use Secrets Manager.

### Step 6.1 — Store All Secrets

```bash
aws secretsmanager create-secret `
  --name "salestorm/database-url" `
  --secret-string "postgresql://salestorm_user:SalestormDB@2026!@${RDS_ENDPOINT}:5432/salestorm_db"

aws secretsmanager create-secret `
  --name "salestorm/redis-url" `
  --secret-string "redis://${REDIS_ENDPOINT}:6379/0"
```

### Step 6.2 — Get Secret ARNs (needed for task definition)

```powershell
$SECRET_DB_ARN = (aws secretsmanager describe-secret `
  --secret-id "salestorm/database-url" --query "ARN" --output text)
$SECRET_REDIS_ARN = (aws secretsmanager describe-secret `
  --secret-id "salestorm/redis-url" --query "ARN" --output text)

Write-Host "DB ARN:    $SECRET_DB_ARN"
Write-Host "Redis ARN: $SECRET_REDIS_ARN"
```

---

## PHASE 7 — ECS FARGATE DEPLOYMENT

### Step 7.1 — Create ECS Cluster

```bash
aws ecs create-cluster `
  --cluster-name salestorm-cluster `
  --capacity-providers FARGATE `
  --tags key=Project,value=SALESTORM
```

### Step 7.2 — Create IAM Roles for ECS

```bash
# Task Execution Role (ECS pulls image + reads secrets)
aws iam create-role `
  --role-name salestorm-ecs-execution-role `
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"}]}'

aws iam attach-role-policy `
  --role-name salestorm-ecs-execution-role `
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam attach-role-policy `
  --role-name salestorm-ecs-execution-role `
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite

# Task Role (app itself calls AWS services if needed)
aws iam create-role `
  --role-name salestorm-ecs-task-role `
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"}]}'
```

### Step 7.3 — Create CloudWatch Log Group

```bash
aws logs create-log-group --log-group-name /ecs/salestorm-api --region ap-south-1
```

### Step 7.4 — Create ECS Task Definition File

Create file `task-definition.json` in your project root `D:\Syscrafters_System_Design\`:

```json
{
  "family": "salestorm-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/salestorm-ecs-execution-role",
  "taskRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/salestorm-ecs-task-role",
  "containerDefinitions": [
    {
      "name": "salestorm-api",
      "image": "YOUR_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com/salestorm:latest",
      "portMappings": [
        {
          "containerPort": 8080,
          "hostPort": 8080,
          "protocol": "tcp"
        }
      ],
      "secrets": [
        {
          "name": "DATABASE_URL",
          "valueFrom": "arn:aws:secretsmanager:ap-south-1:YOUR_ACCOUNT_ID:secret:salestorm/database-url"
        },
        {
          "name": "REDIS_URL",
          "valueFrom": "arn:aws:secretsmanager:ap-south-1:YOUR_ACCOUNT_ID:secret:salestorm/redis-url"
        }
      ],
      "environment": [
        {"name": "PORT", "value": "8080"},
        {"name": "HOST", "value": "0.0.0.0"},
        {"name": "INITIAL_STOCK", "value": "100"},
        {"name": "RESERVATION_LEASE_SECONDS", "value": "300"},
        {"name": "FLASH_SALE_PRODUCT_ID", "value": "550e8400-e29b-41d4-a716-446655440000"},
        {"name": "ENVIRONMENT", "value": "production"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/salestorm-api",
          "awslogs-region": "ap-south-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

> **Important:** Replace ALL `YOUR_ACCOUNT_ID` with your actual AWS Account ID (the number from Step 1.2).

**Register the task definition:**
```bash
aws ecs register-task-definition `
  --cli-input-json file://task-definition.json `
  --region ap-south-1
```

### Step 7.5 — Create Application Load Balancer

```powershell
$PUB_SUBNET_1 = (aws ec2 describe-subnets `
  --filters "Name=tag:Name,Values=salestorm-public-1a" `
  --query "Subnets[0].SubnetId" --output text)
$PUB_SUBNET_2 = (aws ec2 describe-subnets `
  --filters "Name=tag:Name,Values=salestorm-public-1b" `
  --query "Subnets[0].SubnetId" --output text)

aws elbv2 create-load-balancer `
  --name salestorm-alb `
  --subnets $PUB_SUBNET_1 $PUB_SUBNET_2 `
  --security-groups $ALB_SG `
  --scheme internet-facing `
  --type application `
  --tags Key=Project,Value=SALESTORM

$ALB_ARN = (aws elbv2 describe-load-balancers `
  --names salestorm-alb `
  --query "LoadBalancers[0].LoadBalancerArn" --output text)
$ALB_DNS = (aws elbv2 describe-load-balancers `
  --names salestorm-alb `
  --query "LoadBalancers[0].DNSName" --output text)
Write-Host "ALB DNS: http://$ALB_DNS"
```

### Step 7.6 — Create Target Group & Listener

```powershell
aws elbv2 create-target-group `
  --name salestorm-tg `
  --protocol HTTP --port 8080 `
  --vpc-id $VPC_ID `
  --target-type ip `
  --health-check-path /health `
  --health-check-interval-seconds 30 `
  --healthy-threshold-count 2 `
  --unhealthy-threshold-count 3

$TG_ARN = (aws elbv2 describe-target-groups `
  --names salestorm-tg `
  --query "TargetGroups[0].TargetGroupArn" --output text)

aws elbv2 create-listener `
  --load-balancer-arn $ALB_ARN `
  --protocol HTTP --port 80 `
  --default-actions Type=forward,TargetGroupArn=$TG_ARN
```

### Step 7.7 — Create ECS Service (2 replicas behind ALB)

```powershell
aws ecs create-service `
  --cluster salestorm-cluster `
  --service-name salestorm-api-service `
  --task-definition salestorm-api:1 `
  --desired-count 2 `
  --launch-type FARGATE `
  --network-configuration "awsvpcConfiguration={subnets=[$PRIV_SUBNET_1],securityGroups=[$ECS_SG],assignPublicIp=DISABLED}" `
  --load-balancers "targetGroupArn=$TG_ARN,containerName=salestorm-api,containerPort=8080" `
  --health-check-grace-period-seconds 60 `
  --tags key=Project,value=SALESTORM
```

> **Note:** ECS pulls the Docker image from ECR and starts 2 containers. Takes 2–5 minutes to reach RUNNING state.

### Step 7.8 — Verify Deployment

```bash
# Check ECS service health
aws ecs describe-services `
  --cluster salestorm-cluster `
  --services salestorm-api-service `
  --query "services[0].{Status:status,Running:runningCount,Desired:desiredCount}"

# Hit the health endpoint
curl http://$ALB_DNS/health
# Expected: {"status":"HEALTHY","service":"salestorm-api","version":"1.0.0"}

# Check metrics
curl http://$ALB_DNS/metrics

# Open API Docs in browser
Write-Host "Open: http://$ALB_DNS/docs"
```

---

## PHASE 8 — CLOUDWATCH MONITORING & ALERTS

### Step 8.1 — View Live Application Logs

```bash
aws logs tail /ecs/salestorm-api --follow --region ap-south-1
```

### Step 8.2 — Set Up Critical Alarms via SNS

```bash
# Create SNS topic for team alerts
aws sns create-topic --name salestorm-alerts --region ap-south-1

$SNS_ARN = (aws sns list-topics `
  --query "Topics[?contains(TopicArn,'salestorm-alerts')].TopicArn | [0]" --output text)

# Subscribe your team email
aws sns subscribe `
  --topic-arn $SNS_ARN `
  --protocol email `
  --notification-endpoint your-team-email@example.com

# ALARM 1: CPU > 80% for 5 minutes
aws cloudwatch put-metric-alarm `
  --alarm-name "SALESTORM-HighCPU" `
  --metric-name CPUUtilization `
  --namespace AWS/ECS `
  --dimensions Name=ClusterName,Value=salestorm-cluster Name=ServiceName,Value=salestorm-api-service `
  --statistic Average --period 300 --threshold 80 `
  --comparison-operator GreaterThanThreshold `
  --evaluation-periods 1 --alarm-actions $SNS_ARN

# ALARM 2: HTTP 5xx errors > 10 per minute
aws cloudwatch put-metric-alarm `
  --alarm-name "SALESTORM-High5xxErrors" `
  --metric-name HTTPCode_Target_5XX_Count `
  --namespace AWS/ApplicationELB `
  --statistic Sum --period 60 --threshold 10 `
  --comparison-operator GreaterThanThreshold `
  --evaluation-periods 1 --alarm-actions $SNS_ARN

# ALARM 3: RDS free storage < 5 GB
aws cloudwatch put-metric-alarm `
  --alarm-name "SALESTORM-LowDBStorage" `
  --metric-name FreeStorageSpace `
  --namespace AWS/RDS `
  --dimensions Name=DBInstanceIdentifier,Value=salestorm-postgres `
  --statistic Average --period 300 --threshold 5368709120 `
  --comparison-operator LessThanThreshold `
  --evaluation-periods 1 --alarm-actions $SNS_ARN
```

### Step 8.3 — Key CloudWatch Metrics to Watch

| Metric | Namespace | Normal Range | Alert Threshold |
|--------|-----------|--------------|----------------|
| `CPUUtilization` | AWS/ECS | < 60% | > 80% |
| `MemoryUtilization` | AWS/ECS | < 70% | > 85% |
| `RequestCount` | AWS/ApplicationELB | Baseline | Spike > 10x |
| `HTTPCode_Target_5XX_Count` | AWS/ApplicationELB | 0 | > 10/min |
| `TargetResponseTime` | AWS/ApplicationELB | < 200ms | > 1000ms |
| `DatabaseConnections` | AWS/RDS | < 50 | > 90 |
| `CacheHits` | AWS/ElastiCache | High | Low (cache miss spike) |

---

## PHASE 9 — DEPLOYING CODE UPDATES (Zero Downtime)

```powershell
# 1. Build new image
cd D:\Syscrafters_System_Design
docker build -t salestorm:latest .

# 2. Push to ECR
docker tag salestorm:latest "$ECR_REPO:latest"
aws ecr get-login-password --region ap-south-1 | `
  docker login --username AWS `
  --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.ap-south-1.amazonaws.com"
docker push "$ECR_REPO:latest"

# 3. Force ECS rolling update (zero downtime - replaces containers one by one)
aws ecs update-service `
  --cluster salestorm-cluster `
  --service salestorm-api-service `
  --force-new-deployment `
  --region ap-south-1

# 4. Monitor the rolling update
aws ecs describe-services `
  --cluster salestorm-cluster `
  --services salestorm-api-service `
  --query "services[0].{Status:status,Running:runningCount,Pending:pendingCount}"
```

---

## PHASE 10 — AUTO SCALING FOR FLASH SALE TRAFFIC

```bash
# Register scalable target (min 2, max 20 containers)
aws application-autoscaling register-scalable-target `
  --service-namespace ecs `
  --resource-id service/salestorm-cluster/salestorm-api-service `
  --scalable-dimension ecs:service:DesiredCount `
  --min-capacity 2 `
  --max-capacity 20

# Auto scale when CPU > 60% (adds containers automatically)
aws application-autoscaling put-scaling-policy `
  --policy-name salestorm-cpu-scale-out `
  --service-namespace ecs `
  --resource-id service/salestorm-cluster/salestorm-api-service `
  --scalable-dimension ecs:service:DesiredCount `
  --policy-type TargetTrackingScaling `
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 60.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 300
  }'
```

---

## PHASE 11 — INITIALIZE DATABASE SCHEMA ON RDS

The app auto-creates tables via SQLAlchemy on startup, but to apply the full `schema.sql`:

```bash
# Option A: psql client (add your IP temporarily to RDS SG first)
psql -h $RDS_ENDPOINT -U salestorm_user -d salestorm_db -f 04_Database/schema.sql

# Option B: AWS Console
# RDS -> Databases -> salestorm-postgres -> Query Editor
# Paste the contents of 04_Database/schema.sql and run
```

---

## 🧪 FINAL VERIFICATION CHECKLIST

```bash
# 1. Health Check
curl http://$ALB_DNS/health
# Expected: {"status":"HEALTHY","service":"salestorm-api","version":"1.0.0"}

# 2. Product Listing (should show 100 units available)
curl http://$ALB_DNS/api/v1/products

# 3. Live Metrics
curl http://$ALB_DNS/metrics
# Expected: {"initial_stock":100,"available_stock":100,"sold_stock":0,...}

# 4. Reserve a unit (end-to-end test)
curl -X POST http://$ALB_DNS/api/v1/reservations `
  -H "Content-Type: application/json" `
  -H "Idempotency-Key: e2e-test-$(Get-Date -Format 'yyyyMMddHHmmss')" `
  -d '{"product_id":"550e8400-e29b-41d4-a716-446655440000","quantity":1,"customer_id":"00000000-0000-0000-0000-000000000001"}'

# 5. OpenAPI Docs (open in browser)
Start-Process "http://$ALB_DNS/docs"
```

---

## 🗑️ CLEANUP AFTER HACKATHON (Prevents AWS charges)

Run these commands **in order** after the hackathon:

```bash
# Step 1: Scale down ECS to 0
aws ecs update-service --cluster salestorm-cluster --service salestorm-api-service --desired-count 0

# Step 2: Delete ECS Service
aws ecs delete-service --cluster salestorm-cluster --service salestorm-api-service --force

# Step 3: Delete ECS Cluster
aws ecs delete-cluster --cluster salestorm-cluster

# Step 4: Delete Load Balancer & Target Group
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN
Start-Sleep 30
aws elbv2 delete-target-group --target-group-arn $TG_ARN

# Step 5: Delete RDS (skip final snapshot for hackathon)
aws rds delete-db-instance `
  --db-instance-identifier salestorm-postgres `
  --skip-final-snapshot --delete-automated-backups

# Step 6: Delete ElastiCache
aws elasticache delete-cache-cluster --cache-cluster-id salestorm-redis

# Step 7: Delete ECR Repository
aws ecr delete-repository --repository-name salestorm --force

# Step 8: Delete Secrets
aws secretsmanager delete-secret --secret-id "salestorm/database-url" --force-delete-without-recovery
aws secretsmanager delete-secret --secret-id "salestorm/redis-url" --force-delete-without-recovery

# Step 9: Delete CloudWatch logs
aws logs delete-log-group --log-group-name /ecs/salestorm-api
```

---

## 📊 COST ESTIMATE (ap-south-1, Mumbai)

| Service | Configuration | Estimated Cost/Month |
|---------|--------------|---------------------|
| ECS Fargate | 2 tasks x 0.5 vCPU / 1 GB | ~$8 |
| RDS PostgreSQL | db.t3.micro, 20 GB gp3 | ~$20 |
| ElastiCache Redis | cache.t3.micro | ~$12 |
| Application Load Balancer | ~100K requests | ~$20 |
| ECR Storage | ~500 MB image | ~$0.05 |
| CloudWatch Logs | ~1 GB/month | ~$0.50 |
| Secrets Manager | 2 secrets | ~$0.80 |
| **TOTAL** | | **~$61/month** |

> **For the hackathon demo (a few hours): actual cost is under $2.**  
> Run the cleanup commands immediately after the demo!

---

## 📞 QUICK REFERENCE CARD

```powershell
# --- DAILY COMMANDS ---

# View live logs
aws logs tail /ecs/salestorm-api --follow

# Check service health
aws ecs describe-services --cluster salestorm-cluster --services salestorm-api-service

# Deploy new code (after git pull + docker build + push)
aws ecs update-service --cluster salestorm-cluster --service salestorm-api-service --force-new-deployment

# Manually scale to 5 containers (pre-flash-sale)
aws ecs update-service --cluster salestorm-cluster --service salestorm-api-service --desired-count 5

# Scale back down after sale
aws ecs update-service --cluster salestorm-cluster --service salestorm-api-service --desired-count 2

# --- URLS ---
# App:      http://$ALB_DNS
# API Docs: http://$ALB_DNS/docs
# Health:   http://$ALB_DNS/health
# Metrics:  http://$ALB_DNS/metrics
```

---

*Guide authored by Member 1 (System Architect) | SALESTORM SYSCRAFTERS 2026*
