# SALESTORM 2026 | Database Relationships & Referential Integrity

## 1. Architectural Strategy for Relationships

In a high-throughput flash-sale architecture operating at up to 500,000 requests/sec, relational design must balance two opposing forces:
1. **Mathematical Correctness & ACID Guarantees**: Enforcing referential integrity within tightly-coupled aggregate boundaries.
2. **Decoupled Autonomous Services & Low-Latency Execution**: Avoiding synchronous cross-service locking and distributed foreign keys that degrade availability.

To achieve this, SALESTORM segregates relationships into two categories:
- **Intra-Service (Physical Foreign Keys)**: Hard foreign key constraints enforced by the database engine within an autonomous service boundary.
- **Inter-Service (Logical References)**: Asynchronous, event-driven relationships linked via immutable UUID identifiers across service boundaries.

---

## 2. Comprehensive Relationship Catalog

### 2.1 Catalog & Product Domain
```
categories (1) ────< (N) categories [Self-Referencing Subcategories]
    │
    └──< (N) products (1) ────< (N) flash_sale_deals
```
- **`categories` -> `categories`**:
  - Cardinality: `1:N` (Parent Category to Subcategories).
  - Physical Foreign Key: `parent_category_id REFERENCES categories(category_id) ON DELETE SET NULL`.
  - Behavior: If a parent category is deleted, child categories are retained at the root level.
- **`categories` -> `products`**:
  - Cardinality: `1:N` (One category classifies multiple products).
  - Physical Foreign Key: `category_id REFERENCES categories(category_id) ON DELETE RESTRICT`.
  - Behavior: Restricts deletion of any category currently containing active products.
- **`products` -> `flash_sale_deals`**:
  - Cardinality: `1:N` (One product may be scheduled in multiple historical or future flash sale deals).
  - Physical Foreign Key: `product_id REFERENCES products(product_id) ON DELETE CASCADE`.

---

### 2.2 Inventory & Reservation Domain (Hotspot Core)
```
products (1) ────|| (1) inventory (1) ────< (N) inventory_reservations
```
- **`products` -> `inventory`**:
  - Cardinality: `1:1` (Strictly one authoritative inventory record per catalog SKU).
  - Physical Foreign Key: `product_id REFERENCES products(product_id) ON DELETE RESTRICT`.
  - Invariant: Inventory records cannot be deleted if a product exists; decommissioning requires soft-deactivation.
- **`inventory` -> `inventory_reservations`**:
  - Cardinality: `1:N` (One inventory ledger tracks multiple concurrent customer reservations).
  - Physical Foreign Key: `inventory_id REFERENCES inventory(inventory_id) ON DELETE RESTRICT`.
  - Behavior: Reservations hold a direct reference to the parent stock row. Inventory rows cannot be dropped while active reservations exist.

---

### 2.3 Customer & Cart Domain
```
customers (1) ────|| (1) carts (1) ────< (N) cart_items (N) >──── (1) products
```
- **`customers` -> `carts`**:
  - Cardinality: `1:1` (Each customer maintains exactly one active pre-checkout cart).
  - Physical Foreign Key: `customer_id REFERENCES customers(customer_id) ON DELETE CASCADE`.
- **`carts` -> `cart_items`**:
  - Cardinality: `1:N` (One cart contains multiple distinct items).
  - Physical Foreign Key: `cart_id REFERENCES carts(cart_id) ON DELETE CASCADE`.
- **`cart_items` -> `products`**:
  - Cardinality: `N:1` (Items point to catalog merchandise).
  - Physical Foreign Key: `product_id REFERENCES products(product_id) ON DELETE RESTRICT`.

---

### 2.4 Checkout, Order & Payment Domain
```
inventory_reservations (1) ───|| (1) orders (1) ────< (N) order_items
         │                               │
         └───────────< (N) payments >────┘
```
- **`inventory_reservations` -> `orders`**:
  - Cardinality: `1:1` (An order is directly backed by exactly one valid inventory reservation).
  - Physical Constraint: `reservation_id UUID NOT NULL UNIQUE REFERENCES inventory_reservations(reservation_id)`.
  - Invariant: Enforces that one reservation can never produce multiple orders, preventing double-fulfillment.
- **`orders` -> `order_items`**:
  - Cardinality: `1:N` (One order contains line items representing purchased quantities and price snapshots).
  - Physical Foreign Key: `order_id REFERENCES orders(order_id) ON DELETE CASCADE`.
- **`inventory_reservations` -> `payments`**:
  - Cardinality: `1:N` (A single reservation hold may experience multiple payment attempts, e.g. first attempt fails, customer retries with another card before reservation expires).
  - Physical Foreign Key: `reservation_id REFERENCES inventory_reservations(reservation_id) ON DELETE RESTRICT`.
- **`orders` -> `payments`**:
  - Cardinality: `1:N` (Link established once order is confirmed).
  - Logical / Physical Foreign Key: `order_id REFERENCES orders(order_id) ON DELETE RESTRICT`.

---

### 2.5 Order Fulfillment & Logistics Domain
```
orders (1) ────|| (1) shipments
orders (1) ────< (N) notifications
```
- **`orders` -> `shipments`**:
  - Cardinality: `1:1` (In this flash-sale scope, an order maps to a single physical fulfillment shipment).
  - Physical Foreign Key: `order_id UUID NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE RESTRICT`.
- **`customers` -> `notifications`**:
  - Cardinality: `1:N` (Customer receives multiple transactional notifications: reservation, payment receipt, dispatch, delivery).
  - Physical Foreign Key: `customer_id REFERENCES customers(customer_id) ON DELETE CASCADE`.

---

## 3. Distributed Service Boundary Mapping (Cross-Service Decoupling)

When deployed in independent database instances per microservice (as designed by Member 1 and Member 4 on AWS RDS / Aurora):

| Service A | Service B | Inter-Service Contract | Protocol | Consistency Guarantee |
| :--- | :--- | :--- | :--- | :--- |
| **Inventory Service** | **Checkout Service** | `reservation_id`, `inventory_id` | Synchronous REST / gRPC | Strong consistency during hold creation. |
| **Checkout Service** | **Payment Service** | `payment_id`, `reservation_id` | Synchronous REST + Webhook | Idempotent transition; eventual order trigger. |
| **Payment Service** | **Order Service** | `PaymentSucceeded` Event | Async Message Broker (SQS / Kafka) | At-least-once with idempotent consumer deduplication. |
| **Order Service** | **Shipment Service** | `OrderConfirmed` Event | Async Message Broker | Eventual consistency; dead-letter queue backoff. |
| **Order Service** | **Notification Service**| `OrderConfirmed` Event | Async Message Broker | At-least-once async delivery. |
