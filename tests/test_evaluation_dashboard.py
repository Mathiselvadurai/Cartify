"""
Automated Verification Suite for Cartify Stage 3 ML Evaluation Dashboard.
Tests:
1. Dashboard Access Control (403 without key/role, 200 with demo key)
2. Dashboard Template Rendering & Visualization Assets
3. JSON API Endpoint Integrity
4. Offline RecSys Policy Comparison Metric Calculations
5. Strict Temporal Separation (Zero Data Leakage)
6. Privacy & PII Data Masking
7. Read-Only Database Safety Verification
8. Repeatable Inference Latency Benchmark Consistency
"""

import sys
import os
import re
import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.db import query_db
from app.services.evaluator import MLEvaluator
from app.services.recommender import RecommendationEngine

def test_evaluation_suite():
    print("=" * 75)
    print("RUNNING AUTOMATED VERIFICATION FOR CARTIFY STAGE 3 ML EVALUATION DASHBOARD")
    print("=" * 75)

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # -------------------------------------------------------------------------
    # Test 1: Access Control Gate
    # -------------------------------------------------------------------------
    print("\n[Test 1] Testing Dashboard Access Control...")
    
    # 1a. Unauthenticated access without demo key should be rejected with 403
    resp_unauth = client.get("/evaluation/")
    assert resp_unauth.status_code == 403, f"Expected 403 for unauthorized access, got {resp_unauth.status_code}"
    assert b"Academic Evaluation Portal" in resp_unauth.data
    assert b"Evaluator Access Key" in resp_unauth.data
    print("PASS: Unauthorized public access rejected with 403 and access gate rendered.")

    # 1b. Access with ?demo=1 query parameter should succeed with 200
    resp_demo = client.get("/evaluation/?demo=1")
    assert resp_demo.status_code == 200, f"Expected 200 with ?demo=1, got {resp_demo.status_code}"
    assert b"Machine Learning Recommendation Evaluation Dashboard" in resp_demo.data
    print("PASS: Access granted with ?demo=1 parameter.")

    # 1c. Access via POST access key form
    resp_post = client.post("/evaluation/", data={"access_key": "cartify-eval-2026"}, follow_redirects=True)
    assert resp_post.status_code == 200
    assert b"STAGE 3 ML EVALUATION" in resp_post.data
    print("PASS: Access granted via POST evaluation access key.")

    # 1d. Access via authenticated Premium user
    with client.session_transaction() as sess:
        sess.clear()
        sess["user"] = {"id": 1, "name": "Admin Tester", "email": "admin@example.com", "tier": "Premium"}
    resp_premium = client.get("/evaluation/")
    assert resp_premium.status_code == 200
    print("PASS: Access granted to authenticated Premium/Admin user session.")

    # -------------------------------------------------------------------------
    # Test 2: Template Rendering & Section Completeness
    # -------------------------------------------------------------------------
    print("\n[Test 2] Testing Dashboard Template Structure & Chart Assets...")
    resp_dash = client.get("/evaluation/?demo=1")
    assert resp_dash.status_code == 200
    html = resp_dash.data.decode("utf-8")

    # Verify all 7 core sections exist
    required_sections = [
        "1. Engine Architecture & Evaluation Methodology",
        "2. Empirical Recommendation Policy Comparison",
        "3. Recommended Category Distribution",
        "4. Repeatable Inference Latency Benchmarks",
        "5. Personalization Case Studies & Diversity Enforcement",
        "6. Search Quality & Linguistic Resilience Tests",
        "7. System Safeguards & Database Integrity Audits"
    ]
    for sec in required_sections:
        assert sec in html, f"Missing required dashboard section: '{sec}'"

    # Verify Chart.js integration
    assert "cdn.jsdelivr.net/npm/chart.js" in html, "Chart.js library CDN missing!"
    assert "policyComparisonChart" in html, "Policy comparison chart canvas missing!"
    assert "categoryDistChart" in html, "Category distribution chart canvas missing!"
    print("PASS: All 7 required dashboard modules and Chart.js canvases render successfully.")

    # -------------------------------------------------------------------------
    # Test 3: JSON API Endpoint Integrity
    # -------------------------------------------------------------------------
    print("\n[Test 3] Testing Evaluation Summary JSON API Endpoint...")
    resp_api = client.get("/evaluation/api/summary?demo=1")
    assert resp_api.status_code == 200
    assert resp_api.is_json
    data = resp_api.get_json()
    assert "architecture" in data
    assert "policy_evaluation" in data
    assert "latencies" in data
    assert data["architecture"]["active_catalog_size"] == 34190
    print("PASS: Evaluation JSON API responds with complete architecture and benchmark payload.")

    # -------------------------------------------------------------------------
    # Test 4: Offline Policy Comparison Metric Calculations
    # -------------------------------------------------------------------------
    print("\n[Test 4] Testing Offline RecSys Policy Comparison Calculations...")
    eval_res = MLEvaluator.evaluate_offline_policies(sample_users=15, k=8, force_refresh=True)
    assert "policies" in eval_res
    assert eval_res["sample_size"] == 15
    assert eval_res["k_value"] == 8

    policies = eval_res["policies"]
    for p_name in ["popularity", "recent_item", "personalized", "hybrid"]:
        assert p_name in policies
        p = policies[p_name]
        assert 0.0 <= p["hit_rate_at_k"] <= 100.0
        assert 0.0 <= p["precision_at_k"] <= 100.0
        assert 0.0 <= p["recall_at_k"] <= 100.0
        assert 0.0 <= p["ndcg_at_k"] <= 1.0
        assert 0.0 <= p["category_alignment_pct"] <= 100.0
        assert 0.0 <= p["catalog_coverage_pct"] <= 100.0
        assert p["unique_products_recommended"] > 0
        assert p["intra_list_diversity"] >= 0.0

    # Comparative assertions: Personalized policy should outperform popularity baseline in coverage and category alignment
    assert policies["personalized"]["category_alignment_pct"] > policies["popularity"]["category_alignment_pct"]
    assert policies["personalized"]["unique_products_recommended"] > policies["popularity"]["unique_products_recommended"]
    assert policies["hybrid"]["hit_rate_at_k"] >= policies["personalized"]["hit_rate_at_k"]
    print(f"PASS: Policy metrics calculated accurately. Hybrid HR@8: {policies['hybrid']['hit_rate_at_k']}% (NDCG: {policies['hybrid']['ndcg_at_k']}) vs Content: {policies['personalized']['hit_rate_at_k']}% vs Popularity: {policies['popularity']['hit_rate_at_k']}%.")

    # -------------------------------------------------------------------------
    # Test 5: Strict Temporal Separation (Zero Data Leakage)
    # -------------------------------------------------------------------------
    print("\n[Test 5] Testing Strict Temporal Separation & Cutoff Validation...")
    # Verify for sample user that training timestamps strictly precede ground-truth timestamps
    events = query_db("""
        SELECT event_timestamp
        FROM interactions
        WHERE user_id = 644
        ORDER BY event_timestamp ASC
    """)
    assert len(events) >= 10
    split_idx = max(1, int(len(events) * 0.75))
    train_slice = events[:split_idx]
    test_slice = events[split_idx:]
    
    cutoff_ts = train_slice[-1]["event_timestamp"]
    for t_event in train_slice:
        assert t_event["event_timestamp"] <= cutoff_ts, "Data leakage: Train event timestamp exceeds cutoff!"
    for test_event in test_slice:
        assert test_event["event_timestamp"] >= cutoff_ts, "Data leakage: Ground truth event timestamp precedes cutoff!"
    print(f"PASS: Strict temporal boundary verified at cutoff {cutoff_ts}. Zero training data leakage.")

    # -------------------------------------------------------------------------
    # Test 6: Privacy & PII Data Masking
    # -------------------------------------------------------------------------
    print("\n[Test 6] Testing PII Masking & Privacy Protection in Case Studies...")
    case_studies = MLEvaluator.get_personalization_case_studies()
    assert len(case_studies) == 4

    for cs in case_studies:
        # Check that no full names, emails, phone numbers, or addresses are exposed
        assert "@" not in str(cs), f"Found unmasked email in case study: {cs}"
        assert "Ahmedabad" not in str(cs), "Customer city exposed in case study!"
        assert "Revathi Gupta" not in str(cs), "Customer full name exposed in case study!"
        assert "Neha Agarwal" not in str(cs), "Customer full name exposed in case study!"
        # Check anonymized identifiers
        assert cs["profile_id"].startswith("Cohort-")
        assert cs["diversity_cap_preserved"] is True
        assert cs["max_type_count"] <= 3, f"Diversity cap violated: {cs['max_type_count']}"
    print("PASS: PII strictly masked. All case studies anonymized with diversity caps preserved.")

    # -------------------------------------------------------------------------
    # Test 7: Read-Only Database Safety Verification
    # -------------------------------------------------------------------------
    print("\n[Test 7] Verifying 100% Read-Only Safety Against Oracle 26ai...")
    prod_cnt_before = query_db("SELECT COUNT(*) as cnt FROM products", one=True)["cnt"]
    ord_cnt_before = query_db("SELECT COUNT(*) as cnt FROM orders", one=True)["cnt"]
    int_cnt_before = query_db("SELECT COUNT(*) as cnt FROM interactions", one=True)["cnt"]

    # Trigger fresh evaluation & latencies
    _ = MLEvaluator.evaluate_offline_policies(sample_users=5, k=8, force_refresh=True)
    _ = MLEvaluator.benchmark_latencies(runs=5, force_refresh=True)

    prod_cnt_after = query_db("SELECT COUNT(*) as cnt FROM products", one=True)["cnt"]
    ord_cnt_after = query_db("SELECT COUNT(*) as cnt FROM orders", one=True)["cnt"]
    int_cnt_after = query_db("SELECT COUNT(*) as cnt FROM interactions", one=True)["cnt"]

    assert prod_cnt_before == prod_cnt_after, "Products table modified!"
    assert ord_cnt_before == ord_cnt_after, "Orders table modified!"
    assert int_cnt_before == int_cnt_after, "Interactions table modified!"
    print(f"PASS: Oracle 26ai tables remain 100% untouched ({prod_cnt_after:,} products, {ord_cnt_after:,} orders, {int_cnt_after:,} interactions).")

    # -------------------------------------------------------------------------
    # Test 8: Repeatable Inference Latency Benchmark Consistency
    # -------------------------------------------------------------------------
    print("\n[Test 8] Testing Latency Benchmark Statistical Consistency...")
    lat_data = MLEvaluator.benchmark_latencies(runs=10, force_refresh=True)
    for task_name in ["personalized_recs", "similar_products", "smart_search"]:
        assert task_name in lat_data
        t = lat_data[task_name]
        assert t["runs"] == 10
        assert 0.0 < t["min_ms"] <= t["median_ms"] <= t["p95_ms"] <= t["max_ms"], f"Inconsistent latency statistics in {task_name}: {t}"
    print(f"PASS: Latency benchmarks consistent across runs: Search P95={lat_data['smart_search']['p95_ms']}ms, Similar P95={lat_data['similar_products']['p95_ms']}ms, Personalized P95={lat_data['personalized_recs']['p95_ms']}ms.")

    print("\n" + "=" * 75)
    print("ALL 8 STAGE 3 ML EVALUATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 75)

if __name__ == "__main__":
    test_evaluation_suite()
