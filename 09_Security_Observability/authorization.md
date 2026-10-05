# SALESTORM 2026 | Authorization & Access Control Architecture

## 1. Multi-Dimensional Access Control Model

SALESTORM implements **Role-Based Access Control (RBAC)** complemented by **Attribute-Based Access Control (ABAC)** at the resource level:

```
[ Inbound Request with Identity Context ]
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│ STEP 1: ROLE-BASED ACCESS CONTROL (RBAC)               │
│ - Does the caller's role have permission to execute    │
│   this operation?                                      │
│ - Example: Only ADMIN can call POST /inventory/restock │
└────────────────────────────────────────────────────────┘
                 │ (Passed)
                 ▼
┌────────────────────────────────────────────────────────┐
│ STEP 2: RESOURCE-LEVEL OWNERSHIP (ABAC)                │
│ - Does the caller OWN the specific resource identified │
│   by the URI parameter?                                │
│ - Condition: `request.jwt.sub == resource.customer_id` │
└────────────────────────────────────────────────────────┘
                 │ (Passed)
                 ▼
        [ Allow Execution ]
```

---

## 2. Authorization Matrix

| Endpoint | Method | `ANONYMOUS` | `CUSTOMER` | `FULFILLMENT_AGENT` | `ADMIN` | `SERVICE_ACCOUNT` |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `/api/v1/products` | GET | Allowed | Allowed | Allowed | Allowed | Allowed |
| `/api/v1/products` | POST/PUT | Denied | Denied | Denied | Allowed | Denied |
| `/api/v1/reservations` | POST | Denied | Allowed | Denied | Allowed | Denied |
| `/api/v1/reservations/{id}/confirm`| POST | Denied | Own Only | Denied | Allowed | Allowed |
| `/api/v1/payments` | POST | Denied | Own Only | Denied | Allowed | Denied |
| `/api/v1/payments/webhook` | POST | Denied (HMAC)| Denied | Denied | Denied | Gateway Only |
| `/api/v1/orders/{id}` | GET | Denied | Own Only | Allowed | Allowed | Allowed |
| `/api/v1/shipments/{id}` | POST | Denied | Denied | Allowed | Allowed | Allowed |

---

## 3. Database-Level Least-Privilege Grants

In production PostgreSQL, microservice database users are granted strictly bounded privileges:

```sql
-- Inventory Service App User
CREATE ROLE inventory_app_user WITH LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE salestorm TO inventory_app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE inventory, inventory_reservations, transactional_outbox TO inventory_app_user;
-- Revoke dangerous privileges
REVOKE DELETE, TRUNCATE, DROP ON ALL TABLES IN SCHEMA public FROM inventory_app_user;
```
Even if an application instance is compromised, an attacker cannot drop tables or delete customer records.
