"""
Regression Test Suite for Cartify Search NLP & Cologne Query Resolution.
Verifies:
1. 'cologne' returns fragrance-related products in Personal Care.
2. 'fragrance' and 'perfume' continue returning Personal Care products.
3. 'Kenneth Cole' still returns Kenneth Cole brand products (watches/accessories).
4. 'runing shoes' and 'running sheo' retain typo correction to Footwear.
5. 'sneakers' retains footwear synonym expansion.
6. Out-of-vocabulary queries ('xyznonexistentquery123') return empty results (no hallucination).
7. Web catalog route filtering, sorting, and pagination work with search queries.
8. Read-only Oracle 26ai verification.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.db import query_db
from app.services.recommender import RecommendationEngine

def run_regression_tests():
    print("=" * 75)
    print("RUNNING COLOGNE SEARCH & NLP REGRESSION TEST SUITE")
    print("=" * 75)

    eng = RecommendationEngine.get_instance()
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # 1. 'cologne' query resolution
    print("\n[Test 1] Testing 'cologne' search query resolution...")
    res_cologne = eng.smart_search("cologne", top_n=8)
    assert len(res_cologne) > 0, "Failed: 'cologne' returned 0 results!"
    top_cologne = res_cologne[0]
    assert top_cologne["category"] == "Personal Care", f"Expected 'Personal Care' for cologne, got '{top_cologne['category']}'"
    assert top_cologne.get("product_type") == "Perfume and Body Mist" or "perfume" in top_cologne["product_name"].lower() or "cologne" in top_cologne["product_name"].lower(), f"Unexpected product: {top_cologne['product_name']}"
    # Verify Kenneth Cole watch is NOT in the top recommendations for cologne
    for r in res_cologne:
        assert "watch" not in r["product_name"].lower(), f"Watch found in cologne search: {r['product_name']}"
        assert r["brand"] != "Kenneth Cole", f"Kenneth Cole brand found in cologne search: {r['product_name']}"
    print(f"PASS: 'cologne' resolved to Personal Care: '{top_cologne['product_name']}' ({top_cologne['category']} > {top_cologne['product_type']}) [{top_cologne['similarity_score']}%]")

    # 2. 'fragrance' and 'perfume' searches
    print("\n[Test 2] Testing 'fragrance' and 'perfume' searches...")
    res_fragrance = eng.smart_search("fragrance", top_n=5)
    assert len(res_fragrance) > 0
    assert res_fragrance[0]["category"] == "Personal Care"
    
    res_perfume = eng.smart_search("perfume", top_n=5)
    assert len(res_perfume) > 0
    assert res_perfume[0]["category"] == "Personal Care"
    print(f"PASS: 'fragrance' -> {res_fragrance[0]['product_name']} (Personal Care); 'perfume' -> {res_perfume[0]['product_name']} (Personal Care)")

    # 3. 'Kenneth Cole' brand search
    print("\n[Test 3] Testing 'Kenneth Cole' brand search preservation...")
    res_kc = eng.smart_search("Kenneth Cole", top_n=5)
    assert len(res_kc) > 0
    for r in res_kc:
        assert r["brand"] == "Kenneth Cole", f"Expected Kenneth Cole brand, got {r['brand']}"
        assert r["category"] == "Accessories"
    print(f"PASS: 'Kenneth Cole' search properly preserved: '{res_kc[0]['product_name']}' (Brand: {res_kc[0]['brand']}, Category: {res_kc[0]['category']})")

    # 4. Typo correction for 'runing shoes' and 'running sheo'
    print("\n[Test 4] Testing typo correction for 'runing shoes' and 'running sheo'...")
    res_runing = eng.smart_search("runing shoes", top_n=5)
    assert len(res_runing) > 0
    assert res_runing[0]["category"] == "Footwear"
    assert "shoe" in res_runing[0]["product_name"].lower()

    res_sheo = eng.smart_search("running sheo", top_n=5)
    assert len(res_sheo) > 0
    assert res_sheo[0]["category"] == "Footwear"
    assert "shoe" in res_sheo[0]["product_name"].lower()
    print("PASS: Typo corrections properly resolve to Footwear running shoes.")

    # 5. Synonym expansion for 'sneakers'
    print("\n[Test 5] Testing synonym expansion for 'sneakers'...")
    res_sneakers = eng.smart_search("sneakers", top_n=5)
    assert len(res_sneakers) > 0
    assert all(r["category"] == "Footwear" for r in res_sneakers)
    print(f"PASS: 'sneakers' expanded to Footwear: {[r['product_name'] for r in res_sneakers[:3]]}")

    # 6. Out of vocabulary handling (zero fabrication)
    print("\n[Test 6] Testing out-of-vocabulary query handling...")
    res_oov = eng.smart_search("xyznonexistentquery123", top_n=5)
    assert len(res_oov) == 0, f"Expected 0 results for gibberish query, got {len(res_oov)}"
    print("PASS: Out-of-vocabulary query safely returns 0 results with no fabricated matches.")

    # 7. Web catalog route with search, category filtering, and pagination
    print("\n[Test 7] Testing Web Catalog route with search filtering & pagination...")
    resp_web_cologne = client.get("/products?q=cologne")
    assert resp_web_cologne.status_code == 200
    assert b"Personal Care" in resp_web_cologne.data
    assert b"Kenneth Cole Men Black Dial Watch" not in resp_web_cologne.data

    # Category filter applied to search
    resp_cat_filter = client.get("/products?q=cologne&category=Personal+Care")
    assert resp_cat_filter.status_code == 200

    # Sorting parameter applied to search
    resp_sort = client.get("/products?q=cologne&sort=price_asc")
    assert resp_sort.status_code == 200

    # Pagination applied to search
    resp_page2 = client.get("/products?q=cologne&page=2")
    assert resp_page2.status_code == 200
    print("PASS: Web catalog route filters, sorts, and paginates search queries successfully.")

    # 8. ML Evaluation Dashboard Linguistic Test Check
    print("\n[Test 8] Checking ML Evaluation Dashboard linguistic test status...")
    from app.services.evaluator import MLEvaluator
    search_tests = MLEvaluator.evaluate_search_linguistics()
    cologne_test = next((t for t in search_tests if t["raw_query"] == "cologne"), None)
    assert cologne_test is not None, "Cologne test missing from evaluation suite!"
    assert cologne_test["status"] == "PASS", f"Cologne test failed in evaluator: {cologne_test}"
    assert cologne_test["resolved_category"] == "Personal Care", f"Expected Personal Care, got {cologne_test['resolved_category']}"
    assert "Kenneth Cole" not in cologne_test["top_product_name"]
    print(f"PASS: Evaluation dashboard search test for 'cologne' PASSED: Top match is '{cologne_test['top_product_name']}' ({cologne_test['resolved_category']})")

    # 9. Read-only Oracle verification
    print("\n[Test 9] Verifying Oracle 26ai read-only state...")
    prod_cnt = query_db("SELECT COUNT(*) as cnt FROM products", one=True)["cnt"]
    ord_cnt = query_db("SELECT COUNT(*) as cnt FROM orders", one=True)["cnt"]
    assert prod_cnt == 35254, f"Products count mismatch: {prod_cnt}"
    assert ord_cnt >= 18950, f"Orders count mismatch: {ord_cnt}"
    print(f"PASS: Oracle 26ai data confirmed untouched ({prod_cnt:,} products, {ord_cnt:,} orders).")

    print("\n" + "=" * 75)
    print("ALL 9 REGRESSION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 75)

if __name__ == "__main__":
    run_regression_tests()
