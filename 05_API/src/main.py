import os
import sys
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

# Ensure src is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from .config import settings
    from .database import engine, Base, SessionLocal, get_redis_client
    from .models import db_models
    from .routes import products, reservations, payments, orders
    from .services.inventory_service import InventoryService
    from .events.outbox_relay import outbox_relay
except (ImportError, ValueError):
    from config import settings
    from database import engine, Base, SessionLocal, get_redis_client
    from models import db_models
    from routes import products, reservations, payments, orders
    from services.inventory_service import InventoryService
    from events.outbox_relay import outbox_relay

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database Tables & Seed Flash SKU
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed default category & product if not present
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

        # Seed inventory & pre-warm Redis
        inv_svc = InventoryService(db)
        inv_svc.initialize_stock(
            product_id=settings.FLASH_SALE_PRODUCT_ID,
            stock_qty=settings.INITIAL_STOCK
        )
    finally:
        db.close()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="SALESTORM 2026 Production-Grade High-Concurrency Flash-Sale API Engine",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Correlation & Request Timing Middleware
@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    corr_id = request.headers.get("X-Correlation-Id", str(uuid.uuid4()))
    response: Response = await call_next(request)
    response.headers["X-Correlation-Id"] = corr_id
    return response

# Register API v1 Routers
app.include_router(products.router, prefix="/api/v1")
app.include_router(reservations.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")

@app.get("/health", tags=["Health & Observability"])
def health_check():
    return {
        "status": "HEALTHY",
        "service": "salestorm-api",
        "version": settings.APP_VERSION
    }

@app.get("/metrics", tags=["Health & Observability"])
def get_metrics():
    db = SessionLocal()
    try:
        inv = db.query(db_models.Inventory).filter(
            db_models.Inventory.product_id == settings.FLASH_SALE_PRODUCT_ID
        ).first()
        res_count = db.query(db_models.InventoryReservation).count()
        pay_count = db.query(db_models.Payment).count()
        order_count = db.query(db_models.Order).count()
        return {
            "initial_stock": settings.INITIAL_STOCK,
            "available_stock": inv.available_quantity if inv else 0,
            "reserved_stock": inv.reserved_quantity if inv else 0,
            "sold_stock": inv.sold_quantity if inv else 0,
            "total_reservations": res_count,
            "total_payments": pay_count,
            "total_orders": order_count
        }
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)
