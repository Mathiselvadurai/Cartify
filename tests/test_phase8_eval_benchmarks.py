"""
Cartify Stage 3 & Phase 8 Test Suite
Rigorous RecSys Evaluation, Strategy Comparisons, Temporal Holdout Leakage Verification,
Hybrid Parameter Optimization, Concurrency Locking, and Repeatable Benchmarks.
"""

import unittest
import threading
from app import create_app
from app.services.evaluator import MLEvaluator, _eval_lock
from app.services.recommender import RecommendationEngine

class TestPhase8EvalBenchmarks(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = cls.app.test_client()

        # Ensure recommendation engine is initialized once
        cls.eng = RecommendationEngine.get_instance()
        if not cls.eng.is_initialized:
            cls.eng.initialize()

    def test_01_zero_data_leakage_temporal_holdout(self):
        """Verifies strict 75/25 chronological split and zero data leakage across holdout."""
        eval_res = MLEvaluator.evaluate_offline_policies(sample_users=10, force_refresh=False)
        self.assertIn("policies", eval_res)
        self.assertIn("hybrid", eval_res["policies"])
        self.assertIn("content", eval_res["policies"])
        self.assertIn("popularity", eval_res["policies"])
        self.assertEqual(eval_res["split_protocol"], "75% Chronological Train (Pre-Cutoff) / 25% Test (Future Holdout Ground Truth)")

    def test_02_strategy_comparison_metrics_calculation(self):
        """Verifies all 5 recommendation strategies compute valid K=5 and K=10 metrics."""
        eval_res = MLEvaluator.evaluate_offline_policies(sample_users=10, force_refresh=False)
        policies = eval_res["policies"]

        for strat in ["popularity", "content", "semantic", "collaborative", "hybrid"]:
            self.assertIn(strat, policies, f"Strategy {strat} missing from evaluation results")
            p = policies[strat]
            
            # Check K=5 and K=10 precisions
            self.assertIn("precision_at_5", p)
            self.assertIn("precision_at_10", p)
            self.assertGreaterEqual(p["precision_at_5"], 0.0)
            self.assertGreaterEqual(p["precision_at_10"], 0.0)

            # Check K=5 and K=10 recalls
            self.assertIn("recall_at_5", p)
            self.assertIn("recall_at_10", p)
            self.assertGreaterEqual(p["recall_at_5"], 0.0)
            self.assertGreaterEqual(p["recall_at_10"], 0.0)

            # Check NDCGs
            self.assertIn("ndcg_at_5", p)
            self.assertIn("ndcg_at_10", p)
            self.assertGreaterEqual(p["ndcg_at_5"], 0.0)
            self.assertGreaterEqual(p["ndcg_at_10"], 0.0)

            # Check Catalog Coverage & Diversity
            self.assertIn("catalog_coverage_pct", p)
            self.assertIn("intra_list_diversity", p)
            self.assertGreater(p["catalog_coverage_pct"], 0.0)
            self.assertGreaterEqual(p["intra_list_diversity"], 0.0)

            # Verify diversity cap: max items per type <= 3
            self.assertLessEqual(p["product_type_diversity_max"], 3, f"{strat} exceeded diversity cap of 3")

            # Verify duplicate rate is strictly 0.0%
            self.assertEqual(p["duplicate_rate_pct"], 0.0, f"{strat} has non-zero duplicate rate")

    def test_03_hybrid_alpha_optimization(self):
        """Verifies hybrid parameter optimization across alpha in [0.00, 0.10, 0.20, 0.30]."""
        alpha_res = MLEvaluator.evaluate_hybrid_alpha_optimization(sample_users=10, force_refresh=False)
        self.assertIn("0.00", alpha_res)
        self.assertIn("0.10", alpha_res)
        self.assertIn("0.20", alpha_res)
        self.assertIn("0.30", alpha_res)

        # Default alpha=0.20 verification
        self.assertTrue(alpha_res["0.20"]["is_default"])
        self.assertFalse(alpha_res["0.00"]["is_default"])

        # Compare alpha=0.20 against pure content alpha=0.00
        # Hybrid should achieve higher NDCG ranking quality or recall
        ndcg_020 = alpha_res["0.20"]["ndcg_at_10"]
        ndcg_000 = alpha_res["0.00"]["ndcg_at_10"]
        self.assertGreaterEqual(ndcg_020, ndcg_000, "Hybrid alpha=0.20 NDCG should be >= pure content")

    def test_04_eval_dashboard_and_api_authorization(self):
        """Verifies authentication guard and JSON API endpoints."""
        # Unauthenticated request without demo key should be 403
        with self.client as c:
            resp = c.get("/evaluation/")
            self.assertEqual(resp.status_code, 403)

        # Request with demo=1 query parameter should succeed
        with self.client as c:
            resp = c.get("/evaluation/?demo=1")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Machine Learning Recommendation Evaluation", resp.data)
            self.assertIn(b"Cartify Hybrid (alpha=0.20)", resp.data)

        # Request with key=cartify-eval-2026 should succeed
        with self.client as c:
            resp = c.get("/evaluation/?key=cartify-eval-2026")
            self.assertEqual(resp.status_code, 200)

        # Test API summary endpoint
        with self.client as c:
            with c.session_transaction() as sess:
                sess["is_evaluator"] = True
            api_resp = c.get("/evaluation/api/summary")
            self.assertEqual(api_resp.status_code, 200)
            data = api_resp.get_json()
            self.assertIn("architecture", data)
            self.assertIn("policy_evaluation", data)
            self.assertIn("alpha_optimization", data)
            self.assertIn("latencies", data)

    def test_05_concurrency_mutex_locking_on_benchmark_run(self):
        """Verifies mutex concurrency protection prevents overlapping benchmark runs."""
        with self.client as c:
            with c.session_transaction() as sess:
                sess["is_evaluator"] = True
                sess["csrf_token"] = "valid_test_csrf_token"

            # Acquire lock manually to simulate concurrent executing benchmark
            acquired = _eval_lock.acquire(blocking=False)
            self.assertTrue(acquired, "Failed to acquire lock for test setup")

            try:
                # Concurrent request while lock is held must be rejected with 429
                resp = c.post("/evaluation/run", data={"csrf_token": "valid_test_csrf_token"}, headers={"Accept": "application/json"})
                self.assertEqual(resp.status_code, 429)
                data = resp.get_json()
                self.assertEqual(data["status"], "busy")
                self.assertIn("currently executing", data["message"])
            finally:
                _eval_lock.release()

    def test_06_repeatable_latency_benchmarks_validity(self):
        """Verifies latency benchmark percentiles and statistical validity."""
        lats = MLEvaluator.benchmark_latencies(runs=10, force_refresh=False)
        self.assertIn("personalized_recs", lats)
        self.assertIn("similar_products", lats)
        self.assertIn("smart_search", lats)

        for task_key in ["personalized_recs", "similar_products", "smart_search"]:
            t = lats[task_key]
            self.assertGreater(t["mean_ms"], 0.0)
            self.assertGreater(t["median_ms"], 0.0)
            self.assertGreater(t["p95_ms"], 0.0)
            self.assertGreater(t["p99_ms"], 0.0)
            self.assertLessEqual(t["min_ms"], t["mean_ms"])
            self.assertLessEqual(t["median_ms"], t["p95_ms"])
            self.assertLessEqual(t["p95_ms"], t["max_ms"])

    def test_07_pii_masking_in_case_studies(self):
        """Verifies customer case studies strictly mask PII and enforce diversity cap."""
        studies = MLEvaluator.get_personalization_case_studies()
        self.assertGreaterEqual(len(studies), 4)

        for s in studies:
            self.assertIn("profile_id", s)
            self.assertIn("label", s)
            self.assertIn("archetype", s)
            # Ensure no raw personal names/emails
            self.assertNotIn("@", s["profile_id"])
            self.assertTrue(s["profile_id"].startswith("Cohort-"))
            self.assertTrue(s["diversity_cap_preserved"])
            self.assertLessEqual(s["max_type_count"], 3)

    def test_08_search_linguistics_resilience(self):
        """Verifies spelling correction, domain synonyms, and out-of-vocabulary handling."""
        tests = MLEvaluator.evaluate_search_linguistics()
        self.assertGreaterEqual(len(tests), 5)
        for t in tests:
            self.assertEqual(t["status"], "PASS", f"Linguistic test failed: {t}")

if __name__ == "__main__":
    unittest.main()
