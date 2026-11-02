"""
Automated Test Suite for Cartify Phase 4:
Storefront Catalog, Search & Product Detail Modernization.

Verifies:
1. Homepage dynamic product rendering & hero card.
2. Personalized recommendation rendering with real customer session.
3. Popular products and cold-start guest fallback.
4. Search strategy switching (hybrid, semantic, lexical) and UI persistence.
5. Catalog multi-facet filtering (category, gender, price, rating).
6. Catalog pagination and parameter persistence across page links.
7. Catalog empty search state and recovery actions.
8. Product details rendering with real Oracle columns (price_inr, sale_price_inr, stock, specs).
9. Similar-product recommendations (Content-Based TF-IDF + Cosine Similarity).
10. Handling of invalid and non-existent product IDs (clean 404).
11. Add to Cart from product detail with CSRF token and quantity validation.
12. Persistent Wishlist toggle integration from product cards.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.db import query_db

class TestStorefrontCatalogP4(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    def test_01_homepage_rendering_and_hero(self):
        """Verify homepage renders with Stitch Screen 1 components, hero, and categories."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Cartify", html)
        self.assertIn("Curation tailored to your taste", html)
        self.assertIn("Powered by Machine Intelligence", html)
        self.assertIn("Explore Curated Collections", html)
        self.assertIn("Taxonomy Grid", html)
        self.assertIn("Trending & Best Sellers", html)

    def test_02_homepage_personalized_stream_authenticated(self):
        """Verify personalized stream displays customer name and affinity badges for authenticated user."""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {
                "id": 1,
                "name": "Arjun Naidu",
                "email": "arjun@example.com",
                "tier": "Plus"
            }
            sess["wishlist"] = []

        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Personalized Stream for Arjun Naidu", html)
        self.assertIn("Match", html)
        self.assertIn("Hybrid Policy Active", html)

    def test_03_homepage_popular_fallback_guest(self):
        """Verify unauthenticated guests receive valid popular/cold-start recommendations."""
        client = self.app.test_client()
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Personalized Recommendation Stream", html)
        self.assertIn("Quick Add", html)

    def test_04_catalog_search_strategies_switching(self):
        """Verify selectable search strategies (hybrid, semantic, lexical) persist in catalog."""
        client = self.app.test_client()
        for strategy in ["hybrid", "semantic", "lexical"]:
            resp = client.get(f"/products?q=shoes&strategy={strategy}")
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn(f"strategy={strategy}", html)
            self.assertIn('strategy-pill active', html)

    def test_05_catalog_faceted_filtering_persistence(self):
        """Verify faceted filters apply properly and persist in catalog controls."""
        client = self.app.test_client()
        resp = client.get("/products?category=Footwear&gender=Men&sort=price_asc")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Footwear", html)
        self.assertIn("Gender: Men", html)
        self.assertIn("Clear All", html)

    def test_06_catalog_pagination(self):
        """Verify catalog pagination calculates pages and renders navigation links."""
        client = self.app.test_client()
        resp = client.get("/products?page=2")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Page 2 of", html)
        self.assertIn("page=1", html)

    def test_07_catalog_empty_search_state(self):
        """Verify actionable empty state card renders for zero-result queries."""
        client = self.app.test_client()
        resp = client.get("/products?q=xyz987completelynonexistentitem")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("No Matching Products Found", html)
        self.assertIn("Reset All Filters", html)

    def test_08_product_detail_rendering_real_data(self):
        """Verify product detail renders real Oracle columns, INR prices, and specifications."""
        client = self.app.test_client()
        resp = client.get("/product/1551")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Puma", html)
        self.assertIn("Football", html)
        self.assertIn("Technical Attributes from Oracle 26ai", html)
        self.assertIn("Add to Cart", html)
        self.assertIn("Save to Wishlist", html)

    def test_09_product_detail_similar_products_recs(self):
        """Verify content-based TF-IDF similar products carousel renders with match scores."""
        client = self.app.test_client()
        resp = client.get("/product/1551")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("Similar Products You May Like", html)
        self.assertIn("Content-Based TF-IDF + Cosine Similarity", html)
        self.assertIn("% Match", html)

    def test_10_product_detail_invalid_id_404(self):
        """Verify accessing non-existent product ID returns clean 404."""
        client = self.app.test_client()
        resp = client.get("/product/99999999")
        self.assertEqual(resp.status_code, 404)

    def test_11_product_detail_add_to_cart_with_csrf(self):
        """Verify Add to Cart from product detail works with CSRF and updates session."""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["csrf_token"] = "valid_cart_token_999"
            sess["cart"] = {}

        resp = client.post(
            "/cart/add/1551",
            data={"quantity": 2, "csrf_token": "valid_cart_token_999"},
            follow_redirects=False
        )
        self.assertEqual(resp.status_code, 302)
        with client.session_transaction() as sess:
            self.assertIn("1551", sess["cart"])
            self.assertEqual(sess["cart"]["1551"]["quantity"], 2)

    def test_12_product_card_wishlist_toggle(self):
        """Verify Wishlist toggle from storefront product card triggers wishlist endpoint."""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"id": 1, "name": "Arjun Naidu", "email": "arjun@example.com"}
            sess["csrf_token"] = "valid_wishlist_token_888"
            sess["wishlist"] = []

        with patch("app.routes.auth_routes.execute_db") as mock_exec, \
             patch("app.routes.auth_routes.query_db") as mock_query:
            
            mock_query.side_effect = [
                {"product_id": 1551, "product_name": "Puma Ball", "is_active": 1},
                None, # not currently active in wishlist
                []
            ]

            resp = client.post(
                "/wishlist/toggle/1551",
                data={"csrf_token": "valid_wishlist_token_888"},
                headers={"Accept": "application/json"}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["action"], "added")

if __name__ == "__main__":
    unittest.main()
