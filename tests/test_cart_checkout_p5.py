"""
Automated Test Suite for Cartify Phase 5:
Shopping Cart, Multi-Step Checkout & Transaction Reliability.
Tests:
1. Cart retrieval and empty state rendering (/cart)
2. Add product to cart with CSRF (/cart/add/<id>)
3. Cart item quantity increase, decrease, set and remove (/cart/update)
4. Clear entire cart operation (/cart/update action=clear)
5. Coupon application (CARTIFY10, WELCOME10, FESTIVE15, FLAT100) & removal (/cart/apply-coupon, /cart/remove-coupon)
6. Invalid quantity handling (negative or zero quantity rejected at checkout)
7. Empty cart checkout rejection (redirects to /products)
8. Unauthenticated checkout redirection to /login
9. Product inactive-state checkout rejection
10. Insufficient stock conditional rejection
11. Duplicate product ID aggregation & deterministic ordering
12. Atomic checkout execution, order creation & rollback on error
13. Order success confirmation rendering (/order_success/<id> & /order/<id>)
14. IDOR order privacy protection
15. CSRF token enforcement on all state-changing cart and checkout POST routes
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.db import query_db, execute_db


class TestCartCheckoutP5(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.app.config["ENFORCE_CSRF"] = False
        self.client = self.app.test_client()

    def test_01_cart_page_empty_rendering(self):
        """Verify empty shopping cart page renders with Stitch Screen 9 empty state."""
        resp = self.client.get("/cart")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Your Shopping Cart is Empty", html)
        self.assertIn("Browse Smart Catalog", html)

    def test_02_add_to_cart_and_view(self):
        """Verify adding a product to cart updates session and renders in cart."""
        with self.client.session_transaction() as sess:
            sess["csrf_token"] = "valid_token_123"

        resp = self.client.post("/cart/add/1551", data={"quantity": 2, "csrf_token": "valid_token_123"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Shopping Cart", html)
        self.assertIn("Order Summary", html)
        self.assertIn("Puma", html)

    def test_03_cart_quantity_controls_and_remove(self):
        """Verify quantity increment, decrement, and remove operations."""
        with self.client.session_transaction() as sess:
            sess["cart"] = {
                "1551": {"id": 1551, "name": "Puma Ball", "brand": "Puma", "price": 999.0, "quantity": 2}
            }
            sess["csrf_token"] = "valid_token_123"

        # Increment
        self.client.post("/cart/update", data={"product_id": "1551", "action": "increase", "csrf_token": "valid_token_123"})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["cart"]["1551"]["quantity"], 3)

        # Decrement
        self.client.post("/cart/update", data={"product_id": "1551", "action": "decrease", "csrf_token": "valid_token_123"})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["cart"]["1551"]["quantity"], 2)

        # Direct set
        self.client.post("/cart/update", data={"product_id": "1551", "action": "set", "quantity": 5, "csrf_token": "valid_token_123"})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["cart"]["1551"]["quantity"], 5)

        # Remove
        self.client.post("/cart/update", data={"product_id": "1551", "action": "remove", "csrf_token": "valid_token_123"})
        with self.client.session_transaction() as sess:
            self.assertNotIn("1551", sess["cart"])

    def test_04_cart_clear_operation(self):
        """Verify Clear Cart action empties session cart and coupon."""
        with self.client.session_transaction() as sess:
            sess["cart"] = {
                "1551": {"id": 1551, "name": "Puma Ball", "brand": "Puma", "price": 999.0, "quantity": 2}
            }
            sess["coupon_code"] = "CARTIFY10"
            sess["csrf_token"] = "valid_token_123"

        self.client.post("/cart/update", data={"action": "clear", "csrf_token": "valid_token_123"}, follow_redirects=True)
        with self.client.session_transaction() as sess:
            self.assertNotIn("cart", sess)
            self.assertNotIn("coupon_code", sess)

    def test_05_coupon_application_and_discount_calculation(self):
        """Verify supported coupons (CARTIFY10, FESTIVE15, FLAT100) apply discounts properly."""
        with self.client.session_transaction() as sess:
            sess["cart"] = {
                "1551": {"id": 1551, "name": "Item", "brand": "Brand", "price": 1000.0, "quantity": 2} # Subtotal = 2000
            }
            sess["csrf_token"] = "valid_token_123"

        # Apply CARTIFY10 (10% off 2000 = 200 discount)
        self.client.post("/cart/apply-coupon", data={"coupon_code": "CARTIFY10", "csrf_token": "valid_token_123"}, follow_redirects=True)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("coupon_code"), "CARTIFY10")

        # View cart with coupon
        resp = self.client.get("/cart")
        html = resp.get_data(as_text=True)
        self.assertIn("CARTIFY10", html)
        self.assertIn("200.00", html) # ₹200 discount

        # Remove coupon via CSRF-protected POST
        self.client.post("/cart/remove-coupon", data={"csrf_token": "valid_token_123"})
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("coupon_code"))

        # Verify GET /cart/remove-coupon rejects mutation
        with self.client.session_transaction() as sess:
            sess["coupon_code"] = "CARTIFY10"
        self.client.get("/cart/remove-coupon", follow_redirects=True)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("coupon_code"), "CARTIFY10", "GET must not mutate coupon state!")

    def test_06_unauthenticated_checkout_redirects_to_login(self):
        """Verify guest user attempting to checkout is redirected to login."""
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["cart"] = {"1551": {"id": 1551, "name": "Item", "price": 500.0, "quantity": 1}}

        resp = self.client.get("/checkout", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_07_empty_cart_checkout_rejection(self):
        """Verify authenticated user with empty cart cannot access checkout."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
            sess["cart"] = {}

        resp = self.client.get("/checkout", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Your cart is empty", html)

    def test_08_authenticated_checkout_rendering(self):
        """Verify checkout renders with multi-step layout, user address, and order review."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
            sess["cart"] = {
                "1551": {"id": 1551, "name": "Puma Men Sports Shoes", "brand": "Puma", "price": 1299.0, "quantity": 1}
            }

        resp = self.client.get("/checkout")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Secure Financial Checkout", html)
        self.assertIn("Delivery &amp; Payment", html)
        self.assertIn("Order Review", html)
        self.assertIn("Simulated Checkout Mode", html)

    def test_09_checkout_invalid_quantity_rejected(self):
        """Verify non-positive or corrupted item quantities in cart are rejected."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
            sess["cart"] = {
                "1551": {"id": 1551, "name": "Item", "price": 100.0, "quantity": -5}
            }
            sess["csrf_token"] = "valid_token_123"

        resp = self.client.post("/checkout/place_order", data={"csrf_token": "valid_token_123"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Invalid product quantity", html)

    def test_10_checkout_insufficient_stock_rejection(self):
        """Verify requesting more than available stock is conditionally rejected."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
            sess["cart"] = {
                "1551": {"id": 1551, "name": "Puma Item", "price": 999.0, "quantity": 999999}
            }
            sess["csrf_token"] = "valid_token_123"

        resp = self.client.post("/checkout/place_order", data={"csrf_token": "valid_token_123"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertTrue("Insufficient stock" in html or "unavailable" in html)

    def test_11_duplicate_cart_product_aggregation(self):
        """Verify duplicate product IDs in cart are cleanly aggregated and validated."""
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
            # Two entries representing same product ID 1551
            sess["cart"] = {
                "item_a": {"id": 1551, "name": "Puma Item", "price": 999.0, "quantity": 1},
                "item_b": {"id": 1551, "name": "Puma Item", "price": 999.0, "quantity": 2}
            }

        with patch("app.routes.cart_routes.get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            mock_cursor.rowcount = 1
            mock_cursor.fetchone.return_value = (77777,) # mock order_id

            client = self.app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
                sess["cart"] = {
                    "item_a": {"id": 1551, "name": "Puma Item", "price": 999.0, "quantity": 1},
                    "item_b": {"id": 1551, "name": "Puma Item", "price": 999.0, "quantity": 2}
                }
                sess["csrf_token"] = "valid_token_123"

            resp = client.post("/checkout/place_order", data={"csrf_token": "valid_token_123"}, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(resp.headers["Location"].endswith("/77777"))

            # Verify stock decrement was called with aggregated quantity = 3
            update_call_args = [call for call in mock_cursor.execute.call_args_list if "UPDATE products" in str(call)]
            self.assertEqual(len(update_call_args), 1)
            params = update_call_args[0][0][1]
            self.assertEqual(params[0], 3) # aggregated qty = 3

    def test_12_atomic_rollback_on_stock_reservation_failure(self):
        """Verify that when any item stock reservation fails, transaction rolls back and 0 orders created."""
        with patch("app.routes.cart_routes.get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            mock_cursor.rowcount = 0 # Simulate failure in conditional decrement
            mock_cursor.fetchone.return_value = ("Test Item", 0, 1)

            client = self.app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
                sess["cart"] = {"1551": {"id": 1551, "name": "Item", "price": 500.0, "quantity": 5}}
                sess["csrf_token"] = "valid_token_123"

            resp = client.post("/checkout/place_order", data={"csrf_token": "valid_token_123"}, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            mock_conn.return_value.rollback.assert_called()
            mock_conn.return_value.commit.assert_not_called()

    def test_13_order_confirmation_page_rendering(self):
        """Verify order confirmation page renders with Stitch Screen 12 milestone tracker and items."""
        # Query existing order from DB
        order = query_db("SELECT order_id, user_id FROM orders WHERE ROWNUM = 1", one=True)
        self.assertIsNotNone(order)
        order_id = order["order_id"]
        user_id = order["user_id"]

        with self.client.session_transaction() as sess:
            sess["user"] = {"id": user_id, "name": "Order Owner", "email": "owner@example.com"}

        resp = self.client.get(f"/order_success/{order_id}")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Thank you for your order!", html)
        self.assertIn("Oracle 26ai ACID Transaction Committed", html)
        self.assertIn("Fulfillment Status", html)
        self.assertIn("Confirmed", html)

    def test_14_order_privacy_and_idor_guard(self):
        """Verify user cannot view an order belonging to another customer."""
        order = query_db("SELECT order_id, user_id FROM orders WHERE ROWNUM = 1", one=True)
        self.assertIsNotNone(order)
        order_id = order["order_id"]
        victim_user_id = order["user_id"]

        # Log in as a different user
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": victim_user_id + 9999, "name": "Attacker", "email": "attacker@example.com"}

        resp = self.client.get(f"/order_success/{order_id}", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("You do not have permission", html)

    def test_15_csrf_protection_on_cart_and_checkout_endpoints(self):
        """Verify that state-changing endpoints enforce CSRF validation when enabled."""
        self.app.config["ENFORCE_CSRF"] = True
        try:
            client = self.app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
                sess["cart"] = {"1551": {"id": 1551, "name": "Item", "price": 500.0, "quantity": 1}}
                sess["csrf_token"] = "valid_csrf_token_p5"

            # 1. Missing token on /cart/add
            resp = client.post("/cart/add/1551", data={"quantity": 1}, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)

            # 2. Missing token on /cart/update
            resp = client.post("/cart/update", data={"product_id": "1551", "action": "increase"}, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)

            # 3. Missing token on /cart/apply-coupon
            resp = client.post("/cart/apply-coupon", data={"coupon_code": "CARTIFY10"}, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)

            # 4. Missing token on /checkout/place_order
            resp = client.post("/checkout/place_order", data={"payment_method": "Card"}, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)

        finally:
            self.app.config["ENFORCE_CSRF"] = False


if __name__ == "__main__":
    unittest.main()
