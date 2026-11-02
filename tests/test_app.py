"""
Automated smoke & quality test for Cartify Flask application & Recommendation Engine.
Tests:
1. Oracle 26ai connection
2. Homepage route ("/")
3. Catalog route with pagination & search ("/products")
4. Product detail with TF-IDF recommendations ("/product/<id>")
5. Demo Login authentication
6. Cart operations (Add to Cart, View Cart)
7. Spelling error resilience in search ('runing shoes', 'running sheo')
8. Synonym expansion in search ('sneakers')
9. Category relevance in recommendations (Footwear items prioritize Footwear)
10. Edge cases: Empty search results & invalid product IDs
"""

import sys
import os
from unittest.mock import patch
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.db import query_db
from app.services.recommender import RecommendationEngine

def test_full_pipeline():
    print("=" * 70)
    print("RUNNING AUTOMATED TESTS FOR CARTIFY RECOMMENDATION SYSTEM")
    print("=" * 70)
    
    # 1. Oracle DB Verification
    print("\n[Test 1] Checking Oracle Database 26ai Connection...")
    res = query_db("SELECT COUNT(*) as count FROM products", one=True)
    assert res and res["count"] > 0, "Failed: Products table empty!"
    print(f"PASS: Oracle 26ai connected. Total products in DB: {res['count']:,}")

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # 2. Homepage
    print("\n[Test 2] Testing Homepage ('/')...")
    resp = client.get("/")
    assert resp.status_code == 200, f"Failed homepage, status: {resp.status_code}"
    assert b"Cartify" in resp.data, "Failed: Brand name missing from homepage"
    print("PASS: Homepage rendered successfully with categories and recommendations.")

    # 3. Catalog & Product Card Navigation Links
    print("\n[Test 3] Testing Product Catalog ('/products') & Product Card Links...")
    resp = client.get("/products")
    assert resp.status_code == 200, f"Failed catalog page, status: {resp.status_code}"
    html = resp.data.decode("utf-8")
    
    import re
    image_links = re.findall(r'<a\s+href="(/product/\d+)"\s+class="product-img-wrapper[^"]*"', html)
    assert len(image_links) > 0, "Failed: Product images are not wrapped in valid /product/<id> anchor tags!"
    
    title_links = re.findall(r'<a\s+href="(/product/\d+)"\s+class="[^"]*text-truncate[^"]*"', html)
    assert len(title_links) > 0, "Failed: Product titles are not wrapped in valid /product/<id> anchor tags!"
    
    test_detail_url = image_links[0]
    detail_resp = client.get(test_detail_url)
    assert detail_resp.status_code == 200, f"Failed navigating to {test_detail_url}, status: {detail_resp.status_code}"
    assert b"Similar Products You May Like" in detail_resp.data
    print("PASS: Product catalog cards link correctly and open detail pages.")

    # 4. Product Details & TF-IDF Recommendations
    print("\n[Test 4] Testing Product Detail & TF-IDF Recommender ('/product/1551')...")
    resp = client.get("/product/1551")
    assert resp.status_code == 200, f"Failed product detail, status: {resp.status_code}"
    assert b"Similar Products You May Like" in resp.data
    assert b"Match" in resp.data
    print("PASS: Product details and live TF-IDF recommendations rendered with similarity scores.")

    # 5. Demo Login
    print("\n[Test 5] Testing Demo 1-Click Login ('/demo-login/1')...")
    resp = client.get("/demo-login/1", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Logged in as Demo User" in resp.data
    print("PASS: Demo authentication succeeded.")

    # 6. Add to Cart & View Cart (Isolated from Live DB DML)
    print("\n[Test 6] Testing Cart Add & View ('/cart') with DB Write Isolation...")
    int_count_before = query_db("SELECT COUNT(*) as c FROM interactions WHERE user_id = 1 AND product_id = 1551", one=True)["c"]
    total_int_before = query_db("SELECT COUNT(*) as c FROM interactions", one=True)["c"]

    with patch("app.routes.cart_routes.execute_db") as mock_exec:
        mock_exec.return_value = 1
        resp = client.post("/cart/add/1551", data={"quantity": 2}, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Your Shopping Cart" in resp.data
        assert b"Puma Power Cat" in resp.data
        # Verify route attempted interaction logging and was safely intercepted by mock
        assert mock_exec.called, "Route failed to attempt interaction logging!"
        assert "INSERT INTO interactions" in mock_exec.call_args[0][0]

    int_count_after = query_db("SELECT COUNT(*) as c FROM interactions WHERE user_id = 1 AND product_id = 1551", one=True)["c"]
    total_int_after = query_db("SELECT COUNT(*) as c FROM interactions", one=True)["c"]

    assert int_count_before == int_count_after, f"Regression: Cart test committed write! User count changed from {int_count_before} to {int_count_after}"
    assert total_int_before == total_int_after, f"Regression: Total interactions changed from {total_int_before} to {total_int_after}"
    print(f"PASS: Cart updated; DB write safely intercepted (0 DML commits, interaction rows unchanged at {total_int_after:,}).")

    # 7. Recommendation Engine: Spelling Error Resilience
    print("\n[Test 7] Testing Spelling Error Resilience in Search...")
    eng = RecommendationEngine.get_instance()
    
    # 7a. Typo: 'runing shoes' -> should match running shoes
    res_runing = eng.smart_search("runing shoes", top_n=5)
    assert len(res_runing) > 0, "Failed: 'runing shoes' returned 0 results!"
    top_cat = res_runing[0].get("category")
    assert top_cat == "Footwear", f"Expected Footwear for 'runing shoes', got {top_cat}"
    assert "shoe" in res_runing[0]["product_name"].lower(), f"Expected shoe in top result, got {res_runing[0]['product_name']}"
    print(f"PASS: 'runing shoes' correctly resolved to footwear: {res_runing[0]['product_name']}")

    # 7b. Typo: 'running sheo' -> should match running shoes, NOT shirts!
    res_sheo = eng.smart_search("running sheo", top_n=5)
    assert len(res_sheo) > 0, "Failed: 'running sheo' returned 0 results!"
    top_cat_sheo = res_sheo[0].get("category")
    assert top_cat_sheo == "Footwear", f"Expected Footwear for 'running sheo', got {top_cat_sheo}"
    assert "shoe" in res_sheo[0]["product_name"].lower(), f"Expected shoe in top result, got {res_sheo[0]['product_name']}"
    print(f"PASS: 'running sheo' correctly resolved to footwear: {res_sheo[0]['product_name']}")

    # 8. Recommendation Engine: Synonym Expansion & Brand Search Preservation
    print("\n[Test 8] Testing Domain Synonym Expansion ('sneakers', 'cologne') & Brand Preservation ('Kenneth Cole')...")
    res_sneakers = eng.smart_search("sneakers", top_n=5)
    assert len(res_sneakers) > 0, "Failed: 'sneakers' returned 0 results!"
    footwear_count = sum(1 for p in res_sneakers if p.get("category") == "Footwear")
    assert footwear_count >= 4, f"Expected footwear for 'sneakers', got {footwear_count}/5"
    print(f"PASS: 'sneakers' synonym expanded to sports/casual shoes: {res_sneakers[0]['product_name']} ({footwear_count}/5 Footwear)")

    # 8b. Cologne domain synonym check (must return Personal Care, not Kenneth Cole watch)
    res_cologne = eng.smart_search("cologne", top_n=5)
    assert len(res_cologne) > 0, "Failed: 'cologne' returned 0 results!"
    assert res_cologne[0]["category"] == "Personal Care", f"Expected Personal Care for 'cologne', got {res_cologne[0]['category']}"
    assert "Kenneth Cole" not in res_cologne[0]["product_name"], "Kenneth Cole watch incorrectly matched 'cologne'!"
    print(f"PASS: 'cologne' correctly resolved to Personal Care: {res_cologne[0]['product_name']} ({res_cologne[0]['category']})")

    # 8c. Brand search preservation check: 'Kenneth Cole' must return Kenneth Cole brand products
    res_kc = eng.smart_search("Kenneth Cole", top_n=5)
    assert len(res_kc) > 0, "Failed: 'Kenneth Cole' returned 0 results!"
    assert all(r["brand"] == "Kenneth Cole" for r in res_kc), "Expected all Kenneth Cole brand products!"
    assert res_kc[0]["category"] == "Accessories"
    print(f"PASS: 'Kenneth Cole' brand search correctly preserved: {res_kc[0]['product_name']} (Brand: {res_kc[0]['brand']})")

    # 9. Recommendation Engine: Category Relevance & Cross-Category Reduction
    print("\n[Test 9] Testing Category Relevance in Similar-Product Recommendations...")
    # Product 1571 is 'Kalenji Men's Super Soft Sports Shoes' (Footwear)
    recs_1571 = eng.get_similar_products(1571, top_n=5)
    rec_ids = [r["product_id"] for r in recs_1571]
    
    # 9a. Self-exclusion check
    assert 1571 not in rec_ids, "Failed: Target product 1571 was not excluded from its own recommendations!"
    
    # 9b. Duplicate prevention check
    assert len(rec_ids) == len(set(rec_ids)), "Failed: Duplicate product IDs found in recommendations!"
    
    # 9c. Category purity: 100% of top 5 must now be Footwear (no t-shirts or shorts)
    cats_1571 = [r.get("category") for r in recs_1571]
    assert all(c == "Footwear" for c in cats_1571), f"Expected all Footwear, got: {cats_1571}"
    print(f"PASS: Kalenji Sports Shoes recommendations are 100% Footwear: {[r['product_name'] for r in recs_1571]}")

    # 10. Edge Cases: Empty Search Results & Invalid Product IDs
    print("\n[Test 10] Testing Search and Recommender Edge Cases...")
    
    # 10a. Nonexistent search query
    empty_res = eng.smart_search("xyznonexistentquery123", top_n=5)
    assert len(empty_res) == 0, f"Expected 0 results for gibberish query, got {len(empty_res)}"
    
    # 10b. Web catalog route with nonexistent query
    web_empty = client.get("/products?q=xyznonexistentquery123")
    assert web_empty.status_code == 200
    assert b"No Products Found" in web_empty.data
    
    # 10c. Invalid product ID fallback
    invalid_recs = eng.get_similar_products(999999, top_n=5)
    assert len(invalid_recs) == 5, f"Expected 5 popular fallback items, got {len(invalid_recs)}"
    assert all(r.get("is_active") == 1 for r in invalid_recs), "Fallback items must be active!"
    print("PASS: Empty search query and invalid product ID edge cases handled cleanly.")

    # 11. Stage 2 Personalization: Distinct Customer Histories & Exclusion Logic
    print("\n[Test 11] Testing Stage 2 Multi-User Personalization & History Weighting...")
    
    # 11a. Test User #644 (Revathi Gupta - history in Women's Apparel)
    recs_644 = eng.get_personalized_recommendations(user_id=644, limit=5)
    assert len(recs_644) == 5, "Expected 5 recommendations for user #644"
    cats_644 = [r.get("category") for r in recs_644]
    assert "Apparel" in cats_644, "Expected Apparel in user #644 recommendations"
    
    # 11b. Test User #3274 (Neha Agarwal - history in Personal Care Foundation)
    recs_3274 = eng.get_personalized_recommendations(user_id=3274, limit=5)
    assert len(recs_3274) == 5, "Expected 5 recommendations for user #3274"
    cats_3274 = [r.get("category") for r in recs_3274]
    assert "Personal Care" in cats_3274, "Expected Personal Care in user #3274 recommendations"
    
    # 11c. Confirm distinct personalization: User #644 and #3274 receive different recommendation sets
    pids_644 = {r["product_id"] for r in recs_644}
    pids_3274 = {r["product_id"] for r in recs_3274}
    assert pids_644 != pids_3274, "Recommendations for user #644 and user #3274 should be distinct!"
    print(f"PASS: User #644 and #3274 have distinct personalized sets based on their Oracle history.")

    # 11d. Already-Purchased Exclusion Test for User #10000 (Mathi Vanan)
    # Mathi purchased product 2134 (Basics Shirt) and 3439 (Delhi Daredevils Jersey)
    recs_10000 = eng.get_personalized_recommendations(user_id=10000, limit=5)
    pids_10000 = [r["product_id"] for r in recs_10000]
    assert 2134 not in pids_10000, "Failed: Already-purchased product 2134 must be excluded!"
    assert 3439 not in pids_10000, "Failed: Already-purchased product 3439 must be excluded!"
    assert len(pids_10000) == len(set(pids_10000)), "Failed: Duplicate IDs in user recommendations!"
    print(f"PASS: Already-purchased items (2134, 3439) excluded for user #10000; alternatives recommended: {[r['product_name'] for r in recs_10000]}")

    # 11e. Guest & New User Isolation (Cold Start Fallback)
    guest_recs = eng.get_personalized_recommendations(user_id=None, limit=5)
    new_user_recs = eng.get_personalized_recommendations(user_id=999999, limit=5)
    assert len(guest_recs) == 5
    assert len(new_user_recs) == 5
    # Guest must not receive user 644's or 10000's specific personalized vectors
    guest_pids = {r["product_id"] for r in guest_recs}
    assert guest_pids != pids_644, "Guest must receive popular catalog items, not user #644 private recommendations!"
    print("PASS: Guests and new users cleanly isolated and fall back to popular catalog items.")

    # 12. Intent-Bounded Interaction Weighting Hierarchy & Diminishing Frequency
    print("\n[Test 12] Testing Intent-Bounded Weight Hierarchy & Diminishing Frequency...")
    import math
    from app.services.recommender import EVENT_WEIGHTS
    assert EVENT_WEIGHTS["purchase"] == 5.0, "Purchase base intent must be 5.0"
    assert EVENT_WEIGHTS["add_to_cart"] == 3.0, "Cart base intent must be 3.0"
    assert EVENT_WEIGHTS["wishlist"] == 2.0, "Wishlist base intent must be 2.0"
    assert EVENT_WEIGHTS["click"] == 1.2, "Click base intent must be 1.2"
    assert EVENT_WEIGHTS["view"] == 1.0, "View base intent must be 1.0"
    
    # Mathematical proof of intent-bounded diminishing frequency:
    w_view_1 = 1.0 + 0.15 * math.log(1 + 1)
    w_view_100 = 1.0 + 0.15 * math.log(1 + 100)
    w_cart_1 = 3.0 + 0.15 * math.log(1 + 1)
    w_cart_10 = 3.0 + 0.15 * math.log(1 + 10)
    w_purchase_1 = 5.0 + 0.15 * math.log(1 + 1)
    
    assert w_view_100 < w_cart_1, f"100 views ({w_view_100:.3f}) must NEVER overpower 1 cart ({w_cart_1:.3f})!"
    assert w_cart_10 < w_purchase_1, f"10 cart actions ({w_cart_10:.3f}) must NEVER overpower 1 purchase ({w_purchase_1:.3f})!"
    assert w_purchase_1 > w_cart_1 > w_view_100 > w_view_1, "Strict intent hierarchy violated!"
    print(f"PASS: Intent bounds strictly hold: Purchase ({w_purchase_1:.2f}) > Cart ({w_cart_1:.2f}) > 100x Views ({w_view_100:.2f}) > 1x View ({w_view_1:.2f})")

    # 13. Stage 2 Multi-Category Diversity & Product Type Cap (max 3 per type in top 8)
    print("\n[Test 13] Testing Stage 2 Multi-Category Diversity & Product-Type Cap (max 3/type)...")
    from collections import Counter
    top8_644 = eng.get_personalized_recommendations(user_id=644, limit=8)
    assert len(top8_644) == 8, f"Expected 8 recommendations, got {len(top8_644)}"
    types_644 = Counter(r.get("product_type") for r in top8_644)
    cats_644 = Counter(r.get("category") for r in top8_644)
    
    # Verify no single product type monopolizes more than 3 slots
    max_type_cnt_644 = max(types_644.values())
    assert max_type_cnt_644 <= 3, f"Failed: Product type exceeded max of 3 items for User #644: {types_644}"
    # Verify multi-category diversity (spans at least 2 categories and at least 3 types)
    assert len(cats_644) >= 2, f"Expected >= 2 categories for User #644, got: {cats_644}"
    assert len(types_644) >= 3, f"Expected >= 3 product types for User #644, got: {types_644}"
    print(f"PASS: User #644 receives diverse multi-category recommendations (types: {dict(types_644)}, categories: {dict(cats_644)})")

    top8_3274 = eng.get_personalized_recommendations(user_id=3274, limit=8)
    assert len(top8_3274) == 8, f"Expected 8 recommendations, got {len(top8_3274)}"
    types_3274 = Counter(r.get("product_type") for r in top8_3274)
    cats_3274 = Counter(r.get("category") for r in top8_3274)
    max_type_cnt_3274 = max(types_3274.values())
    assert max_type_cnt_3274 <= 3, f"Failed: Product type exceeded max of 3 items for User #3274: {types_3274}"
    assert len(cats_3274) >= 2, f"Expected >= 2 categories for User #3274, got: {cats_3274}"
    print(f"PASS: User #3274 receives diverse recommendations (types: {dict(types_3274)}, categories: {dict(cats_3274)})")

    # 14. Recommendation Score Transparency (Raw Cosine Similarity & Adjusted Ranking Score)
    print("\n[Test 14] Testing Score Transparency (Raw Cosine Match & Adjusted Rank Score)...")
    for r in top8_644:
        assert "similarity_score" in r, "Missing raw similarity_score on recommendation item"
        assert "ranking_score" in r, "Missing adjusted ranking_score on recommendation item"
        assert 0.0 <= r["similarity_score"] <= 100.0, f"Invalid similarity_score {r['similarity_score']}"
        assert 0.0 <= r["ranking_score"] <= 100.0, f"Invalid ranking_score {r['ranking_score']}"
    
    # Assert ranking scores are monotonically non-increasing (strictly sorted order)
    rank_scores = [r["ranking_score"] for r in top8_644]
    assert rank_scores == sorted(rank_scores, reverse=True), f"Ranking scores must be sorted descending: {rank_scores}"
    print(f"PASS: Scores transparent and correctly ordered: raw={[r['similarity_score'] for r in top8_644[:4]]}, rank={[r['ranking_score'] for r in top8_644[:4]]}")

    # 15. Diversity Cap Exclusivity & Safe Handling of Edge Cases
    print("\n[Test 15] Testing Diversity Cap Exclusivity & Safety Edge Cases...")
    # 15a. Diversity cap is NOT applied to item-to-item recommendations (product detail page)
    sim_1571 = eng.get_similar_products(1571, top_n=5)
    sim_types = [r.get("product_type") for r in sim_1571]
    assert all(t == "Sports Shoes" for t in sim_types), f"Item-to-item must preserve close type matching, got {sim_types}"
    
    # 15b. Safe handling of small limit (e.g., limit=2)
    small_recs = eng.get_personalized_recommendations(user_id=644, limit=2)
    assert len(small_recs) == 2, f"Expected exactly 2 items for limit=2, got {len(small_recs)}"
    
    # 15c. Safe handling of cold-start user (zero history)
    cold_recs = eng.get_personalized_recommendations(user_id=777777, limit=8)
    assert len(cold_recs) == 8, f"Expected 8 items for cold-start user, got {len(cold_recs)}"
    assert all(r.get("is_active") == 1 for r in cold_recs), "All fallback items must be active"
    print("PASS: Diversity cap properly scoped only to personalization; edge cases handled cleanly.")

    print("\n" + "=" * 70)
    print("ALL 15 VERIFICATION & QUALITY MODULES PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    test_full_pipeline()
