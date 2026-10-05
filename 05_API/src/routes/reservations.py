from fastapi import APIRouter, Depends, HTTPException, Header, Response, status
from sqlalchemy.orm import Session
from typing import Optional

try:
    from ..database import get_db
    from ..models.schemas import CreateReservationRequest, ReservationResponse
    from ..services.inventory_service import InventoryService
except (ImportError, ValueError):
    from database import get_db
    from models.schemas import CreateReservationRequest, ReservationResponse
    from services.inventory_service import InventoryService

router = APIRouter(prefix="/reservations", tags=["Inventory & Reservation"])

@router.post("", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
def create_reservation(
    req: CreateReservationRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    svc = InventoryService(db)
    result = svc.reserve(
        product_id=req.product_id,
        customer_id=req.customer_id,
        quantity=req.quantity,
        idempotency_key=idempotency_key
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INVENTORY_OUT_OF_STOCK",
                "message": "All flash sale units have been reserved or sold out."
            }
        )

    res = result["reservation"]
    if result["duplicate"]:
        response.status_code = status.HTTP_200_OK

    return ReservationResponse(
        reservation_id=res.reservation_id,
        product_id=res.product_id,
        customer_id=res.customer_id,
        quantity=res.quantity,
        status=res.status,
        expires_at=res.expires_at.isoformat() if hasattr(res.expires_at, "isoformat") else str(res.expires_at),
        created_at=res.created_at.isoformat() if hasattr(res.created_at, "isoformat") else str(res.created_at)
    )

@router.delete("/{reservation_id}/release", status_code=status.HTTP_204_NO_CONTENT)
def release_reservation(reservation_id: str, db: Session = Depends(get_db)):
    svc = InventoryService(db)
    released = svc.release(reservation_id, reason="CLIENT_ABANDONED")
    if not released:
        raise HTTPException(status_code=404, detail="Reservation not found or already released/confirmed")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
