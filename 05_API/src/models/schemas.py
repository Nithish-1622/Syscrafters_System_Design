from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal

# --- PRODUCT SCHEMAS ---
class ProductResponse(BaseModel):
    product_id: str
    sku: str
    title: str
    description: Optional[str] = None
    base_price: float
    currency: str = "USD"
    is_active: bool = True
    is_flash_sale: bool = False
    available_stock: Optional[int] = None

class PaginatedProductResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    cursor: Optional[str] = None

# --- RESERVATION SCHEMAS ---
class CreateReservationRequest(BaseModel):
    product_id: str = Field(..., description="UUID of flash-sale product")
    quantity: int = Field(1, ge=1, le=5, description="Number of units to reserve (max 1 for flash)")
    customer_id: str = Field(..., description="UUID of authenticated customer")

class ReservationResponse(BaseModel):
    reservation_id: str
    product_id: str
    customer_id: str
    quantity: int
    status: str
    expires_at: str
    created_at: str

# --- PAYMENT SCHEMAS ---
class ChargeRequest(BaseModel):
    reservation_id: str = Field(..., description="UUID of the active reservation")
    payment_token: str = Field(..., description="Tokenized payment source (Stripe tok_*)")
    amount: float = Field(..., gt=0)
    currency: str = "USD"
    payment_method: str = "CARD"

class PaymentResponse(BaseModel):
    payment_id: str
    reservation_id: str
    status: str
    amount: float
    currency: str
    provider_transaction_id: Optional[str] = None
    created_at: str

# --- ORDER SCHEMAS ---
class OrderResponse(BaseModel):
    order_id: str
    order_number: str
    customer_id: str
    reservation_id: str
    status: str
    total_amount: float
    currency: str
    created_at: str

# --- ERROR SCHEMA (RFC 7807) ---
class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    code: Optional[str] = None
