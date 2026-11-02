"""
Test Suite for Cartify Phase 3: Customer Authentication, Profile Integration & Wishlist Management.
Verifies:
1. Login and registration page rendering (split-screen layout).
2. Existing 1-click viva demo authentication.
3. Authenticated customer profile access (GET /profile).
4. Unauthenticated customer profile protection (redirect to /login).
5. Customer order privacy & IDOR protection.
6. Wishlist addition with storefront_wishlist tag.
7. Wishlist removal with wishlist_remove event.
8. Duplicate active wishlist prevention.
9. Persistent active wishlist query accuracy.
10. CSRF security protection on POST operations.
11. Recommendation history preservation & Oracle zero-pollution verification.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.db import query_db

class TestAuthProfileWishlist(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def test_01_login_and_registration_rendering(self):
        """Verify login/registration split-screen template renders with Teal & Mint styling."""
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Cartify", html)
        self.assertIn("Sign In to Cartify", html)
        self.assertIn("Create Free Account", html)
        self.assertIn("College Viva 1-Click Demo Login", html)
        self.assertIn("cartify-theme.css", html)

    def test_02_demo_login_functionality(self):
        """Verify 1-click demo login authenticates seeded user and populates session."""
        with self.app.test_client() as client:
            resp = client.get("/demo-login/1", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            with client.session_transaction() as sess:
                self.assertIn("user", sess)
                self.assertEqual(sess["user"]["id"], 1)

    def test_03_unauthenticated_profile_access_blocked(self):
        """Verify unauthenticated access to /profile is blocked and redirected to /login."""
        client = self.app.test_client()
        resp = client.get("/profile", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_04_authenticated_profile_access(self):
        """Verify authenticated customer can view their profile command center."""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {
                "id": 1,
                "name": "Aditi Sharma",
                "email": "aditi.sharma@example.com",
                "tier": "Basic"
            }
            sess["wishlist"] = []

        resp = client.get("/profile")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Customer Command Center", html)
        self.assertIn("Welcome back, Arjun", html)
        self.assertIn("Lifetime Orders", html)
        self.assertIn("Saved Wishlist Items", html)
        self.assertIn("Primary Verified Account", html)

    def test_05_customer_order_privacy_guard(self):
        """Verify customers cannot view other customers' orders (IDOR prevention)."""
        # Seeded order 100163 belongs to User 1928
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {
                "id": 1, # User 1 attempting to view User 1928's order
                "name": "Aditi Sharma",
                "email": "aditi@example.com",
                "tier": "Basic"
            }

        resp = client.get("/order_success/100163", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("You do not have permission to view this order confirmation", html)

    def test_06_wishlist_add_toggle_isolated(self):
        """Verify wishlist toggle adds an item with storefront_wishlist tag."""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Aditi Sharma", "email": "aditi@example.com"}
            sess["csrf_token"] = "valid_csrf_token_12345"
            sess["wishlist"] = []

        with patch("app.routes.auth_routes.execute_db") as mock_exec, \
             patch("app.routes.auth_routes.query_db") as mock_query:
            
            # Mock product lookup: exists & active
            mock_query.side_effect = [
                {"product_id": 1163, "product_name": "Nike Running Shoes", "is_active": 1}, # product check
                None, # latest wishlist status: none active
                [] # sync_user_wishlist return
            ]

            resp = client.post(
                "/wishlist/toggle/1163",
                data={"csrf_token": "valid_csrf_token_12345"},
                headers={"Accept": "application/json"}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["action"], "added")
            self.assertTrue(data["active"])

            # Verify SQL executed with correct event_type and storefront_wishlist referrer
            self.assertTrue(mock_exec.called)
            sql_called = mock_exec.call_args[0][0]
            params_called = mock_exec.call_args[0][1]
            self.assertIn("INSERT INTO interactions", sql_called)
            self.assertEqual(params_called[0], 1)      # user_id
            self.assertEqual(params_called[1], 1163)   # product_id
            self.assertEqual(params_called[2], "wishlist")
            self.assertEqual(params_called[3], "storefront_wishlist")

    def test_07_wishlist_remove_toggle_isolated(self):
        """Verify wishlist toggle removes currently active item with wishlist_remove event."""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Aditi Sharma", "email": "aditi@example.com"}
            sess["csrf_token"] = "valid_csrf_token_12345"
            sess["wishlist"] = [1163]

        with patch("app.routes.auth_routes.execute_db") as mock_exec, \
             patch("app.routes.auth_routes.query_db") as mock_query:
            
            mock_query.side_effect = [
                {"product_id": 1163, "product_name": "Nike Running Shoes", "is_active": 1},
                {"event_type": "wishlist"}, # currently active
                []
            ]

            resp = client.post(
                "/wishlist/toggle/1163",
                data={"csrf_token": "valid_csrf_token_12345"},
                headers={"Accept": "application/json"}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["action"], "removed")
            self.assertFalse(data["active"])

            self.assertTrue(mock_exec.called)
            sql_called = mock_exec.call_args[0][0]
            params_called = mock_exec.call_args[0][1]
            self.assertIn("INSERT INTO interactions", sql_called)
            self.assertEqual(params_called[0], 1)
            self.assertEqual(params_called[1], 1163)
            self.assertEqual(params_called[2], "wishlist_remove")
            self.assertEqual(params_called[3], "storefront_wishlist")

    def test_08_duplicate_wishlist_prevention(self):
        """Verify calling wishlist/add on already-active item does not duplicate rows."""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Aditi Sharma", "email": "aditi@example.com"}
            sess["csrf_token"] = "valid_csrf_token_12345"
            sess["wishlist"] = [1163]

        with patch("app.routes.auth_routes.execute_db") as mock_exec, \
             patch("app.routes.auth_routes.query_db") as mock_query:
            
            mock_query.side_effect = [
                {"product_id": 1163, "product_name": "Nike Running Shoes", "is_active": 1},
                {"event_type": "wishlist"}, # already in active wishlist
                []
            ]

            resp = client.post(
                "/wishlist/add/1163",
                data={"csrf_token": "valid_csrf_token_12345"},
                headers={"Accept": "application/json"}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["action"], "already_active")
            # execute_db should NOT be called because it is already active
            self.assertFalse(mock_exec.called, "execute_db should not be called when product is already active in wishlist")

    def test_09_csrf_protection_validation(self):
        """Verify CSRF token protection rejects requests with missing or invalid tokens."""
        # Enable CSRF enforcement for this test
        self.app.config["ENFORCE_CSRF"] = True
        try:
            client = self.app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = {"id": 1, "name": "Aditi Sharma", "email": "aditi@example.com"}
                sess["csrf_token"] = "secret_session_token_xyz"

            # 1. Missing CSRF token
            resp_missing = client.post("/wishlist/toggle/1163", headers={"Accept": "application/json"})
            self.assertEqual(resp_missing.status_code, 403)
            data_missing = resp_missing.get_json()
            self.assertEqual(data_missing["code"], "CSRF_ERROR")

            # 2. Invalid CSRF token
            resp_invalid = client.post(
                "/wishlist/toggle/1163",
                data={"csrf_token": "wrong_token_123"},
                headers={"Accept": "application/json"}
            )
            self.assertEqual(resp_invalid.status_code, 403)
            data_invalid = resp_invalid.get_json()
            self.assertEqual(data_invalid["code"], "CSRF_ERROR")

            # 3. Valid matching CSRF token
            with patch("app.routes.auth_routes.execute_db"), \
                 patch("app.routes.auth_routes.query_db") as mock_query:
                mock_query.side_effect = [
                    {"product_id": 1163, "product_name": "Shoes", "is_active": 1},
                    None,
                    []
                ]
                resp_valid = client.post(
                    "/wishlist/toggle/1163",
                    data={"csrf_token": "secret_session_token_xyz"},
                    headers={"Accept": "application/json"}
                )
                self.assertEqual(resp_valid.status_code, 200)
        finally:
            self.app.config["ENFORCE_CSRF"] = False

    def test_10_recommendation_history_preserved_zero_db_pollution(self):
        """Verify that live Oracle interaction rows remain completely untouched."""
        total_interactions = query_db("SELECT COUNT(*) as cnt FROM interactions", one=True)["cnt"]
        self.assertEqual(total_interactions, 50056, f"Expected 50,056 interactions, found {total_interactions}")
        total_orders = query_db("SELECT COUNT(*) as cnt FROM orders", one=True)["cnt"]
        self.assertEqual(total_orders, 18951, f"Expected 18,951 orders, found {total_orders}")
        total_products = query_db("SELECT COUNT(*) as cnt FROM products", one=True)["cnt"]
        self.assertEqual(total_products, 35254, f"Expected 35,254 products, found {total_products}")

    def test_11_oracle_products_column_names_verified(self):
        """Verify that PRODUCTS columns price_inr, sale_price_inr, rating, review_count exist and execute safely."""
        row = query_db("""
            SELECT product_id, product_name, price_inr, sale_price_inr, discount_percent, rating, review_count
            FROM products
            WHERE is_active = 1
            FETCH FIRST 1 ROWS ONLY
        """, one=True)
        self.assertIsNotNone(row)
        self.assertIn("product_id", row)
        self.assertIn("price_inr", row)
        self.assertIn("sale_price_inr", row)
        self.assertIn("rating", row)
        self.assertIn("review_count", row)
        # Verify unit_price and rating_avg do NOT exist in PRODUCTS
        col_names = [c["column_name"].lower() for c in query_db("SELECT column_name FROM user_tab_cols WHERE table_name = 'PRODUCTS'")]
        self.assertIn("price_inr", col_names)
        self.assertIn("sale_price_inr", col_names)
        self.assertIn("rating", col_names)
        self.assertIn("review_count", col_names)
        self.assertNotIn("unit_price", col_names, "unit_price must not exist in PRODUCTS (it belongs to ORDER_ITEMS)")
        self.assertNotIn("rating_avg", col_names, "rating_avg must not exist in PRODUCTS (column is RATING)")

    def test_12_customer_order_links_and_alias_idor_verified(self):
        """Verify that both /order_success/<id> and /order/<id> endpoints exist, resolve, and enforce IDOR."""
        client = self.app.test_client()
        # Seeded order 100163 belongs to User 1928
        # 1. Test /order/<id> without login
        resp_anon = client.get("/order/100163", follow_redirects=False)
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn("/login", resp_anon.headers.get("Location", ""))

        # 2. Test /order/<id> with unauthorized user (IDOR attempt)
        with client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com", "tier": "Plus"}
        resp_unauth = client.get("/order/100163", follow_redirects=True)
        self.assertEqual(resp_unauth.status_code, 200)
        html = resp_unauth.get_data(as_text=True)
        self.assertIn("You do not have permission to view this order confirmation", html)

        # 3. Test /order_success/<id> with unauthorized user (IDOR attempt)
        resp_unauth_success = client.get("/order_success/100163", follow_redirects=True)
        self.assertEqual(resp_unauth_success.status_code, 200)
        html_success = resp_unauth_success.get_data(as_text=True)
        self.assertIn("You do not have permission to view this order confirmation", html_success)

    def test_13_complete_csrf_coverage_cart_checkout_auth(self):
        """Verify that all state-changing POST endpoints reject requests when CSRF token is invalid/missing."""
        self.app.config["ENFORCE_CSRF"] = True
        try:
            client = self.app.test_client()
            with client.session_transaction() as sess:
                sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com", "tier": "Plus"}
                sess["csrf_token"] = "correct_token_cartify_789"
                sess["cart"] = {"1163": {"id": 1163, "name": "Shoe", "price": 999.0, "quantity": 1}}

            endpoints_to_test = [
                ("/cart/add/1163", {"quantity": 1}),
                ("/cart/update", {"product_id": "1163", "action": "increase"}),
                ("/cart/apply-coupon", {"coupon_code": "WELCOME10"}),
                ("/checkout/place_order", {"city": "Mumbai", "state": "Maharashtra"}),
                ("/wishlist/toggle/1163", {}),
                ("/wishlist/remove/1163", {}),
                ("/wishlist/add/1163", {}),
            ]

            for path, form_data in endpoints_to_test:
                # A: Missing CSRF token -> Rejected (redirect or 403)
                resp = client.post(path, data=form_data, follow_redirects=False)
                if path.startswith("/wishlist"):
                    # JSON header returns 403
                    resp_json = client.post(path, data=form_data, headers={"Accept": "application/json"})
                    self.assertEqual(resp_json.status_code, 403, f"{path} should return 403 when CSRF missing")
                else:
                    self.assertEqual(resp, resp) # Verify response received
                    self.assertEqual(resp.status_code, 302, f"{path} should redirect on missing CSRF token")

                # B: Invalid CSRF token -> Rejected
                bad_data = dict(form_data)
                bad_data["csrf_token"] = "tampered_csrf_token_xyz"
                resp_bad = client.post(path, data=bad_data, follow_redirects=False)
                if path.startswith("/wishlist"):
                    resp_bad_json = client.post(path, data=bad_data, headers={"Accept": "application/json"})
                    self.assertEqual(resp_bad_json.status_code, 403, f"{path} should return 403 on invalid CSRF")
                else:
                    self.assertEqual(resp_bad.status_code, 302, f"{path} should redirect on invalid CSRF")

        finally:
            self.app.config["ENFORCE_CSRF"] = False

if __name__ == "__main__":
    unittest.main()
