"""
SALESTORM 2026 | pytest conftest.py
=====================================
Fixes: TestClient does not trigger FastAPI lifespan in older Starlette versions.
This conftest:
  1. Overrides DATABASE_URL to use in-memory SQLite (no real Postgres needed)
  2. Creates all ORM tables via create_all() before any test runs
  3. Seeds the flash-sale product and initial inventory (100 units) in Redis + DB
"""
import os
import sys
import uuid
import pytest

# ---------------------------------------------------------------------------
# 1. Path setup — ensure 05_API/src is importable before anything else
# ---------------------------------------------------------------------------
SRC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "05_API", "src"))
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

# ---------------------------------------------------------------------------
# 2. Force SQLite in-memory BEFORE importing any app module
#    (pydantic-settings reads env at import time)
# ---------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./salestorm_test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"  # falls back to MockRedis if unavailable
os.environ["INITIAL_STOCK"] = "100"

# ---------------------------------------------------------------------------
# 3. Now import app internals (safe after env vars are set)
# ---------------------------------------------------------------------------
from config import settings
from database import engine, Base, SessionLocal, get_redis_client
from models import db_models
from services.inventory_service import InventoryService


@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    """
    Session-scoped fixture: create all tables and seed initial data once
    before any test in the session runs.
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Seed Category
        cat = db.query(db_models.Category).first()
        if not cat:
            cat = db_models.Category(
                category_id=str(uuid.uuid4()),
                name="Electronics",
                slug="electronics",
                description="High-end smartphones"
            )
            db.add(cat)
            db.commit()

        # Seed Product
        prod = db.query(db_models.Product).filter(
            db_models.Product.product_id == settings.FLASH_SALE_PRODUCT_ID
        ).first()
        if not prod:
            prod = db_models.Product(
                product_id=settings.FLASH_SALE_PRODUCT_ID,
                category_id=cat.category_id,
                sku="SALESTORM-PHONE-PRO",
                title="SALESTORM Flagship Pro (Titanium Edition)",
                description="Limited 100-unit release",
                base_price=499.00,
                currency="USD",
                is_active=True,
                is_flash_sale=True
            )
            db.add(prod)
            db.commit()

        # Seed Inventory + Redis stock counter
        inv_svc = InventoryService(db)
        inv_svc.initialize_stock(
            product_id=settings.FLASH_SALE_PRODUCT_ID,
            stock_qty=settings.INITIAL_STOCK
        )
    finally:
        db.close()

    yield  # All tests run here

    # Teardown: drop all tables after the full test session
    Base.metadata.drop_all(bind=engine)
    # Clean up test db file
    test_db_path = os.path.join(os.path.dirname(__file__), "..", "salestorm_test.db")
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except Exception:
            pass
