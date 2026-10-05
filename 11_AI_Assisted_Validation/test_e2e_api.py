import pytest
import uuid
import sys
import os
from fastapi.testclient import TestClient

# Add 05_API/src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "05_API", "src")))

from main import app
from config import settings

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"

def test_product_catalog_discovery():
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data

def test_atomic_reservation_and_idempotency():
    product_id = settings.FLASH_SALE_PRODUCT_ID
    customer_id = str(uuid.uuid4())
    idempotency_key = f"test-idemp-{uuid.uuid4()}"

    # 1. First Reservation Attempt -> 201 Created
    payload = {
        "product_id": product_id,
        "quantity": 1,
        "customer_id": customer_id
    }
    headers = {"Idempotency-Key": idempotency_key}

    res1 = client.post("/api/v1/reservations", json=payload, headers=headers)
    assert res1.status_code == 201
    data1 = res1.json()
    assert "reservation_id" in data1
    assert data1["status"] == "RESERVED"

    # 2. Duplicate Request with Same Idempotency Key -> 200 OK (Cached hit)
    res2 = client.post("/api/v1/reservations", json=payload, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["reservation_id"] == data1["reservation_id"]

def test_payment_and_order_flow():
    product_id = settings.FLASH_SALE_PRODUCT_ID
    customer_id = str(uuid.uuid4())
    res_idem = f"res-idem-{uuid.uuid4()}"

    # Create reservation
    res = client.post("/api/v1/reservations", json={
        "product_id": product_id,
        "quantity": 1,
        "customer_id": customer_id
    }, headers={"Idempotency-Key": res_idem})
    assert res.status_code == 201
    res_id = res.json()["reservation_id"]

    # Charge payment
    pay_idem = f"pay-idem-{uuid.uuid4()}"
    pay_res = client.post("/api/v1/payments/charges", json={
        "reservation_id": res_id,
        "payment_token": "tok_visa_valid",
        "amount": 499.00,
        "currency": "USD"
    }, headers={"Idempotency-Key": pay_idem})

    assert pay_res.status_code == 201
    pay_data = pay_res.json()
    assert pay_data["status"] == "SUCCEEDED"

def test_payment_failure_triggers_release():
    product_id = settings.FLASH_SALE_PRODUCT_ID
    customer_id = str(uuid.uuid4())
    res_idem = f"fail-res-idem-{uuid.uuid4()}"

    # Create reservation
    res = client.post("/api/v1/reservations", json={
        "product_id": product_id,
        "quantity": 1,
        "customer_id": customer_id
    }, headers={"Idempotency-Key": res_idem})
    assert res.status_code == 201
    res_id = res.json()["reservation_id"]

    # Force payment decline
    pay_res = client.post("/api/v1/payments/charges", json={
        "reservation_id": res_id,
        "payment_token": "tok_force_decline",
        "amount": 499.00,
        "currency": "USD"
    }, headers={"Idempotency-Key": f"fail-pay-{uuid.uuid4()}"})

    assert pay_res.status_code == 402
    assert "PAYMENT_DECLINED" in str(pay_res.json())
