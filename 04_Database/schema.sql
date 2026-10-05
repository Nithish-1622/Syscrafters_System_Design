-- ============================================================================
-- SALESTORM 2026 | HIGH-SCALE FLASH-SALE SYSTEM
-- 04_Database/schema.sql
-- Relational Persistence Engine: PostgreSQL 15+ / ANSI SQL Compliant
-- Author: Member 3 (Database, API, Event, Reliability & Security Engineer)
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

CREATE TYPE reservation_status_enum AS ENUM (
    'PENDING',
    'RESERVED',
    'PAYMENT_PENDING',
    'CONFIRMED',
    'SOLD',
    'PAYMENT_FAILED',
    'EXPIRED',
    'RELEASED'
);

CREATE TYPE payment_status_enum AS ENUM (
    'INITIATED',
    'PROCESSING',
    'SUCCEEDED',
    'FAILED',
    'TIMED_OUT',
    'RECONCILIATION_REQUIRED',
    'REFUNDED'
);

CREATE TYPE order_status_enum AS ENUM (
    'CREATED',
    'PAYMENT_PENDING',
    'CONFIRMED',
    'PROCESSING',
    'SHIPPED',
    'OUT_FOR_DELIVERY',
    'DELIVERED',
    'CANCELLED',
    'FAILED'
);

CREATE TYPE shipment_status_enum AS ENUM (
    'PENDING',
    'DISPATCHED',
    'IN_TRANSIT',
    'OUT_FOR_DELIVERY',
    'DELIVERED',
    'RETURNED',
    'FAILED'
);

CREATE TYPE notification_status_enum AS ENUM (
    'PENDING',
    'SENT',
    'DELIVERED',
    'FAILED'
);

CREATE TYPE idempotency_status_enum AS ENUM (
    'IN_PROGRESS',
    'COMPLETED',
    'FAILED'
);

-- ============================================================================
-- 1. CATEGORY
-- ============================================================================
CREATE TABLE categories (
    category_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(120) NOT NULL UNIQUE,
    description TEXT,
    parent_category_id UUID REFERENCES categories(category_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 2. CUSTOMER
-- ============================================================================
CREATE TABLE customers (
    customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone_number VARCHAR(30),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 3. PRODUCT
-- ============================================================================
CREATE TABLE products (
    product_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id UUID NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,
    sku VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    base_price NUMERIC(12, 2) NOT NULL CHECK (base_price >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_flash_sale BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 4. INVENTORY
-- Core invariant: available_quantity + reserved_quantity + sold_quantity = total_stock
-- Invariants enforced via CHECK constraints:
-- available_quantity >= 0, reserved_quantity >= 0, sold_quantity >= 0
-- ============================================================================
CREATE TABLE inventory (
    inventory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL UNIQUE REFERENCES products(product_id) ON DELETE RESTRICT,
    total_quantity INT NOT NULL CHECK (total_quantity >= 0),
    available_quantity INT NOT NULL CHECK (available_quantity >= 0),
    reserved_quantity INT NOT NULL CHECK (reserved_quantity >= 0),
    sold_quantity INT NOT NULL CHECK (sold_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_inventory_quantities_balance 
        CHECK (available_quantity + reserved_quantity + sold_quantity = total_quantity)
);

-- ============================================================================
-- 5. INVENTORY_RESERVATION
-- Manages temporary hold of inventory during checkout
-- Idempotency key guarantees no duplicate reservation creation per checkout attempt
-- ============================================================================
CREATE TABLE inventory_reservations (
    reservation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inventory_id UUID NOT NULL REFERENCES inventory(inventory_id) ON DELETE RESTRICT,
    customer_id UUID NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    quantity INT NOT NULL CHECK (quantity > 0),
    status reservation_status_enum NOT NULL DEFAULT 'RESERVED',
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 6. CART & CART_ITEM
-- ============================================================================
CREATE TABLE carts (
    cart_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL UNIQUE REFERENCES customers(customer_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cart_items (
    cart_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cart_id UUID NOT NULL REFERENCES carts(cart_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity INT NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_cart_product UNIQUE (cart_id, product_id)
);

-- ============================================================================
-- 7. PROMOTIONS / FLASH SALE DEALS
-- ============================================================================
CREATE TABLE flash_sale_deals (
    deal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE CASCADE,
    sale_price NUMERIC(12, 2) NOT NULL CHECK (sale_price >= 0),
    allocated_quantity INT NOT NULL CHECK (allocated_quantity > 0),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_deal_time_window CHECK (ends_at > starts_at)
);

-- ============================================================================
-- 8. ORDER & ORDER_ITEM
-- Order created after or alongside payment confirmation in saga flow
-- ============================================================================
CREATE TABLE orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(32) NOT NULL UNIQUE,
    customer_id UUID NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    reservation_id UUID NOT NULL UNIQUE REFERENCES inventory_reservations(reservation_id) ON DELETE RESTRICT,
    status order_status_enum NOT NULL DEFAULT 'CREATED',
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    shipping_address_json JSONB NOT NULL,
    billing_address_json JSONB NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
    order_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    total_price NUMERIC(12, 2) NOT NULL CHECK (total_price >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 9. PAYMENT
-- Payment tracking with external provider references, idempotency, and reconciliation
-- ============================================================================
CREATE TABLE payments (
    payment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(order_id) ON DELETE RESTRICT,
    reservation_id UUID NOT NULL REFERENCES inventory_reservations(reservation_id) ON DELETE RESTRICT,
    customer_id UUID NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    payment_method VARCHAR(50) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    provider_transaction_id VARCHAR(128) UNIQUE,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    status payment_status_enum NOT NULL DEFAULT 'INITIATED',
    failure_reason VARCHAR(255),
    reconciliation_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 10. SHIPMENT
-- ============================================================================
CREATE TABLE shipments (
    shipment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL UNIQUE REFERENCES orders(order_id) ON DELETE RESTRICT,
    carrier VARCHAR(100) NOT NULL,
    tracking_number VARCHAR(128) UNIQUE,
    status shipment_status_enum NOT NULL DEFAULT 'PENDING',
    dispatched_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 11. NOTIFICATION
-- ============================================================================
CREATE TABLE notifications (
    notification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    channel VARCHAR(30) NOT NULL, -- EMAIL, SMS, PUSH
    template_type VARCHAR(50) NOT NULL, -- RESERVATION_CONFIRMED, PAYMENT_SUCCESS, ORDER_CONFIRMED, SHIPMENT_UPDATE
    status notification_status_enum NOT NULL DEFAULT 'PENDING',
    recipient VARCHAR(255) NOT NULL,
    payload_json JSONB NOT NULL,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 12. IDEMPOTENCY_RECORDS
-- Dedicated distributed idempotency table for HTTP APIs & Command Handlers
-- ============================================================================
CREATE TABLE idempotency_records (
    idempotency_key VARCHAR(128) PRIMARY KEY,
    scope VARCHAR(64) NOT NULL, -- e.g., 'RESERVATION_CREATE', 'PAYMENT_CHARGE', 'ORDER_CREATE'
    request_hash VARCHAR(64) NOT NULL, -- SHA-256 of request payload
    status idempotency_status_enum NOT NULL DEFAULT 'IN_PROGRESS',
    response_code INT,
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL
);

-- ============================================================================
-- 13. TRANSACTIONAL_OUTBOX
-- Reliable asynchronous event publishing (Guarantees At-Least-Once Delivery)
-- Avoids Dual-Write Distributed Inconsistencies
-- ============================================================================
CREATE TABLE transactional_outbox (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(64) NOT NULL, -- 'INVENTORY', 'PAYMENT', 'ORDER', 'RESERVATION'
    aggregate_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL, -- e.g., 'ReservationCreated', 'PaymentSucceeded'
    payload JSONB NOT NULL,
    correlation_id VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'PUBLISHED', 'FAILED'
    retry_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);

-- ============================================================================
-- 14. AUDIT_LOG
-- Immutable ledger for high-value business & financial transitions
-- ============================================================================
CREATE TABLE audit_logs (
    audit_id BIGSERIAL PRIMARY KEY,
    entity_name VARCHAR(64) NOT NULL,
    entity_id VARCHAR(128) NOT NULL,
    action VARCHAR(64) NOT NULL, -- 'RESERVED', 'CONFIRMED', 'PAYMENT_CAPTURED', 'RELEASED'
    actor VARCHAR(128) NOT NULL, -- Customer UUID or System Service ID
    state_before JSONB,
    state_after JSONB,
    ip_address VARCHAR(45),
    correlation_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES FOR HIGH-THROUGHPUT ACCESS PATTERNS
-- ============================================================================

-- Inventory lookup by product (hotspot read/update path)
CREATE INDEX idx_inventory_product_id ON inventory(product_id);

-- Reservation active state & expiry reaper scanning
CREATE INDEX idx_reservations_status_expires_at 
    ON inventory_reservations(status, expires_at) 
    WHERE status IN ('RESERVED', 'PAYMENT_PENDING');

-- Reservation lookup by customer & idempotency
CREATE INDEX idx_reservations_customer ON inventory_reservations(customer_id);
CREATE INDEX idx_reservations_idempotency ON inventory_reservations(idempotency_key);

-- Payment lookup by provider reference & reservation
CREATE INDEX idx_payments_provider_tx ON payments(provider_transaction_id);
CREATE INDEX idx_payments_reservation_id ON payments(reservation_id);
CREATE INDEX idx_payments_order_id ON payments(order_id);
CREATE INDEX idx_payments_status ON payments(status);

-- Order lookup by customer (customer dashboard)
CREATE INDEX idx_orders_customer_id ON orders(customer_id, created_at DESC);
CREATE INDEX idx_orders_reservation_id ON orders(reservation_id);
CREATE INDEX idx_orders_status ON orders(status);

-- Outbox polling index (CDC / Polling publisher pattern)
CREATE INDEX idx_outbox_pending ON transactional_outbox(created_at) WHERE status = 'PENDING';

-- Idempotency expiry index (TTL background cleanup)
CREATE INDEX idx_idempotency_expires_at ON idempotency_records(expires_at);

-- Audit log lookup by entity & correlation ID
CREATE INDEX idx_audit_entity ON audit_logs(entity_name, entity_id);
CREATE INDEX idx_audit_correlation ON audit_logs(correlation_id);
