from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

try:
    from ..database import get_db
    from ..models.db_models import Product, Inventory
    from ..models.schemas import ProductResponse, PaginatedProductResponse
except (ImportError, ValueError):
    from database import get_db
    from models.db_models import Product, Inventory
    from models.schemas import ProductResponse, PaginatedProductResponse

router = APIRouter(prefix="/products", tags=["Product Discovery"])

@router.get("", response_model=PaginatedProductResponse)
def list_products(limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_active == True).limit(limit).all()
    items = []
    for p in products:
        inv = db.query(Inventory).filter(Inventory.product_id == p.product_id).first()
        items.append(ProductResponse(
            product_id=p.product_id,
            sku=p.sku,
            title=p.title,
            description=p.description,
            base_price=float(p.base_price),
            currency=p.currency,
            is_active=p.is_active,
            is_flash_sale=p.is_flash_sale,
            available_stock=inv.available_quantity if inv else 0
        ))
    return PaginatedProductResponse(items=items, total=len(items))

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: str, db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.product_id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")
    inv = db.query(Inventory).filter(Inventory.product_id == p.product_id).first()
    return ProductResponse(
        product_id=p.product_id,
        sku=p.sku,
        title=p.title,
        description=p.description,
        base_price=float(p.base_price),
        currency=p.currency,
        is_active=p.is_active,
        is_flash_sale=p.is_flash_sale,
        available_stock=inv.available_quantity if inv else 0
    )
