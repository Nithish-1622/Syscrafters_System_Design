from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

try:
    from ..database import get_db
    from ..models.schemas import OrderResponse
    from ..services.order_service import OrderService
except (ImportError, ValueError):
    from database import get_db
    from models.schemas import OrderResponse
    from services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Order Management"])

@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    svc = OrderService(db)
    order = svc.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse(
        order_id=order.order_id,
        order_number=order.order_number,
        customer_id=order.customer_id,
        reservation_id=order.reservation_id,
        status=order.status,
        total_amount=float(order.total_amount),
        currency=order.currency,
        created_at=order.created_at.isoformat() if hasattr(order.created_at, "isoformat") else str(order.created_at)
    )
