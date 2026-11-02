"""
Automated Test Suite for Cartify Phase 6:
Store Owner Dashboard and Role-Based Management Foundation.

Tests:
1. Unauthenticated guest access to /owner/dashboard redirects to /login.
2. Unauthenticated guest access to /owner redirects to /login.
3. Ordinary customer (Basic/Plus/Standard membership) access to /owner/dashboard is blocked with HTTP 403.
4. Ordinary customer access to /owner placeholder routes is blocked with HTTP 403.
5. Verified Store Owner (user 51 Bharath Patel / ADMIN_EMAILS) gains HTTP 200 access to /owner/dashboard.
6. Dashboard renders real Oracle metrics (Total SKUs, Active SKUs, Orders, Revenue, AOV).
7. Dashboard renders Low Stock alerts table with defined threshold (<= 35 units).
8. Dashboard renders Recent Transactions table with real database records.
9. Dashboard renders Catalog Health and Stock Availability distribution.
10. Store Owner can access Phase 7 placeholder routes (/owner/products, /owner/inventory, /owner/orders).
11. Direct unit test of is_store_owner() logic (admin email whitelist, session role, user dict, inactive user).
12. Owner sidebar and header navigation render expected operational links and Oracle 26ai live badge.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.security import is_store_owner, ADMIN_EMAILS


class TestStoreOwnerP6(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.app.config["ENFORCE_CSRF"] = False
        self.client = self.app.test_client()

    def test_01_unauthenticated_owner_redirect(self):
        """Unauthenticated requests to /owner/dashboard must redirect to /login with next param."""
        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].startswith("/login"))
        self.assertIn("next=", resp.headers["Location"])

    def test_02_unauthenticated_owner_root_redirect(self):
        """Unauthenticated requests to /owner/ must redirect to /login."""
        resp = self.client.get("/owner/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].startswith("/login"))

    def test_03_ordinary_customer_blocked_with_403(self):
        """Ordinary customers (even with active sessions) must receive HTTP 403 Forbidden."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 52,  # Kavya Rao (Basic membership tier)
                "name": "Kavya Rao",
                "email": "kavya.rao21@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = False

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 403)
        html = resp.get_data(as_text=True)
        self.assertIn("403", html)
        self.assertIn("Access Restricted", html)

    def test_04_ordinary_customer_blocked_from_placeholders(self):
        """Ordinary customers must be blocked from all /owner/* management sub-routes."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 52,
                "name": "Kavya Rao",
                "email": "kavya.rao21@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = False

        for endpoint in ["/owner/products", "/owner/inventory", "/owner/orders"]:
            resp = self.client.get(endpoint)
            self.assertEqual(resp.status_code, 403)

    def test_05_verified_owner_access_granted(self):
        """Verified active store manager (User 53 Arjun Shetty, is_active=1) gains access."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 53,
                "name": "Arjun Shetty",
                "email": "arjun.shetty53@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = True

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Store Overview", html)
        self.assertIn("ORACLE DB SYNCED", html)

    def test_06_dashboard_metrics_rendering(self):
        """Dashboard must render live aggregate metrics from Oracle Database 26ai."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 53,
                "name": "Arjun Shetty",
                "email": "arjun.shetty53@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = True

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Core metric card headings
        self.assertIn("Catalog Depth", html)
        self.assertIn("Total Orders", html)
        self.assertIn("Stock Vigilance", html)
        self.assertIn("Gross Revenue", html)

        # Real numbers or symbols
        self.assertIn("35,254", html)  # Total SKUs
        self.assertIn("18,951", html)  # Total Orders
        self.assertIn("₹", html)       # Revenue symbol

    def test_07_low_stock_alerts_rendering(self):
        """Dashboard renders Low Stock Alerts table with critical threshold <= 35 units."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 53,
                "name": "Arjun Shetty",
                "email": "arjun.shetty53@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = True

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn("Low Stock Alerts", html)
        self.assertIn("Reorder", html)
        self.assertIn("left", html)

    def test_08_recent_transactions_rendering(self):
        """Dashboard renders Recent Transactions ledger with order numbers and status badges."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 53,
                "name": "Arjun Shetty",
                "email": "arjun.shetty53@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = True

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn("Recent Transactions", html)
        self.assertIn("#ORD-", html)

    def test_09_catalog_health_breakdown_rendering(self):
        """Dashboard renders catalog health breakdown bar and legend cards."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 53,
                "name": "Arjun Shetty",
                "email": "arjun.shetty53@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = True

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn("Catalog Health &amp; Stock Availability", html)
        self.assertIn("Nominal", html)
        self.assertIn("Healthy SKUs", html)

    def test_10_owner_placeholder_routes(self):
        """Store Owner can access Phase 7 placeholder routes and see planned release cards."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 53,
                "name": "Arjun Shetty",
                "email": "arjun.shetty53@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = True

        routes = [
            ("/owner/products", "Product"),
            ("/owner/inventory", "Inventory"),
            ("/owner/orders", "Order")
        ]

        for path, title_fragment in routes:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn(title_fragment, html)

    def test_11_is_store_owner_unit_logic(self):
        """Verify multi-tier authorization logic in is_store_owner()."""
        # 1. None user
        self.assertFalse(is_store_owner(None))

        # 2. Empty dict
        self.assertFalse(is_store_owner({}))

        # 3. Ordinary customer dict (user 52)
        ordinary_user = {"id": 52, "email": "kavya.rao52@example.com"}
        self.assertFalse(is_store_owner(ordinary_user))

        # 4. Deactivated manager in DB (user 51 Bharath Patel has is_active=0 in Oracle)
        deactivated_admin = {"id": 51, "email": "bharath.patel51@example.com"}
        self.assertFalse(is_store_owner(deactivated_admin))

        # 5. Whitelisted email with non-existent database ID
        nonexistent_admin = {"id": 999999, "email": "admin@cartify.com"}
        self.assertFalse(is_store_owner(nonexistent_admin))

        # 6. Forged browser/session email (user 52 claiming to be admin@cartify.com)
        forged_email_user = {"id": 52, "email": "admin@cartify.com"}
        self.assertFalse(is_store_owner(forged_email_user))

        # 7. Verified active admin user (user 53 Arjun Shetty has is_active=1 in Oracle)
        active_admin = {"id": 53, "email": "arjun.shetty53@example.com"}
        self.assertTrue(is_store_owner(active_admin))

    def test_12_owner_sidebar_navigation_links(self):
        """Owner navigation sidebar contains valid routes for dashboard, inventory, products, orders."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 53,
                "name": "Arjun Shetty",
                "email": "arjun.shetty53@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = True

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        self.assertIn('/owner/dashboard', html)
        self.assertIn('/owner/inventory', html)
        self.assertIn('/owner/products', html)
        self.assertIn('/owner/orders', html)
        self.assertIn('/evaluation', html)

    def test_13_deactivated_owner_blocked_at_route(self):
        """Deactivated store manager (user 51) requesting /owner/dashboard gets 403 Forbidden."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 51,
                "name": "Bharath Patel",
                "email": "bharath.patel51@example.com",
                "tier": "Basic"
            }
            sess["is_admin"] = True

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 403)

    def test_14_whitelisted_email_nonexistent_account_blocked(self):
        """Whitelisted email without a valid matching database row gets 403 Forbidden."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 999999,
                "name": "Ghost Admin",
                "email": "admin@cartify.com",
                "tier": "Admin"
            }
            sess["is_admin"] = True

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 403)

    def test_15_forged_admin_flag_ordinary_customer_blocked(self):
        """Ordinary customer with forged session['is_admin']=True gets 403 Forbidden."""
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "id": 52,
                "name": "Kavya Rao",
                "email": "kavya.rao52@example.com",
                "tier": "Premium"
            }
            sess["is_admin"] = True  # Forged administrative flag

        resp = self.client.get("/owner/dashboard")
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
