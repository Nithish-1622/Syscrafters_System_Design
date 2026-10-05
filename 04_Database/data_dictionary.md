# SALESTORM 2026 | Comprehensive Data Dictionary

## 1. Domain Overview & Technical Specifications

This data dictionary defines the complete logical and physical storage model for SALESTORM. Every table is documented with strict type specifications, nullability rules, database constraints, business lifecycles, and operational ownership.

---

## 2. Table Catalog

### 2.1 Table: `categories`
- **Domain**: Catalog Service
- **Purpose**: Organizes products into navigable hierarchies.
- **Access Pattern**: Read-heavy; aggressive CDN and read-replica caching.

| Column Name | Physical Type | Nullable | Default | Constraints | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `category_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Globally unique category identifier. |
| `name` | VARCHAR(100) | No | None | UNIQUE | Human-readable category title. |
| `slug` | VARCHAR(120) | No | None | UNIQUE | URL-safe slug for SEO and routing. |
| `description` | TEXT | Yes | NULL | None | Extended category description. |
| `parent_category_id` | UUID | Yes | NULL | FK -> `categories(category_id)` | Self-referencing FK for subcategories. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Timestamp of creation. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Timestamp of last modification. |

---

### 2.2 Table: `customers`
- **Domain**: Identity & Customer Service
- **Purpose**: Stores verified customer profiles and authentication credentials.
- **Access Pattern**: Write-once on registration; authenticated lookup per checkout.

| Column Name | Physical Type | Nullable | Default | Constraints | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `customer_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Unique customer identifier. |
| `email` | VARCHAR(255) | No | None | UNIQUE | Canonical user email; login username. |
| `password_hash` | VARCHAR(255) | No | None | None | Argon2id / bcrypt salted hash. |
| `full_name` | VARCHAR(150) | No | None | None | Customer legal or display name. |
| `phone_number` | VARCHAR(30) | Yes | NULL | None | E.164 formatted contact number for SMS. |
| `is_active` | BOOLEAN | No | `TRUE` | None | Account status flag (for fraud/abuse deactivation). |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Creation timestamp. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Last profile update. |

---

### 2.3 Table: `products`
- **Domain**: Catalog Service
- **Purpose**: Master entity for all merchandise, sale pricing, and flash-sale flags.
- **Access Pattern**: Massive read volume (500k req/sec peak); served from distributed edge caches and read-replicas.

| Column Name | Physical Type | Nullable | Default | Constraints | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `product_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Unique product entity identifier. |
| `category_id` | UUID | No | None | FK -> `categories` | Category classification. |
| `sku` | VARCHAR(64) | No | None | UNIQUE | Stock Keeping Unit code. |
| `title` | VARCHAR(255) | No | None | None | Product title displayed to customer. |
| `description` | TEXT | Yes | NULL | None | Rich text markdown or product copy. |
| `base_price` | NUMERIC(12, 2)| No | None | `CHECK (base_price >= 0)` | Standard catalog price. |
| `currency` | VARCHAR(3) | No | `'USD'` | ISO 4217 standard | Base currency code. |
| `is_active` | BOOLEAN | No | `TRUE` | None | Product visibility in store. |
| `is_flash_sale` | BOOLEAN | No | `FALSE` | None | Identifies products subjected to flash-sale logic. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Creation timestamp. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Last catalog modification. |

---

### 2.4 Table: `inventory`
- **Domain**: Inventory Service (CRITICAL DOMAIN)
- **Purpose**: Authoritative single source of truth for stock quantities. Enforces mathematical invariants against overselling.
- **Access Pattern**: Extreme write contention during flash-sale; updated via atomic conditional SQL queries.

| Column Name | Physical Type | Nullable | Default | Constraints | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `inventory_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Unique inventory record identifier. |
| `product_id` | UUID | No | None | UNIQUE, FK -> `products` | 1-to-1 relationship with product entity. |
| `total_quantity` | INT | No | None | `CHECK (total_quantity >= 0)` | Total physical units allocated. |
| `available_quantity` | INT | No | None | `CHECK (available_quantity >= 0)` | Unreserved units available for reservation. |
| `reserved_quantity` | INT | No | None | `CHECK (reserved_quantity >= 0)` | Units temporarily held in active checkouts. |
| `sold_quantity` | INT | No | None | `CHECK (sold_quantity >= 0)` | Units successfully paid and converted to orders. |
| `version` | BIGINT | No | `0` | None | Optimistic locking counter / state revision. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Creation timestamp. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Last inventory transition. |

**Database Table Constraints**:
- `chk_inventory_quantities_balance`: `CHECK (available_quantity + reserved_quantity + sold_quantity = total_quantity)`
- Non-negative guarantees: `available_quantity >= 0`, `reserved_quantity >= 0`, `sold_quantity >= 0`.

---

### 2.5 Table: `inventory_reservations`
- **Domain**: Reservation & Checkout Service
- **Purpose**: Represents a temporary claim on physical inventory during customer checkout.
- **Access Pattern**: High-velocity inserts and conditional status updates; scanned by background reaper jobs for expiry.

| Column Name | Physical Type | Nullable | Default | Constraints | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `reservation_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Unique reservation identifier. |
| `inventory_id` | UUID | No | None | FK -> `inventory` | Target inventory record. |
| `customer_id` | UUID | No | None | FK -> `customers` | Claiming customer. |
| `quantity` | INT | No | None | `CHECK (quantity > 0)` | Number of units held. |
| `status` | ENUM | No | `'RESERVED'` | `reservation_status_enum` | Lifecycle state (`RESERVED`, `PAYMENT_PENDING`, `CONFIRMED`, `SOLD`, `PAYMENT_FAILED`, `EXPIRED`, `RELEASED`). |
| `idempotency_key` | VARCHAR(128) | No | None | UNIQUE | Client-supplied key to prevent duplicate holds. |
| `expires_at` | TIMESTAMPTZ | No | None | None | Hard deadline (e.g. `NOW() + INTERVAL '5 minutes'`). |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Reservation timestamp. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Last status change timestamp. |

---

### 2.6 Table: `carts` & `cart_items`
- **Domain**: Cart Service
- **Purpose**: Persists pre-checkout intent for authenticated customers.

#### `carts`
| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `cart_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Cart identifier. |
| `customer_id` | UUID | No | None | UNIQUE, FK -> `customers` | 1-to-1 active cart per customer. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Timestamp. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Last cart modification. |

#### `cart_items`
| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `cart_item_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Unique line item ID. |
| `cart_id` | UUID | No | None | FK -> `carts` (CASCADE) | Parent cart. |
| `product_id` | UUID | No | None | FK -> `products` | Target product. |
| `quantity` | INT | No | None | `CHECK (quantity > 0)` | Selected quantity. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Timestamp. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Timestamp. |

---

### 2.7 Table: `flash_sale_deals`
- **Domain**: Promotion & Campaign Service
- **Purpose**: Defines promotional price reductions and dedicated inventory quotas for time-boxed sales.

| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `deal_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Unique promotional deal identifier. |
| `product_id` | UUID | No | None | FK -> `products` | Product featured in sale. |
| `sale_price` | NUMERIC(12, 2)| No | None | `CHECK (sale_price >= 0)`| Discounted flash sale unit price. |
| `allocated_quantity`| INT | No | None | `CHECK (allocated_quantity > 0)`| Maximum units available under this deal. |
| `starts_at` | TIMESTAMPTZ | No | None | None | Sale launch timestamp. |
| `ends_at` | TIMESTAMPTZ | No | None | `CHECK (ends_at > starts_at)`| Hard end of flash sale pricing. |
| `is_active` | BOOLEAN | No | `TRUE` | None | Kill-switch toggle for operations. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Created at. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Updated at. |

---

### 2.8 Table: `orders` & `order_items`
- **Domain**: Order Management Service
- **Purpose**: Authoritative historical record of completed customer purchases.

#### `orders`
| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `order_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Order identifier. |
| `order_number` | VARCHAR(32) | No | None | UNIQUE | Human-readable customer reference (e.g. `ORD-20261005-9821`). |
| `customer_id` | UUID | No | None | FK -> `customers` | Purchasing customer. |
| `reservation_id` | UUID | No | None | UNIQUE, FK -> `reservations`| Direct 1-to-1 link to inventory reservation. |
| `status` | ENUM | No | `'CREATED'` | `order_status_enum` | Status (`CREATED`, `PAYMENT_PENDING`, `CONFIRMED`, `PROCESSING`, `SHIPPED`, `DELIVERED`, `CANCELLED`). |
| `total_amount` | NUMERIC(12, 2)| No | None | `CHECK (total_amount >= 0)`| Grand total billed to customer. |
| `currency` | VARCHAR(3) | No | `'USD'` | ISO currency | Currency code. |
| `shipping_address_json`| JSONB | No | None | Valid JSON structure | Physical delivery address snapshot. |
| `billing_address_json` | JSONB | No | None | Valid JSON structure | Billing address snapshot. |
| `version` | BIGINT | No | `0` | None | Optimistic lock counter. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Creation timestamp. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Modification timestamp. |

#### `order_items`
| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `order_item_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Line item identifier. |
| `order_id` | UUID | No | None | FK -> `orders` (CASCADE) | Parent order. |
| `product_id` | UUID | No | None | FK -> `products` | Product purchased. |
| `quantity` | INT | No | None | `CHECK (quantity > 0)` | Units purchased. |
| `unit_price` | NUMERIC(12, 2)| No | None | `CHECK (unit_price >= 0)` | Price per unit at purchase time. |
| `total_price` | NUMERIC(12, 2)| No | None | `CHECK (total_price >= 0)`| `quantity * unit_price`. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Line creation timestamp. |

---

### 2.9 Table: `payments`
- **Domain**: Payment & Financial Settlement Service
- **Purpose**: Persists payment intent, gateway responses, and idempotent status reconciliation.

| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `payment_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Internal payment identifier. |
| `order_id` | UUID | Yes | NULL | FK -> `orders` | Associated order (nullable at initiation). |
| `reservation_id` | UUID | No | None | FK -> `inventory_reservations`| Reservation securing this payment. |
| `customer_id` | UUID | No | None | FK -> `customers` | Payer customer ID. |
| `amount` | NUMERIC(12, 2)| No | None | `CHECK (amount > 0)` | Financial charge amount. |
| `currency` | VARCHAR(3) | No | `'USD'` | ISO currency | Billed currency. |
| `payment_method` | VARCHAR(50) | No | None | None | Card, UPI, ApplePay, PayPal. |
| `provider` | VARCHAR(50) | No | None | None | Gateway name (e.g. Stripe, Adyen). |
| `provider_transaction_id`| VARCHAR(128)| Yes | NULL | UNIQUE | External gateway charge ID (`ch_xxx`). |
| `idempotency_key`| VARCHAR(128)| No | None | UNIQUE | Client-supplied key to prevent duplicate charge. |
| `status` | ENUM | No | `'INITIATED'`| `payment_status_enum` | `INITIATED`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `RECONCILIATION_REQUIRED`, `REFUNDED`. |
| `failure_reason` | VARCHAR(255)| Yes | NULL | None | Error description if declined. |
| `reconciliation_notes` | TEXT | Yes | NULL | None | Operator / engine notes for ambiguous states. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Charge initiation timestamp. |
| `updated_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Last status change timestamp. |

---

### 2.10 Table: `idempotency_records`
- **Domain**: Reliability Infrastructure
- **Purpose**: Distributed API deduplication and locking store. Prevents double-submissions under network retries.

| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `idempotency_key`| VARCHAR(128)| No | None | PRIMARY KEY | Client-provided uniqueness token. |
| `scope` | VARCHAR(64) | No | None | None | Endpoint/action scope (`RESERVATION`, `PAYMENT`). |
| `request_hash` | VARCHAR(64) | No | None | None | SHA-256 hash of normalized request body. |
| `status` | ENUM | No | `'IN_PROGRESS'`| `idempotency_status_enum`| `IN_PROGRESS`, `COMPLETED`, `FAILED`. |
| `response_code` | INT | Yes | NULL | None | Cached HTTP status code. |
| `response_body` | JSONB | Yes | NULL | None | Cached JSON response body. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Initial receipt timestamp. |
| `expires_at` | TIMESTAMPTZ | No | None | None | Retention TTL (typically 24 hours). |

---

### 2.11 Table: `transactional_outbox`
- **Domain**: Reliability Infrastructure (Messaging)
- **Purpose**: Implements the Transactional Outbox pattern to guarantee at-least-once message publishing without distributed dual-write inconsistencies.

| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `event_id` | UUID | No | `gen_random_uuid()` | PRIMARY KEY | Unique event identifier. |
| `aggregate_type` | VARCHAR(64) | No | None | None | Aggregate root name (`INVENTORY`, `PAYMENT`). |
| `aggregate_id` | VARCHAR(128)| No | None | None | Entity ID of aggregate. |
| `event_type` | VARCHAR(64) | No | None | None | Domain event type name (`PaymentSucceeded`). |
| `payload` | JSONB | No | None | None | Complete event body formatted as CloudEvents. |
| `correlation_id`| VARCHAR(128)| No | None | None | Distributed trace/request correlation ID. |
| `status` | VARCHAR(20) | No | `'PENDING'` | None | Status (`PENDING`, `PUBLISHED`, `FAILED`). |
| `retry_count` | INT | No | `0` | None | Publication retry attempts. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Insertion timestamp. |
| `published_at` | TIMESTAMPTZ | Yes | NULL | None | Publisher dispatch timestamp. |

---

### 2.12 Table: `audit_logs`
- **Domain**: Security & Compliance
- **Purpose**: Append-only immutable ledger tracking state changes for financial, inventory, and administrative actions.

| Column Name | Physical Type | Nullable | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `audit_id` | BIGSERIAL | No | Auto-increment | PRIMARY KEY | Sequential audit entry ID. |
| `entity_name` | VARCHAR(64) | No | None | None | Target entity (`PAYMENT`, `RESERVATION`). |
| `entity_id` | VARCHAR(128)| No | None | None | Identifier of affected entity. |
| `action` | VARCHAR(64) | No | None | None | Action performed (`RESERVE`, `CHARGE`). |
| `actor` | VARCHAR(128)| No | None | None | Customer ID, API key, or system service ID. |
| `state_before` | JSONB | Yes | NULL | None | Snapshot before modification. |
| `state_after` | JSONB | Yes | NULL | None | Snapshot after modification. |
| `ip_address` | VARCHAR(45) | Yes | NULL | None | Client IP (IPv4 / IPv6). |
| `correlation_id`| VARCHAR(128)| No | None | None | Distributed correlation ID. |
| `created_at` | TIMESTAMPTZ | No | `CURRENT_TIMESTAMP` | None | Timestamp (immutable). |
