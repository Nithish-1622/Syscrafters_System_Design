import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text

try:
    from ..models.db_models import Inventory, InventoryReservation
    from ..database import get_redis_client
    from .lua_scripts import RedisLuaEngine
    from ..config import settings
except (ImportError, ValueError):
    from models.db_models import Inventory, InventoryReservation
    from database import get_redis_client
    from services.lua_scripts import RedisLuaEngine
    from config import settings

class InventoryService:
    def __init__(self, db: Session):
        self.db = db
        self.redis = get_redis_client()
        self.lua_engine = RedisLuaEngine(self.redis)

    def initialize_stock(self, product_id: str, stock_qty: int):
        self.redis.set(f"stock:item:{product_id}", stock_qty)
        inv = self.db.query(Inventory).filter(Inventory.product_id == product_id).first()
        if not inv:
            inv = Inventory(
                product_id=product_id,
                total_quantity=stock_qty,
                available_quantity=stock_qty,
                reserved_quantity=0,
                sold_quantity=0,
                version=0
            )
            self.db.add(inv)
            self.db.commit()

    def get_stock(self, product_id: str) -> int:
        stock = self.redis.get(f"stock:item:{product_id}")
        if stock is not None:
            return int(stock)
        inv = self.db.query(Inventory).filter(Inventory.product_id == product_id).first()
        return inv.available_quantity if inv else 0

    def reserve(self, product_id: str, customer_id: str, quantity: int, idempotency_key: str) -> dict:
        existing = self.db.query(InventoryReservation).filter(
            InventoryReservation.idempotency_key == idempotency_key
        ).first()
        if existing:
            return {
                "success": True,
                "duplicate": True,
                "reservation": existing
            }

        reservation_id = str(uuid.uuid4())
        lease_seconds = settings.RESERVATION_LEASE_SECONDS

        granted = self.lua_engine.reserve_stock(
            product_id=product_id,
            customer_id=customer_id,
            quantity=quantity,
            reservation_id=reservation_id,
            lease_seconds=lease_seconds
        )

        if not granted:
            return {
                "success": False,
                "error": "INVENTORY_OUT_OF_STOCK",
                "message": "Flash-sale inventory depleted."
            }

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        reservation = InventoryReservation(
            reservation_id=reservation_id,
            product_id=product_id,
            customer_id=customer_id,
            quantity=quantity,
            status="RESERVED",
            idempotency_key=idempotency_key,
            expires_at=expires_at
        )

        try:
            self.db.add(reservation)
            self.db.execute(
                text("""
                UPDATE inventory 
                SET available_quantity = available_quantity - :qty,
                    reserved_quantity  = reserved_quantity + :qty,
                    version            = version + 1
                WHERE product_id = :prod_id AND available_quantity >= :qty
                """),
                {"qty": quantity, "prod_id": product_id}
            )
            self.db.commit()
            self.db.refresh(reservation)
        except Exception as e:
            self.db.rollback()
            self.lua_engine.release_stock(product_id, reservation_id, quantity)
            raise e

        return {
            "success": True,
            "duplicate": False,
            "reservation": reservation
        }

    def release(self, reservation_id: str, reason: str = "EXPIRED") -> bool:
        res = self.db.query(InventoryReservation).filter(
            InventoryReservation.reservation_id == reservation_id,
            InventoryReservation.status.in_(["RESERVED", "PAYMENT_PENDING"])
        ).first()

        if not res:
            return False

        res.status = "RELEASED"
        self.db.execute(
            text("""
            UPDATE inventory 
            SET available_quantity = available_quantity + :qty,
                reserved_quantity  = reserved_quantity - :qty,
                version            = version + 1
            WHERE product_id = :prod_id
            """),
            {"qty": res.quantity, "prod_id": res.product_id}
        )
        self.db.commit()
        self.lua_engine.release_stock(res.product_id, reservation_id, res.quantity)
        return True
