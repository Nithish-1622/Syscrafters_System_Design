"""
SALESTORM 2026 | Database Initialization & Seeding Script
=========================================================
Author: Engineering Team (MEMBER 1, 2, 3)
Purpose: Initializes database schema and seeds initial flash-sale SKU (100 units)
         and baseline customer accounts for automated testing and load simulation.
Supports: PostgreSQL (Production / Docker) & SQLite (Local / In-Memory fallback)
"""

import os
import sys
import uuid
import datetime
from decimal import Decimal

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FLASH_SALE_PRODUCT_ID = "550e8400-e29b-41d4-a716-446655440000"
FLASH_SALE_SKU = "SALESTORM-PHONE-PRO"
INITIAL_STOCK = 100
FLASH_SALE_PRICE = 499.00


def seed_database(db_session):
    """Seeds the catalog with initial Category, Product, Inventory (100 units), and Deal."""
    from sqlalchemy import text

    print("[*] Seeding SALESTORM Database...")

    # 1. Insert Category
    cat_id = str(uuid.uuid4())
    db_session.execute(
        text("""
        INSERT INTO categories (category_id, name, slug, description, created_at, updated_at)
        VALUES (:cat_id, 'Electronics', 'electronics', 'High-end smartphones and consumer gadgets', NOW(), NOW())
        ON CONFLICT (name) DO NOTHING;
    """),
        {"cat_id": cat_id},
    )

    # Fetch category_id
    cat_row = db_session.execute(
        text("SELECT category_id FROM categories WHERE slug = 'electronics'")
    ).fetchone()
    cat_id = cat_row[0]

    # 2. Insert Flash-Sale Product
    db_session.execute(
        text("""
        INSERT INTO products (product_id, category_id, sku, title, description, base_price, currency, is_active, is_flash_sale, created_at, updated_at)
        VALUES (:prod_id, :cat_id, :sku, 'SALESTORM Flagship Pro (Titanium Edition)', 
                'Limited 100-unit release with next-gen quantum processor', :price, 'USD', TRUE, TRUE, NOW(), NOW())
        ON CONFLICT (sku) DO UPDATE SET is_active = TRUE, is_flash_sale = TRUE;
    """),
        {
            "prod_id": FLASH_SALE_PRODUCT_ID,
            "cat_id": cat_id,
            "sku": FLASH_SALE_SKU,
            "price": FLASH_SALE_PRICE,
        },
    )

    # 3. Insert or Reset Inventory (Exactly 100 units total)
    db_session.execute(
        text("""
        INSERT INTO inventory (inventory_id, product_id, total_quantity, available_quantity, reserved_quantity, sold_quantity, version, created_at, updated_at)
        VALUES (:inv_id, :prod_id, :qty, :qty, 0, 0, 0, NOW(), NOW())
        ON CONFLICT (product_id) DO UPDATE 
        SET total_quantity = :qty, available_quantity = :qty, reserved_quantity = 0, sold_quantity = 0, version = 0, updated_at = NOW();
    """),
        {
            "inv_id": str(uuid.uuid4()),
            "prod_id": FLASH_SALE_PRODUCT_ID,
            "qty": INITIAL_STOCK,
        },
    )

    # 4. Insert Flash Sale Deal Rule
    db_session.execute(
        text("""
        INSERT INTO flash_sale_deals (deal_id, product_id, sale_price, allocated_quantity, starts_at, ends_at, is_active, created_at, updated_at)
        VALUES (:deal_id, :prod_id, :sale_price, :qty, NOW() - INTERVAL '1 HOUR', NOW() + INTERVAL '24 HOUR', TRUE, NOW(), NOW())
        ON CONFLICT DO NOTHING;
    """),
        {
            "deal_id": str(uuid.uuid4()),
            "prod_id": FLASH_SALE_PRODUCT_ID,
            "sale_price": FLASH_SALE_PRICE,
            "qty": INITIAL_STOCK,
        },
    )

    # 5. Insert Baseline Customers
    for i in range(1, 101):
        cust_id = f"c0000000-0000-0000-0000-{i:012d}"
        email = f"customer_{i:03d}@salestorm.io"
        db_session.execute(
            text("""
            INSERT INTO customers (customer_id, email, password_hash, full_name, phone_number, is_active, created_at, updated_at)
            VALUES (:cust_id, :email, 'hash_pbkdf2_test', :name, '+1-555-0100', TRUE, NOW(), NOW())
            ON CONFLICT (email) DO NOTHING;
        """),
            {
                "cust_id": cust_id,
                "email": email,
                "name": f"Flash Customer {i:03d}",
            },
        )

    db_session.commit()
    print(
        f"[+] Seed complete! Flash-Sale SKU '{FLASH_SALE_SKU}' initialized with exactly {INITIAL_STOCK} available units."
    )


if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://salestorm_user:salestorm_password@localhost:5432/salestorm_db",
    )
    try:
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        seed_database(session)
        session.close()
    except Exception as e:
        print(f"[!] Database connection failed: {e}")
        print(
            "[*] To run locally with Docker, execute: docker-compose up -d postgres"
        )
