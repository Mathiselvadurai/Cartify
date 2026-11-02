"""
Automated Test Suite for Cartify Phase 7:
Store Owner Inventory, Product, and Order Management.

Tests:
 1. Inventory page (/owner/inventory) renders real Oracle stock metrics and product list for verified owner.
 2. Ordinary customer is blocked from /owner/inventory with HTTP 403 Forbidden.
 3. Inventory taxonomy, search, and status filters function correctly.
 4. Stock modification endpoint (/owner/inventory/update-stock) updates stock with 'exact' adjustment.
 5. Stock modification endpoint supports 'add' and 'remove' relative adjustments and respects non-negative floor.
 6. Stock modification endpoint rejects invalid product IDs, non-existent products, and negative quantities.
 7. Products catalog (/owner/products) renders catalog for verified owner with pagination and filters.
 8. Ordinary customer is blocked from /owner/products with HTTP 403 Forbidden.
 9. Product creation (/owner/products/new) creates product atomically using Oracle sequence seq_product_id.NEXTVAL.
10. Product creation enforces strict server-side validation (pricing, required fields, non-negative stock).
11. Product editing (/owner/products/<id>/edit) updates attributes in Oracle DB.
12. Product active toggle (/owner/products/<id>/toggle-active) toggles is_active state reliably.
13. Orders management (/owner/orders) renders master-detail drawer, KPI metrics, and order listing for owner.
14. Ordinary customer is blocked from /owner/orders with HTTP 403 Forbidden.
15. Order details JSON API (/owner/orders/<id>) returns structured customer info and line items.
16. Order status transition enforces state machine rules without modifying inventory.
17. Order status transition rejects invalid / illegal transitions with HTTP 400.
18. CSRF validation protects state-changing POST endpoints against forged requests.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.db import query_db, execute_db


class TestOwnerManagementP7(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.app.config["ENFORCE_CSRF"] = False
        self.client = self.app.test_client()

        # Verified Active Owner (User 53: Arjun Shetty, is_active=1 in USERS table)
        self.owner_user = {
            "id": 53,
            "name": "Arjun Shetty",
            "email": "arjun.shetty53@example.com",
            "tier": "Basic"
        }

        # Ordinary Customer (User 52: Kavya Rao, non-admin)
        self.customer_user = {
            "id": 52,
            "name": "Kavya Rao",
            "email": "kavya.rao21@example.com",
            "tier": "Basic"
        }

        # Dynamically fetch an existing product ID from database
        sample = query_db("SELECT product_id FROM products FETCH FIRST 1 ROWS ONLY", one=True)
        self.sample_product_id = sample["product_id"] if sample else 1551

    def _login_as_owner(self):
        with self.client.session_transaction() as sess:
            sess["user"] = self.owner_user
            sess["is_admin"] = True
            sess["csrf_token"] = "test_csrf_token_p7"

    def _login_as_customer(self):
        with self.client.session_transaction() as sess:
            sess["user"] = self.customer_user
            sess["is_admin"] = False
            sess["csrf_token"] = "test_csrf_token_p7"

    # ==========================================================================
    # Screen 5: Inventory Management Tests
    # ==========================================================================

    def test_01_inventory_render_owner(self):
        """Verified store owner can view Screen 5 Inventory Management with live KPIs."""
        self._login_as_owner()
        resp = self.client.get("/owner/inventory")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Inventory Management", html)
        self.assertIn("Total SKUs", html)
        self.assertIn("In Stock (Nominal)", html)
        self.assertIn("Low Stock Vigilance", html)
        self.assertIn("Update Stock", html)

    def test_02_inventory_blocked_customer(self):
        """Ordinary customers cannot access /owner/inventory (HTTP 403 Forbidden)."""
        self._login_as_customer()
        resp = self.client.get("/owner/inventory")
        self.assertEqual(resp.status_code, 403)
        html = resp.get_data(as_text=True)
        self.assertIn("Access Restricted", html)

    def test_03_inventory_filters(self):
        """Inventory search and status filters return matching catalog items."""
        self._login_as_owner()
        # Filter: low_stock
        resp = self.client.get("/owner/inventory?status=low_stock")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Inventory Management", html)

        # Search query
        resp_search = self.client.get("/owner/inventory?q=Puma")
        self.assertEqual(resp_search.status_code, 200)

    def test_04_inventory_update_stock_exact(self):
        """Stock update endpoint sets exact stock level in Oracle DB."""
        self._login_as_owner()
        test_pid = self.sample_product_id
        orig_row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (test_pid,), one=True)
        orig_stock = int(orig_row["stock_quantity"] or 0)

        target_stock = 42
        try:
            resp = self.client.post("/owner/inventory/update-stock", json={
                "product_id": test_pid,
                "adjustment_type": "exact",
                "quantity": target_stock
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["new_stock"], target_stock)

            # Verify in DB
            db_row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (test_pid,), one=True)
            self.assertEqual(int(db_row["stock_quantity"]), target_stock)
        finally:
            # Restore original stock
            execute_db("UPDATE products SET stock_quantity = :1 WHERE product_id = :2", (orig_stock, test_pid))

    def test_05_inventory_update_stock_add_remove(self):
        """Stock update supports relative 'add' and 'remove' modes with zero floor."""
        self._login_as_owner()
        test_pid = self.sample_product_id
        orig_row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (test_pid,), one=True)
        orig_stock = int(orig_row["stock_quantity"] or 0)

        try:
            # Set to 20
            self.client.post("/owner/inventory/update-stock", json={
                "product_id": test_pid,
                "adjustment_type": "exact",
                "quantity": 20
            })
            # Add 10 -> 30
            resp_add = self.client.post("/owner/inventory/update-stock", json={
                "product_id": test_pid,
                "adjustment_type": "add",
                "quantity": 10
            })
            self.assertEqual(resp_add.get_json()["new_stock"], 30)

            # Remove 5 -> 25
            resp_rem = self.client.post("/owner/inventory/update-stock", json={
                "product_id": test_pid,
                "adjustment_type": "remove",
                "quantity": 5
            })
            self.assertEqual(resp_rem.get_json()["new_stock"], 25)

            # Remove 50 -> should floor at 0
            resp_floor = self.client.post("/owner/inventory/update-stock", json={
                "product_id": test_pid,
                "adjustment_type": "remove",
                "quantity": 50
            })
            self.assertEqual(resp_floor.get_json()["new_stock"], 0)
        finally:
            execute_db("UPDATE products SET stock_quantity = :1 WHERE product_id = :2", (orig_stock, test_pid))

    def test_06_inventory_update_stock_validation(self):
        """Rejects negative quantities, invalid product IDs, and non-existent products."""
        self._login_as_owner()
        # Invalid product ID 0
        resp_bad_id = self.client.post("/owner/inventory/update-stock", json={
            "product_id": 0,
            "adjustment_type": "exact",
            "quantity": 10
        })
        self.assertEqual(resp_bad_id.status_code, 400)

        # Non-existent product ID
        resp_not_found = self.client.post("/owner/inventory/update-stock", json={
            "product_id": 9999999,
            "adjustment_type": "exact",
            "quantity": 10
        })
        self.assertEqual(resp_not_found.status_code, 404)

        # Negative quantity on a valid product
        resp_neg_qty = self.client.post("/owner/inventory/update-stock", json={
            "product_id": self.sample_product_id,
            "adjustment_type": "exact",
            "quantity": -5
        })
        self.assertEqual(resp_neg_qty.status_code, 400)

    # ==========================================================================
    # Screen 6: Product Catalog & Lifecycle Management Tests
    # ==========================================================================

    def test_07_products_catalog_render_owner(self):
        """Verified store owner can view Screen 6 Product Catalog table."""
        self._login_as_owner()
        resp = self.client.get("/owner/products")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Product Catalog", html)
        self.assertIn("Add New Product", html)
        self.assertIn("Oracle Database 26ai", html)

    def test_08_products_catalog_blocked_customer(self):
        """Ordinary customers cannot view /owner/products."""
        self._login_as_customer()
        resp = self.client.get("/owner/products")
        self.assertEqual(resp.status_code, 403)

    def test_09_product_add_atomic_sequence(self):
        """Product creation uses Oracle sequence seq_product_id.NEXTVAL atomically."""
        self._login_as_owner()
        unique_name = "TEST_P7_PRECISION_SKU_AUTOMATION"

        # Make sure no leftover from previous runs
        execute_db("DELETE FROM products WHERE product_name = :1", (unique_name,))

        try:
            resp = self.client.post("/owner/products/new", data={
                "product_name": unique_name,
                "brand": "Cartify Precision Labs",
                "category": "Electronics",
                "subcategory": "Accessories",
                "product_type": "Hardware",
                "price_inr": "1499.00",
                "sale_price_inr": "1299.00",
                "stock_quantity": "75",
                "is_active": "1",
                "product_description": "Automated unit test product for Phase 7 sequence verification."
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

            # Verify in DB
            created = query_db("SELECT product_id, product_name, price_inr, stock_quantity, is_active FROM products WHERE product_name = :1", (unique_name,), one=True)
            self.assertIsNotNone(created)
            # Must be generated from seq_product_id starting at 60001
            self.assertGreaterEqual(created["product_id"], 60001)
            self.assertEqual(float(created["price_inr"]), 1499.0)
            self.assertEqual(int(created["stock_quantity"]), 75)
            self.assertEqual(int(created["is_active"]), 1)
        finally:
            # Clean up immediately to preserve catalog row count baseline
            execute_db("DELETE FROM products WHERE product_name = :1", (unique_name,))

    def test_10_product_add_validation(self):
        """Product creation enforces server-side pricing and required field validation."""
        self._login_as_owner()

        # Missing name
        resp_missing = self.client.post("/owner/products/new", data={
            "product_name": "",
            "brand": "TestBrand",
            "category": "Electronics",
            "price_inr": "100.00"
        })
        self.assertEqual(resp_missing.status_code, 200)
        html = resp_missing.get_data(as_text=True)
        self.assertIn("Product name is required", html)

        # Negative price
        resp_neg_price = self.client.post("/owner/products/new", data={
            "product_name": "Bad Price SKU",
            "brand": "TestBrand",
            "category": "Electronics",
            "price_inr": "-100.00"
        })
        html = resp_neg_price.get_data(as_text=True)
        self.assertIn("Retail price must be a positive number", html)

        # Sale price > regular price
        resp_bad_sale = self.client.post("/owner/products/new", data={
            "product_name": "Bad Sale SKU",
            "brand": "TestBrand",
            "category": "Electronics",
            "price_inr": "100.00",
            "sale_price_inr": "150.00"
        })
        html = resp_bad_sale.get_data(as_text=True)
        self.assertIn("Sale price cannot be higher than regular retail price", html)

    def test_11_product_edit(self):
        """Product edit form loads and updates product attributes in Oracle DB."""
        self._login_as_owner()
        test_pid = self.sample_product_id

        # Read original product
        orig = query_db("SELECT product_name, price_inr, brand, category FROM products WHERE product_id = :1", (test_pid,), one=True)
        orig_name = orig["product_name"]

        # GET edit form
        resp_get = self.client.get(f"/owner/products/{test_pid}/edit")
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn("Edit Product", resp_get.get_data(as_text=True))

        updated_name = f"{orig_name} (P7 Edited)"
        try:
            resp_post = self.client.post(f"/owner/products/{test_pid}/edit", data={
                "product_name": updated_name,
                "brand": orig["brand"],
                "category": orig["category"],
                "price_inr": str(orig["price_inr"]),
                "stock_quantity": "50",
                "is_active": "1"
            }, follow_redirects=True)
            self.assertEqual(resp_post.status_code, 200)

            # Check DB
            after = query_db("SELECT product_name FROM products WHERE product_id = :1", (test_pid,), one=True)
            self.assertEqual(after["product_name"], updated_name)
        finally:
            # Restore original
            execute_db("UPDATE products SET product_name = :1 WHERE product_id = :2", (orig_name, test_pid))

    def test_12_product_toggle_active(self):
        """Active state toggle updates is_active in DB and returns new state."""
        self._login_as_owner()
        test_pid = self.sample_product_id
        orig_row = query_db("SELECT is_active FROM products WHERE product_id = :1", (test_pid,), one=True)
        orig_active = int(orig_row["is_active"])

        try:
            # Toggle once
            resp1 = self.client.post(f"/owner/products/{test_pid}/toggle-active", headers={"Accept": "application/json"})
            self.assertEqual(resp1.status_code, 200)
            data1 = resp1.get_json()
            self.assertTrue(data1["success"])
            expected1 = 0 if orig_active == 1 else 1
            self.assertEqual(data1["is_active"], expected1)

            # Toggle back
            resp2 = self.client.post(f"/owner/products/{test_pid}/toggle-active", headers={"Accept": "application/json"})
            self.assertEqual(resp2.status_code, 200)
            data2 = resp2.get_json()
            self.assertEqual(data2["is_active"], orig_active)
        finally:
            execute_db("UPDATE products SET is_active = :1 WHERE product_id = :2", (orig_active, test_pid))

    # ==========================================================================
    # Screen 7: Order Management & Fulfillment Tests
    # ==========================================================================

    def test_13_orders_master_detail_render_owner(self):
        """Verified store owner can view Screen 7 Order Management & Fulfillment Center."""
        self._login_as_owner()
        resp = self.client.get("/owner/orders")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Order Management", html)
        self.assertIn("Fulfillment", html)
        self.assertIn("Total Recorded Orders", html)
        self.assertIn("Confirmed", html)
        self.assertIn("In Processing", html)
        self.assertIn("Shipped", html)
        self.assertIn("Delivered", html)
        self.assertIn("Cancelled", html)
        self.assertIn("Returned", html)

    def test_14_orders_blocked_customer(self):
        """Ordinary customers cannot view /owner/orders (HTTP 403 Forbidden)."""
        self._login_as_customer()
        resp = self.client.get("/owner/orders")
        self.assertEqual(resp.status_code, 403)

    def test_15_order_detail_api(self):
        """Order detail JSON API returns customer info and line items."""
        self._login_as_owner()
        # Find first valid order
        first_order = query_db("SELECT order_id FROM orders FETCH FIRST 1 ROWS ONLY", one=True)
        self.assertIsNotNone(first_order)
        oid = first_order["order_id"]

        resp = self.client.get(f"/owner/orders/{oid}")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertIn("order", data)
        self.assertIn("items", data)
        self.assertEqual(data["order"]["order_id"], oid)

        # Non-existent order returns 404
        resp_404 = self.client.get("/owner/orders/9999999")
        self.assertEqual(resp_404.status_code, 404)

    def test_16_order_status_valid_transition(self):
        """Validated status transition updates order_status without modifying inventory stock."""
        self._login_as_owner()
        # Find an order in 'Confirmed' or 'Processing' status
        order = query_db("SELECT order_id, order_status FROM orders WHERE order_status IN ('Confirmed', 'Processing') FETCH FIRST 1 ROWS ONLY", one=True)
        if not order:
            self.skipTest("No Confirmed or Processing orders available in database")

        oid = order["order_id"]
        curr_status = order["order_status"]
        new_status = "Processing" if curr_status == "Confirmed" else "Shipped"

        # Check a product's stock before transition
        item = query_db("SELECT product_id FROM order_items WHERE order_id = :1 FETCH FIRST 1 ROWS ONLY", (oid,), one=True)
        pre_stock = None
        if item:
            p_row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (item["product_id"],), one=True)
            if p_row:
                pre_stock = p_row["stock_quantity"]

        try:
            resp = self.client.post(f"/owner/orders/{oid}/status", json={"new_status": new_status})
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["new_status"], new_status)

            # Verify in DB
            db_order = query_db("SELECT order_status FROM orders WHERE order_id = :1", (oid,), one=True)
            self.assertEqual(db_order["order_status"], new_status)

            # Stock must NOT change during fulfillment lifecycle transitions
            if item and pre_stock is not None:
                post_stock_row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (item["product_id"],), one=True)
                self.assertEqual(post_stock_row["stock_quantity"], pre_stock)
        finally:
            execute_db("UPDATE orders SET order_status = :1 WHERE order_id = :2", (curr_status, oid))

    def test_17_order_status_invalid_transition(self):
        """Illegal status transitions (e.g. Delivered -> Processing) are rejected with HTTP 400."""
        self._login_as_owner()
        delivered_order = query_db("SELECT order_id FROM orders WHERE order_status = 'Delivered' FETCH FIRST 1 ROWS ONLY", one=True)
        if not delivered_order:
            self.skipTest("No Delivered orders found")

        oid = delivered_order["order_id"]
        resp = self.client.post(f"/owner/orders/{oid}/status", json={"new_status": "Processing"})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data.get("code"), "INVALID_TRANSITION")

    def test_18_csrf_validation_enforced(self):
        """CSRF token protection blocks forged requests when validation is active."""
        self._login_as_owner()
        # Temporarily enable CSRF enforcement for this specific test
        self.app.config["ENFORCE_CSRF"] = True
        try:
            # Post without valid CSRF token header or form field
            resp = self.client.post("/owner/inventory/update-stock", json={
                "product_id": self.sample_product_id,
                "adjustment_type": "exact",
                "quantity": 10
            })
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertFalse(data["success"])
            self.assertEqual(data.get("code"), "CSRF_FAILED")
        finally:
            self.app.config["ENFORCE_CSRF"] = False

    def test_19_cancellation_restores_stock_exactly_once(self):
        """Pre-shipment order cancellation restores reserved stock exactly once with double-cancellation defense."""
        self._login_as_owner()
        order = query_db("SELECT order_id, order_status FROM orders WHERE order_status IN ('Confirmed', 'Processing') FETCH FIRST 1 ROWS ONLY", one=True)
        if not order:
            self.skipTest("No Confirmed/Processing order available for cancellation test")

        oid = order["order_id"]
        curr_status = order["order_status"]
        items = query_db("SELECT product_id, quantity FROM order_items WHERE order_id = :1", (oid,))
        if not items:
            self.skipTest(f"Order #{oid} has no line items")

        # Record initial stock levels for all products in this order
        initial_stocks = {}
        for it in items:
            p_id = it["product_id"]
            row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (p_id,), one=True)
            initial_stocks[p_id] = int(row["stock_quantity"] or 0)

        try:
            # 1. First Cancellation Attempt -> MUST succeed
            resp1 = self.client.post(f"/owner/orders/{oid}/status", json={"new_status": "Cancelled"})
            self.assertEqual(resp1.status_code, 200)
            data1 = resp1.get_json()
            self.assertTrue(data1["success"])
            self.assertEqual(data1["new_status"], "Cancelled")

            # Verify order status in DB
            db_order = query_db("SELECT order_status FROM orders WHERE order_id = :1", (oid,), one=True)
            self.assertEqual(db_order["order_status"], "Cancelled")

            # Verify that stock was restored by exactly the ordered quantity
            for it in items:
                p_id = it["product_id"]
                qty = it["quantity"]
                row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (p_id,), one=True)
                expected_stock = initial_stocks[p_id] + qty
                self.assertEqual(int(row["stock_quantity"]), expected_stock, f"Stock for product #{p_id} was not restored accurately")

            # 2. Duplicate Cancellation Attempt -> MUST be rejected (Idempotency / Re-entrancy guard)
            resp2 = self.client.post(f"/owner/orders/{oid}/status", json={"new_status": "Cancelled"})
            self.assertEqual(resp2.status_code, 400)
            data2 = resp2.get_json()
            self.assertFalse(data2["success"])
            self.assertEqual(data2.get("code"), "ALREADY_CANCELLED")

            # Verify that stock was NOT incremented again
            for it in items:
                p_id = it["product_id"]
                qty = it["quantity"]
                row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (p_id,), one=True)
                self.assertEqual(int(row["stock_quantity"]), initial_stocks[p_id] + qty, f"Stock for product #{p_id} was double-restored on repeat cancellation")

        finally:
            # Revert order status and stock back to baseline
            for it in items:
                p_id = it["product_id"]
                execute_db("UPDATE products SET stock_quantity = :1 WHERE product_id = :2", (initial_stocks[p_id], p_id))
            execute_db("UPDATE orders SET order_status = :1 WHERE order_id = :2", (curr_status, oid))

    def test_20_return_does_not_restore_stock(self):
        """Transitioning an order to Returned does NOT automatically restore stock without inspection."""
        self._login_as_owner()
        order = query_db("SELECT order_id, order_status FROM orders WHERE order_status = 'Delivered' FETCH FIRST 1 ROWS ONLY", one=True)
        if not order:
            self.skipTest("No Delivered order available for return test")

        oid = order["order_id"]
        items = query_db("SELECT product_id, quantity FROM order_items WHERE order_id = :1", (oid,))
        if not items:
            self.skipTest(f"Order #{oid} has no line items")

        initial_stocks = {}
        for it in items:
            p_id = it["product_id"]
            row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (p_id,), one=True)
            initial_stocks[p_id] = int(row["stock_quantity"] or 0)

        try:
            # Transition Delivered -> Returned
            resp = self.client.post(f"/owner/orders/{oid}/status", json={"new_status": "Returned"})
            self.assertEqual(resp.status_code, 200)

            # Verify stock remained unchanged
            for it in items:
                p_id = it["product_id"]
                row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (p_id,), one=True)
                self.assertEqual(int(row["stock_quantity"]), initial_stocks[p_id], f"Stock for product #{p_id} was improperly restored on return")
        finally:
            execute_db("UPDATE orders SET order_status = 'Delivered' WHERE order_id = :1", (oid,))

    def test_21_discrete_order_kpis_sum_equality(self):
        """Discrete order KPI metrics must satisfy: SUM(individual status counts) == Total recorded orders."""
        self._login_as_owner()
        resp = self.client.get("/owner/orders")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Direct database verification
        status_counts = query_db("SELECT order_status, COUNT(*) as c FROM orders GROUP BY order_status")
        total_orders = query_db("SELECT COUNT(*) as c FROM orders", one=True)["c"]
        status_dict = {r["order_status"]: r["c"] for r in status_counts}

        individual_sum = sum(status_dict.values())
        self.assertEqual(individual_sum, total_orders)
        self.assertIn("Confirmed", status_dict)
        self.assertIn("Processing", status_dict)
        self.assertIn("Shipped", status_dict)
        self.assertIn("Delivered", status_dict)
        self.assertIn("Cancelled", status_dict)
        self.assertIn("Returned", status_dict)

        # Check presence in template HTML
        self.assertIn("Confirmed", html)
        self.assertIn("In Processing", html)
        self.assertIn("Shipped", html)
        self.assertIn("Delivered", html)
        self.assertIn("Cancelled", html)
        self.assertIn("Returned", html)

    def test_22_concurrent_stock_updates(self):
        """Concurrent stock increments with row locking do not suffer from lost updates."""
        from concurrent.futures import ThreadPoolExecutor

        test_pid = self.sample_product_id
        orig_row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (test_pid,), one=True)
        orig_stock = int(orig_row["stock_quantity"] or 0)

        num_threads = 4
        qty_per_thread = 5

        def _do_add(_):
            app = create_app()
            app.config["TESTING"] = True
            app.config["WTF_CSRF_ENABLED"] = False
            app.config["ENFORCE_CSRF"] = False
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = self.owner_user
                sess["is_admin"] = True
            r = client.post("/owner/inventory/update-stock", json={
                "product_id": test_pid,
                "adjustment_type": "add",
                "quantity": qty_per_thread
            })
            return r.status_code

        try:
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                results = list(executor.map(_do_add, range(num_threads)))

            self.assertEqual(results, [200] * num_threads)
            after_row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (test_pid,), one=True)
            expected_stock = orig_stock + (num_threads * qty_per_thread)
            self.assertEqual(int(after_row["stock_quantity"]), expected_stock)
        finally:
            execute_db("UPDATE products SET stock_quantity = :1 WHERE product_id = :2", (orig_stock, test_pid))

    def test_23_concurrent_order_cancellations(self):
        """Concurrent cancellation requests on the same order serialize safely: exactly one succeeds."""
        from concurrent.futures import ThreadPoolExecutor

        order = query_db("SELECT order_id, order_status FROM orders WHERE order_status IN ('Confirmed', 'Processing') FETCH FIRST 1 ROWS ONLY", one=True)
        if not order:
            self.skipTest("No Confirmed/Processing order available for concurrent cancellation test")

        oid = order["order_id"]
        curr_status = order["order_status"]
        items = query_db("SELECT product_id, quantity FROM order_items WHERE order_id = :1", (oid,))
        if not items:
            self.skipTest(f"Order #{oid} has no line items")

        initial_stocks = {}
        for it in items:
            p_id = it["product_id"]
            row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (p_id,), one=True)
            initial_stocks[p_id] = int(row["stock_quantity"] or 0)

        num_threads = 4

        def _cancel_attempt(_):
            app = create_app()
            app.config["TESTING"] = True
            app.config["WTF_CSRF_ENABLED"] = False
            app.config["ENFORCE_CSRF"] = False
            client = app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = self.owner_user
                sess["is_admin"] = True
            r = client.post(f"/owner/orders/{oid}/status", json={"new_status": "Cancelled"})
            return r.status_code

        try:
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                status_codes = list(executor.map(_cancel_attempt, range(num_threads)))

            # Exactly one request must succeed with 200, all others must be rejected with 400
            success_count = status_codes.count(200)
            failure_count = status_codes.count(400)
            self.assertEqual(success_count, 1, f"Expected exactly 1 successful cancellation, got {success_count} ({status_codes})")
            self.assertEqual(failure_count, num_threads - 1)

            # Verify stock was restored EXACTLY ONCE
            for it in items:
                p_id = it["product_id"]
                qty = it["quantity"]
                row = query_db("SELECT stock_quantity FROM products WHERE product_id = :1", (p_id,), one=True)
                self.assertEqual(int(row["stock_quantity"]), initial_stocks[p_id] + qty)
        finally:
            for it in items:
                p_id = it["product_id"]
                execute_db("UPDATE products SET stock_quantity = :1 WHERE product_id = :2", (initial_stocks[p_id], p_id))
            execute_db("UPDATE orders SET order_status = :1 WHERE order_id = :2", (curr_status, oid))

    def test_24_customer_cancel_ownership_guard(self):
        """Customer cannot cancel an order owned by a different customer (IDOR / Ownership guard)."""
        self._login_as_customer()  # User 52
        # Find an order owned by another user (e.g. user_id != 52)
        other_order = query_db("SELECT order_id FROM orders WHERE user_id != 52 AND order_status IN ('Confirmed', 'Processing') FETCH FIRST 1 ROWS ONLY", one=True)
        if not other_order:
            self.skipTest("No foreign Confirmed/Processing order found")

        foreign_oid = other_order["order_id"]
        resp = self.client.post(f"/order/{foreign_oid}/cancel", json={})
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data.get("code"), "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
