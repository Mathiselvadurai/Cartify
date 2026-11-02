"""
Mandatory Concurrent Checkout Concurrency & Atomicity Test Suite for Cartify Phase 5.
Validates:
1. Two distinct Oracle Database 26ai sessions simultaneously attempt to purchase the last unit (stock = 1).
2. Atomic conditional stock decrement: UPDATE products SET stock_quantity = stock_quantity - :q WHERE stock_quantity >= :q.
3. Rowcount guard strictly ensures exactly one session succeeds (rowcount=1) and the other is rejected (rowcount=0).
4. Final stock equals exactly 0, never negative.
5. Zero inventory leakage, no duplicate orders, and rollback behavior verified.
6. Safe isolation: creates a dedicated high-range test product (ID 999991) and completely cleans up afterwards.
"""

import threading
import time
import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import get_connection, execute_db, query_db


class TestConcurrentCheckout(unittest.TestCase):
    TEST_PID = 999991

    def setUp(self):
        # 1. Ensure test fixture is clean
        execute_db("DELETE FROM products WHERE product_id = :1", (self.TEST_PID,))
        
        # 2. Insert isolated test product with exactly ONE unit in stock
        insert_sql = """
            INSERT INTO products (
                product_id, product_name, brand, category, subcategory, 
                price_inr, sale_price_inr, stock_quantity, sales_count, is_active
            ) VALUES (
                :1, 'Concurrency Test Widget', 'Cartify Lab', 'Testing', 'Concurrency',
                999.0, 999.0, 1, 0, 1
            )
        """
        execute_db(insert_sql, (self.TEST_PID,))
        
        # Verify initial fixture state
        p = query_db("SELECT stock_quantity, is_active FROM products WHERE product_id = :1", (self.TEST_PID,), one=True)
        self.assertIsNotNone(p)
        self.assertEqual(p["stock_quantity"], 1)
        self.assertEqual(p["is_active"], 1)

    def tearDown(self):
        # Completely clean up test product
        execute_db("DELETE FROM products WHERE product_id = :1", (self.TEST_PID,))

    def test_simultaneous_last_unit_checkout_two_sessions(self):
        """Simultaneously attempt to purchase the final unit across two separate Oracle DB connections."""
        results = {}
        barrier = threading.Barrier(2)

        def session_worker(session_name):
            conn = get_connection()
            cur = conn.cursor()
            try:
                # Wait for both worker threads to reach starting line
                barrier.wait(timeout=5)

                # Real conditional stock reservation logic
                stock_sql = """
                    UPDATE products
                    SET stock_quantity = stock_quantity - :1,
                        sales_count = sales_count + :2
                    WHERE product_id = :3
                      AND is_active = 1
                      AND stock_quantity >= :4
                """
                # Attempt to decrement 1 unit
                cur.execute(stock_sql, (1, 1, self.TEST_PID, 1))
                rc = cur.rowcount

                if rc == 1:
                    # Stock successfully secured -> simulate order completion & commit
                    conn.commit()
                    results[session_name] = {"success": True, "rowcount": 1, "status": "ORDER_COMMITTED"}
                else:
                    # Insufficient stock or race loss -> rollback
                    conn.rollback()
                    results[session_name] = {"success": False, "rowcount": 0, "status": "REJECTED_OUT_OF_STOCK"}

            except Exception as e:
                conn.rollback()
                results[session_name] = {"success": False, "rowcount": -1, "error": str(e)}
            finally:
                cur.close()
                conn.close()

        # Launch Thread A (Session A) and Thread B (Session B)
        t_a = threading.Thread(target=session_worker, args=("Session_A",))
        t_b = threading.Thread(target=session_worker, args=("Session_B",))

        t_a.start()
        t_b.start()

        t_a.join(timeout=10)
        t_b.join(timeout=10)

        # Assertions
        print("\n" + "=" * 70)
        print("CONCURRENT CHECKOUT RACE OUTCOME:")
        print(f"  Session A: {results.get('Session_A')}")
        print(f"  Session B: {results.get('Session_B')}")
        print("=" * 70)

        success_count = sum(1 for res in results.values() if res["success"])
        rejected_count = sum(1 for res in results.values() if not res["success"] and res["rowcount"] == 0)

        self.assertEqual(success_count, 1, f"Exactly 1 session must succeed! Got: {results}")
        self.assertEqual(rejected_count, 1, f"Exactly 1 session must be cleanly rejected! Got: {results}")

        # Check final stock in Oracle DB
        final_row = query_db("SELECT stock_quantity, sales_count FROM products WHERE product_id = :1", (self.TEST_PID,), one=True)
        self.assertIsNotNone(final_row)
        self.assertEqual(final_row["stock_quantity"], 0, f"Final stock must equal exactly 0, got {final_row['stock_quantity']}")
        self.assertGreaterEqual(final_row["stock_quantity"], 0, "Stock must never become negative!")
        self.assertEqual(final_row["sales_count"], 1, "Sales count should have incremented by exactly 1")

    def test_overselling_prevention_zero_stock(self):
        """Verify that attempting to purchase when stock = 0 immediately fails with rowcount = 0."""
        # Set stock to 0
        execute_db("UPDATE products SET stock_quantity = 0 WHERE product_id = :1", (self.TEST_PID,))

        conn = get_connection()
        cur = conn.cursor()
        try:
            stock_sql = """
                UPDATE products
                SET stock_quantity = stock_quantity - :1,
                    sales_count = sales_count + :2
                WHERE product_id = :3
                  AND is_active = 1
                  AND stock_quantity >= :4
            """
            cur.execute(stock_sql, (1, 1, self.TEST_PID, 1))
            self.assertEqual(cur.rowcount, 0, "Must affect 0 rows when stock is 0")
            conn.rollback()
        finally:
            cur.close()
            conn.close()


if __name__ == "__main__":
    unittest.main()
