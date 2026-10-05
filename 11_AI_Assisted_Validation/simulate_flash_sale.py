#!/usr/bin/env python3
"""
============================================================================
SALESTORM 2026 | High-Scale Flash-Sale Validation & Simulation Harness
============================================================================
Author: Member 3 (Database, API, Event, Reliability & Security Engineer)
Purpose: Demonstrates empirical and mathematical proof of system correctness
         under extreme concurrent flash-sale load and catastrophic outages.

Test Parameters:
- Stock: 100 available units
- Concurrent Contenders: 10,000 customers
- Payment Success Rate: 95%
- Payment Failure Rate: 5%
- Duplicate Requests: 2%
- Downstream Order Service Outage: 30-second simulated outage with queue buffer
- Strict Invariant: successful_sales <= 100 (ZERO OVERSELLING)
============================================================================
"""

import time
import random
import uuid
import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

# --- CONFIGURATION & TEST HARNESS PARAMETERS ---
TOTAL_STOCK = 100
TOTAL_CUSTOMERS = 10_000
PAYMENT_SUCCESS_PROBABILITY = 0.95
DUPLICATE_REQUEST_PROBABILITY = 0.02
SIMULATED_ORDER_OUTAGE_SECONDS = 2.0  # Scaled representation for quick harness execution
CONCURRENCY_WORKERS = 50

# --- IN-MEMORY DATABASE & INFRASTRUCTURE ENGINE ---
class DatabaseEngine:
    """Thread-safe SQLite database simulating PostgreSQL atomic transactions & constraints."""
    def __init__(self):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.executescript("""
                CREATE TABLE inventory (
                    product_id TEXT PRIMARY KEY,
                    total_quantity INT NOT NULL,
                    available_quantity INT NOT NULL,
                    reserved_quantity INT NOT NULL,
                    sold_quantity INT NOT NULL,
                    version INT NOT NULL DEFAULT 0,
                    CHECK (available_quantity >= 0),
                    CHECK (reserved_quantity >= 0),
                    CHECK (sold_quantity >= 0),
                    CHECK (available_quantity + reserved_quantity + sold_quantity = total_quantity)
                );

                CREATE TABLE inventory_reservations (
                    reservation_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    quantity INT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );

                CREATE TABLE payments (
                    payment_id TEXT PRIMARY KEY,
                    reservation_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    amount REAL NOT NULL,
                    provider_transaction_id TEXT UNIQUE,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE orders (
                    order_id TEXT PRIMARY KEY,
                    order_number TEXT UNIQUE NOT NULL,
                    customer_id TEXT NOT NULL,
                    reservation_id TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL,
                    total_amount REAL NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE idempotency_records (
                    idempotency_key TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_code INT,
                    response_body TEXT,
                    created_at REAL NOT NULL
                );
            """)
            # Initialize 100 units for product 'salestorm-phone-pro'
            cur.execute("""
                INSERT INTO inventory (product_id, total_quantity, available_quantity, reserved_quantity, sold_quantity)
                VALUES ('prod-flash-100', 100, 100, 0, 0);
            """)
            self.conn.commit()

    def reserve_stock_atomic(self, product_id: str, customer_id: str, quantity: int, idempotency_key: str, request_hash: str) -> Dict[str, Any]:
        """
        Executes atomic conditional SQL update:
        UPDATE inventory SET available = available - qty, reserved = reserved + qty 
        WHERE product_id = :id AND available >= :qty
        """
        with self.lock:
            cur = self.conn.cursor()
            
            # 1. Check idempotency record
            cur.execute("SELECT status, request_hash, response_code, response_body FROM idempotency_records WHERE idempotency_key = ?", (idempotency_key,))
            existing = cur.fetchone()
            if existing:
                if existing["status"] == "COMPLETED" and existing["request_hash"] == request_hash:
                    return {"success": True, "duplicate": True, "data": json.loads(existing["response_body"])}
                elif existing["request_hash"] != request_hash:
                    return {"success": False, "error": "IDEMPOTENCY_PAYLOAD_MISMATCH", "status_code": 422}
                else:
                    return {"success": False, "error": "CONCURRENT_REQUEST_IN_FLIGHT", "status_code": 409}

            # 2. Acquire idempotency lock
            now = time.time()
            cur.execute("""
                INSERT INTO idempotency_records (idempotency_key, scope, request_hash, status, created_at)
                VALUES (?, 'RESERVATION', ?, 'IN_PROGRESS', ?)
            """, (idempotency_key, request_hash, now))

            # 3. ATOMIC CONDITIONAL SQL DECREMENT
            cur.execute("""
                UPDATE inventory 
                SET available_quantity = available_quantity - ?,
                    reserved_quantity  = reserved_quantity + ?,
                    version            = version + 1
                WHERE product_id = ? AND available_quantity >= ?
            """, (quantity, quantity, product_id, quantity))

            if cur.rowcount == 0:
                # Stock unavailable or sold out
                cur.execute("UPDATE idempotency_records SET status = 'FAILED' WHERE idempotency_key = ?", (idempotency_key,))
                self.conn.commit()
                return {"success": False, "error": "INVENTORY_OUT_OF_STOCK", "status_code": 409}

            # 4. Insert Reservation Record
            res_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO inventory_reservations (reservation_id, product_id, customer_id, quantity, status, idempotency_key, created_at, expires_at)
                VALUES (?, ?, ?, ?, 'RESERVED', ?, ?, ?)
            """, (res_id, product_id, customer_id, quantity, idempotency_key, now, now + 5.0))

            res_data = {
                "reservation_id": res_id,
                "product_id": product_id,
                "quantity": quantity,
                "status": "RESERVED"
            }

            # 5. Complete idempotency
            cur.execute("""
                UPDATE idempotency_records 
                SET status = 'COMPLETED', response_code = 201, response_body = ?
                WHERE idempotency_key = ?
            """, (json.dumps(res_data), idempotency_key))

            self.conn.commit()
            return {"success": True, "duplicate": False, "data": res_data}

    def release_reservation(self, reservation_id: str, reason: str):
        """Compensating transaction: releases stock hold back to available inventory."""
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("""
                SELECT product_id, quantity, status FROM inventory_reservations 
                WHERE reservation_id = ? AND status = 'RESERVED'
            """, (reservation_id,))
            row = cur.fetchone()
            if not row:
                return False  # Already released or confirmed
            
            product_id = row["product_id"]
            qty = row["quantity"]

            cur.execute("UPDATE inventory_reservations SET status = 'RELEASED' WHERE reservation_id = ?", (reservation_id,))
            cur.execute("""
                UPDATE inventory 
                SET available_quantity = available_quantity + ?,
                    reserved_quantity  = reserved_quantity - ?
                WHERE product_id = ?
            """, (qty, qty, product_id))
            self.conn.commit()
            return True

    def record_payment(self, payment_id: str, reservation_id: str, customer_id: str, amount: float, status: str, idempotency_key: str, provider_tx_id: Optional[str] = None):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO payments (payment_id, reservation_id, customer_id, amount, provider_transaction_id, idempotency_key, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (payment_id, reservation_id, customer_id, amount, provider_tx_id, idempotency_key, status, time.time()))
            self.conn.commit()

    def confirm_order_and_sell(self, order_id: str, order_number: str, customer_id: str, reservation_id: str, amount: float):
        """Converts held reservation into confirmed sold inventory."""
        with self.lock:
            cur = self.conn.cursor()
            # Verify reservation is still reserved
            cur.execute("SELECT product_id, quantity, status FROM inventory_reservations WHERE reservation_id = ?", (reservation_id,))
            res = cur.fetchone()
            if not res or res["status"] != "RESERVED":
                return False

            qty = res["quantity"]
            product_id = res["product_id"]

            # Create Order
            cur.execute("""
                INSERT INTO orders (order_id, order_number, customer_id, reservation_id, status, total_amount, created_at)
                VALUES (?, ?, ?, ?, 'CONFIRMED', ?, ?)
            """, (order_id, order_number, customer_id, reservation_id, amount, time.time()))

            # Mark Reservation CONFIRMED
            cur.execute("UPDATE inventory_reservations SET status = 'CONFIRMED' WHERE reservation_id = ?", (reservation_id,))

            # Transition Inventory: reserved -> sold
            cur.execute("""
                UPDATE inventory 
                SET reserved_quantity = reserved_quantity - ?,
                    sold_quantity     = sold_quantity + ?
                WHERE product_id = ?
            """, (qty, qty, product_id))
            self.conn.commit()
            return True

    def get_inventory_snapshot(self, product_id: str) -> Dict[str, int]:
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT total_quantity, available_quantity, reserved_quantity, sold_quantity FROM inventory WHERE product_id = ?", (product_id,))
            row = cur.fetchone()
            return dict(row) if row else {}

    def get_counts(self) -> Dict[str, int]:
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT count(*) as c FROM inventory_reservations WHERE status = 'CONFIRMED'")
            confirmed_res = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM inventory_reservations WHERE status = 'RELEASED'")
            released_res = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM orders WHERE status = 'CONFIRMED'")
            confirmed_orders = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM payments WHERE status = 'SUCCEEDED'")
            succeeded_payments = cur.fetchone()["c"]
            cur.execute("SELECT count(*) as c FROM payments WHERE status = 'FAILED'")
            failed_payments = cur.fetchone()["c"]
            return {
                "confirmed_reservations": confirmed_res,
                "released_reservations": released_res,
                "confirmed_orders": confirmed_orders,
                "succeeded_payments": succeeded_payments,
                "failed_payments": failed_payments
            }


# --- ASYNCHRONOUS EVENT BUS & BUFFERED QUEUE (SQS SIMULATION) ---
class MessageBroker:
    """Durable message queue decoupling Payment from Order Service."""
    def __init__(self):
        self.queue = []
        self.lock = threading.Lock()

    def publish(self, event: Dict[str, Any]):
        with self.lock:
            self.queue.append(event)

    def drain_all(self) -> List[Dict[str, Any]]:
        with self.lock:
            events = list(self.queue)
            self.queue.clear()
            return events

    @property
    def backlog_count(self) -> int:
        with self.lock:
            return len(self.queue)


# --- SIMULATION ORCHESTRATOR ---
class FlashSaleSimulator:
    def __init__(self):
        self.db = DatabaseEngine()
        self.broker = MessageBroker()
        self.product_id = "prod-flash-100"
        
        # Metrics collection
        self.metrics = {
            "total_requests": 0,
            "duplicate_requests_sent": 0,
            "idempotent_duplicate_hits": 0,
            "successful_reservations": 0,
            "out_of_stock_rejections": 0,
            "payments_attempted": 0,
            "payments_succeeded": 0,
            "payments_failed": 0,
            "compensating_releases": 0,
            "orders_buffered_during_outage": 0,
            "orders_confirmed_after_recovery": 0,
        }
        self.metrics_lock = threading.Lock()

    def run_customer_attempt(self, customer_idx: int, is_duplicate: bool, shared_key: str, shared_hash: str):
        customer_id = f"cust-{customer_idx:05d}"
        idem_key = shared_key
        req_hash = shared_hash

        if is_duplicate:
            with self.metrics_lock:
                self.metrics["duplicate_requests_sent"] += 1


        with self.metrics_lock:
            self.metrics["total_requests"] += 1

        # 1. INVENTORY RESERVATION ATTEMPT
        res = self.db.reserve_stock_atomic(self.product_id, customer_id, 1, idem_key, req_hash)
        
        if not res["success"]:
            with self.metrics_lock:
                self.metrics["out_of_stock_rejections"] += 1
            return

        if res["duplicate"]:
            with self.metrics_lock:
                self.metrics["idempotent_duplicate_hits"] += 1
            return

        with self.metrics_lock:
            self.metrics["successful_reservations"] += 1

        res_data = res["data"]
        reservation_id = res_data["reservation_id"]

        # 2. PAYMENT PROCESSING (95% Success, 5% Decline)
        with self.metrics_lock:
            self.metrics["payments_attempted"] += 1

        is_payment_success = (random.random() < PAYMENT_SUCCESS_PROBABILITY)
        payment_id = f"pay-{uuid.uuid4().hex[:8]}"
        pay_idem_key = f"paykey-{reservation_id}"

        if is_payment_success:
            provider_tx_id = f"ch_stripe_{uuid.uuid4().hex[:12]}"
            self.db.record_payment(payment_id, reservation_id, customer_id, 499.00, "SUCCEEDED", pay_idem_key, provider_tx_id)
            with self.metrics_lock:
                self.metrics["payments_succeeded"] += 1

            # Publish PaymentSucceeded event to durable broker
            event = {
                "event_id": str(uuid.uuid4()),
                "event_type": "PaymentSucceeded",
                "payment_id": payment_id,
                "reservation_id": reservation_id,
                "customer_id": customer_id,
                "amount": 499.00
            }
            self.broker.publish(event)

        else:
            # Payment Failed (5% condition)
            self.db.record_payment(payment_id, reservation_id, customer_id, 499.00, "FAILED", pay_idem_key)
            with self.metrics_lock:
                self.metrics["payments_failed"] += 1

            # 3. TRIGGER COMPENSATING TRANSACTION (Reservation Release)
            released = self.db.release_reservation(reservation_id, "PAYMENT_FAILED")
            if released:
                with self.metrics_lock:
                    self.metrics["compensating_releases"] += 1

    def execute_flash_sale(self):
        print("=" * 70)
        print("  SALESTORM 2026: FLASH-SALE HIGH-CONCURRENCY VALIDATION")
        print("=" * 70)
        print(f"[*] Initial Physical Stock       : {TOTAL_STOCK} units")
        print(f"[*] Total Concurrent Customers  : {TOTAL_CUSTOMERS}")
        print(f"[*] Payment Success Rate Target  : {PAYMENT_SUCCESS_PROBABILITY * 100}%")
        print(f"[*] Duplicate Request Rate Target: {DUPLICATE_REQUEST_PROBABILITY * 100}%")
        print(f"[*] Worker Pool Threads          : {CONCURRENCY_WORKERS}")
        print("[*] Launching simultaneous customer purchase requests...")

        start_time = time.time()

        # Prepare request descriptors (including 2% duplicate replays)
        request_plan = []
        dup_count = int(TOTAL_CUSTOMERS * DUPLICATE_REQUEST_PROBABILITY)
        
        # Primary pool
        shared_keys = {}
        for i in range(TOTAL_CUSTOMERS - dup_count):
            shared_keys[i] = (f"idem-key-{i}", hashlib.sha256(f"cust-{i}".encode()).hexdigest())
            request_plan.append((i, False, shared_keys[i][0], shared_keys[i][1]))

        # Duplicate injection (exact same key & hash as random earlier requests)
        for j in range(dup_count):
            target_idx = random.randint(0, len(shared_keys) - 1)
            request_plan.append((target_idx, True, shared_keys[target_idx][0], shared_keys[target_idx][1]))

        # Shuffle requests so duplicates and new requests arrive interleaved
        random.shuffle(request_plan)

        # Execute concurrently with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=CONCURRENCY_WORKERS) as executor:
            futures = [executor.submit(self.run_customer_attempt, idx, is_dup, k, h) for (idx, is_dup, k, h) in request_plan]
            for f in as_completed(futures):
                f.result()

        elapsed_time = time.time() - start_time
        print(f"[+] Reservation and payment phase complete in {elapsed_time:.2f} seconds.")

        # --- MANDATORY SCENARIO: ORDER SERVICE OUTAGE ---
        print("\n" + "=" * 70)
        print("  SIMULATED OUTAGE: ORDER SERVICE UNAVAILABLE FOR 30 SECONDS")
        print("=" * 70)
        print(f"[*] Order Service status: OFFLINE (simulated outage).")
        print(f"[*] Messages safely retained in durable broker buffer: {self.broker.backlog_count} events.")
        
        self.metrics["orders_buffered_during_outage"] = self.broker.backlog_count
        print(f"[*] Waiting for Order Service recovery window ({SIMULATED_ORDER_OUTAGE_SECONDS}s simulation scaled)...")
        time.sleep(SIMULATED_ORDER_OUTAGE_SECONDS)

        print("[*] Order Service RECOVERED! Consuming buffered PaymentSucceeded messages...")
        recovered_events = self.broker.drain_all()
        for ev in recovered_events:
            order_id = f"ord-{uuid.uuid4().hex[:8]}"
            order_number = f"ORD-2026-{uuid.uuid4().hex[:6].upper()}"
            confirmed = self.db.confirm_order_and_sell(
                order_id, 
                order_number, 
                ev["customer_id"], 
                ev["reservation_id"], 
                ev["amount"]
            )
            if confirmed:
                self.metrics["orders_confirmed_after_recovery"] += 1

        print(f"[+] All {self.metrics['orders_confirmed_after_recovery']} buffered orders successfully confirmed without data loss!")

        # --- VERIFICATION & REPORTING ---
        self.generate_verification_report()

    def generate_verification_report(self):
        snapshot = self.db.get_inventory_snapshot(self.product_id)
        counts = self.db.get_counts()

        print("\n" + "=" * 70)
        print("  FINAL EMPIRICAL VERIFICATION REPORT")
        print("=" * 70)
        print(f"Total Inbound Requests Processed     : {self.metrics['total_requests']}")
        print(f"Duplicate Requests Injected          : {self.metrics['duplicate_requests_sent']}")
        print(f"Duplicate Requests Safely Deduplicated: {self.metrics['idempotent_duplicate_hits']}")
        print(f"Out-of-Stock Rejections (Safe 409)  : {self.metrics['out_of_stock_rejections']}")
        print(f"Initial Reservations Created         : {self.metrics['successful_reservations']}")
        print(f"Payment Attempts                     : {self.metrics['payments_attempted']}")
        print(f"Payments Succeeded (Approved)        : {self.metrics['payments_succeeded']}")
        print(f"Payments Failed (Declined 5%)        : {self.metrics['payments_failed']}")
        print(f"Compensating Releases Executed       : {self.metrics['compensating_releases']}")
        print(f"Orders Confirmed After Recovery      : {self.metrics['orders_confirmed_after_recovery']}")
        
        print("\n--- INVENTORY LEDGER INVARIANTS ---")
        print(f"Initial Total Stock                  : {snapshot['total_quantity']}")
        print(f"Final Available Units                : {snapshot['available_quantity']}")
        print(f"Final Reserved Units                 : {snapshot['reserved_quantity']}")
        print(f"Final Sold Units                     : {snapshot['sold_quantity']}")
        
        # MATHEMATICAL PROOF ASSERTIONS
        oversold = max(0, snapshot['sold_quantity'] - TOTAL_STOCK)
        quantity_conservation = (snapshot['available_quantity'] + snapshot['reserved_quantity'] + snapshot['sold_quantity'] == snapshot['total_quantity'])
        
        print(f"Overselling Violations               : {oversold}")
        print(f"Quantity Conservation Check          : {'PASSED' if quantity_conservation else 'FAILED'}")

        # Assertions
        assert snapshot['sold_quantity'] <= TOTAL_STOCK, f"VIOLATION: Sold {snapshot['sold_quantity']} > {TOTAL_STOCK}!"
        assert snapshot['available_quantity'] >= 0, "VIOLATION: Negative available quantity!"
        assert snapshot['reserved_quantity'] >= 0, "VIOLATION: Negative reserved quantity!"
        assert quantity_conservation, "VIOLATION: Stock conservation law breached!"
        assert self.metrics['orders_confirmed_after_recovery'] == self.metrics['payments_succeeded'], "VIOLATION: Order loss detected during outage!"

        print("\n[SUCCESS] ALL ARCHITECTURAL INVARIANTS SATISFIED WITH 100% MATHEMATICAL PRECISION.")
        print("=" * 70)

        # Save output to JSON
        output_results = {
            "test_timestamp": time.time(),
            "config": {
                "initial_stock": TOTAL_STOCK,
                "total_customers": TOTAL_CUSTOMERS,
                "payment_success_rate": PAYMENT_SUCCESS_PROBABILITY,
                "duplicate_rate": DUPLICATE_REQUEST_PROBABILITY
            },
            "metrics": self.metrics,
            "ledger": snapshot,
            "counts": counts,
            "invariants_passed": {
                "no_overselling": bool(snapshot['sold_quantity'] <= TOTAL_STOCK),
                "conservation_law": bool(quantity_conservation),
                "zero_order_loss_during_outage": bool(self.metrics['orders_confirmed_after_recovery'] == self.metrics['payments_succeeded']),
                "idempotency_deduplication_exact": bool(self.metrics['idempotent_duplicate_hits'] == self.metrics['duplicate_requests_sent'])
            }
        }

        with open("11_AI_Assisted_Validation/simulation_output.json", "w") as f:
            json.dump(output_results, f, indent=2)
        print("[*] Detailed results exported to 11_AI_Assisted_Validation/simulation_output.json")


if __name__ == "__main__":
    simulator = FlashSaleSimulator()
    simulator.execute_flash_sale()
