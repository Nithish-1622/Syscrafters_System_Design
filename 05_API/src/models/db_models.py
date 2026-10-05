import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Numeric, Boolean, DateTime, ForeignKey, 
    Text, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship

try:
    from ..database import Base
except (ImportError, ValueError):
    from database import Base

class Category(Base):
    __tablename__ = "categories"
    category_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True)
    slug = Column(String(120), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Customer(Base):
    __tablename__ = "customers"
    customer_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    phone_number = Column(String(30), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    product_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    category_id = Column(String(36), ForeignKey("categories.category_id"), nullable=False)
    sku = Column(String(64), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    base_price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="USD")
    is_active = Column(Boolean, default=True)
    is_flash_sale = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Inventory(Base):
    __tablename__ = "inventory"
    inventory_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String(36), ForeignKey("products.product_id"), nullable=False, unique=True)
    total_quantity = Column(Integer, nullable=False)
    available_quantity = Column(Integer, nullable=False)
    reserved_quantity = Column(Integer, nullable=False, default=0)
    sold_quantity = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        CheckConstraint("available_quantity >= 0", name="chk_available_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="chk_reserved_non_negative"),
        CheckConstraint("sold_quantity >= 0", name="chk_sold_non_negative"),
        CheckConstraint(
            "available_quantity + reserved_quantity + sold_quantity = total_quantity",
            name="chk_inventory_conservation"
        ),
    )

class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    reservation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String(36), ForeignKey("products.product_id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.customer_id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="RESERVED")
    idempotency_key = Column(String(128), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

class Payment(Base):
    __tablename__ = "payments"
    payment_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reservation_id = Column(String(36), ForeignKey("inventory_reservations.reservation_id"), nullable=False)
    customer_id = Column(String(36), ForeignKey("customers.customer_id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="USD")
    payment_method = Column(String(50), default="CARD")
    provider = Column(String(50), default="STRIPE")
    provider_transaction_id = Column(String(128), unique=True, nullable=True)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default="INITIATED")
    failure_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    order_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_number = Column(String(32), nullable=False, unique=True)
    customer_id = Column(String(36), ForeignKey("customers.customer_id"), nullable=False)
    reservation_id = Column(String(36), ForeignKey("inventory_reservations.reservation_id"), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default="CONFIRMED")
    total_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="USD")
    shipping_address = Column(Text, nullable=True)
    version = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    idempotency_key = Column(String(128), primary_key=True)
    scope = Column(String(64), nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="IN_PROGRESS")
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

class TransactionalOutbox(Base):
    __tablename__ = "transactional_outbox"
    event_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    aggregate_type = Column(String(64), nullable=False)
    aggregate_id = Column(String(128), nullable=False)
    event_type = Column(String(64), nullable=False)
    payload = Column(Text, nullable=False)
    correlation_id = Column(String(128), nullable=False)
    status = Column(String(20), default="PENDING")
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
