import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

try:
    from ..models.db_models import Order, InventoryReservation, Inventory
except (ImportError, ValueError):
    from models.db_models import Order, InventoryReservation, Inventory

class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def create_order_from_payment_event(self, event_data: dict) -> dict:
        payment_id = event_data["payment_id"]
        reservation_id = event_data["reservation_id"]
        customer_id = event_data["customer_id"]
        product_id = event_data["product_id"]
        quantity = event_data.get("quantity", 1)
        amount = event_data["amount"]
        currency = event_data.get("currency", "USD")

        existing_order = self.db.query(Order).filter(Order.reservation_id == reservation_id).first()
        if existing_order:
            return {
                "success": True,
                "duplicate": True,
                "order": existing_order
            }

        res = self.db.query(InventoryReservation).filter(
            InventoryReservation.reservation_id == reservation_id
        ).first()

        if not res:
            return {"success": False, "error": "RESERVATION_NOT_FOUND"}

        order_id = str(uuid.uuid4())
        order_number = f"ORD-2026-{uuid.uuid4().hex[:6].upper()}"

        order = Order(
            order_id=order_id,
            order_number=order_number,
            customer_id=customer_id,
            reservation_id=reservation_id,
            status="CONFIRMED",
            total_amount=amount,
            currency=currency,
            shipping_address="Standard Expedited Shipping"
        )
        self.db.add(order)
        res.status = "SOLD"

        self.db.execute(
            text("""
            UPDATE inventory 
            SET reserved_quantity = reserved_quantity - :qty,
                sold_quantity     = sold_quantity + :qty,
                version           = version + 1
            WHERE product_id = :prod_id
            """),
            {"qty": quantity, "prod_id": product_id}
        )

        self.db.commit()
        self.db.refresh(order)

        return {
            "success": True,
            "duplicate": False,
            "order": order
        }

    def get_order(self, order_id: str):
        return self.db.query(Order).filter(Order.order_id == order_id).first()
