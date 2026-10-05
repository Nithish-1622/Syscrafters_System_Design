# SALESTORM 2026 | Authorization Specification & Access Control

## 1. Access Control Model

SALESTORM combines **Role-Based Access Control (RBAC)** with **Resource-Level Attribute-Based Access Control (ABAC)** to ensure fine-grained isolation and enforce the principle of least privilege.

---

## 2. Role Definitions & Scopes

| Role | Scope / Permissions | Allowed Endpoints |
| :--- | :--- | :--- |
| **`CUSTOMER`** | Manage own cart, create own reservations, initiate own payments, read own orders. | `GET /products/*`, `POST /reservations`, `POST /payments`, `GET /orders/*` (owned) |
| **`ADMIN`** | Catalog management, inventory replenishment, manual reconciliation, system config. | Full CRUD on `/products`, `/inventory`, `/reconciliation/*` |
| **`FULFILLMENT_AGENT`** | View confirmed orders, dispatch shipments, update tracking numbers. | `GET /orders`, `POST /shipments/*` |
| **`SERVICE_ACCOUNT`** | Machine-to-machine internal asynchronous processing and event relaying. | Internal event topics, private gRPC endpoints |

---

## 3. Resource Ownership Invariant (ABAC)

Authentication answers *"Who are you?"*; Authorization answers *"Do you own this specific record?"*

### Rule: Strict Data Isolation by Customer ID
A customer with a valid JWT must never be permitted to read, confirm, or cancel another customer's reservation or order.

```
[ Request: GET /api/v1/orders/{orderId} ]
                    │
                    ▼
          ┌───────────────────┐
          │ Verify JWT Token  │ ──► sub = "cust-123"
          └───────────────────┘
                    │
                    ▼
          ┌───────────────────┐
          │ Query Database    │ ──► SELECT customer_id FROM orders WHERE order_id = :orderId
          └───────────────────┘
                    │
                    ▼
          ┌───────────────────┐
          │ Ownership Guard   │
          │ cust-123 == DB.id?│
          └───────────────────┘
               │         │
          YES  │         │  NO
               ▼         ▼
          [ 200 OK ]   [ 403 Forbidden ]
                       (RFC 7807 Error)
```

### Authorization Enforcement Code Contract:
```python
def authorize_order_access(authenticated_user_id: str, order: Order, user_role: str):
    if user_role == "ADMIN" or user_role == "FULFILLMENT_AGENT":
        return True
    if order.customer_id == authenticated_user_id:
        return True
    raise ForbiddenException(
        code="ACCESS_DENIED", 
        detail="Customer is not authorized to access this order."
    )
```
