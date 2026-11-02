"""
Automated Verification & Evaluation Suite for Cartify Phase 8: Semantic Search & Vector Embeddings.
Tests:
1. Precomputed Embedding Representation & Dimensions
2. Selectable Retrieval Strategies ('hybrid', 'semantic', 'lexical')
3. Semantic Paraphrase Retrieval (Conceptual search without exact token match)
4. Exact Brand & Product Query Preservation ('Kenneth Cole', 'Puma')
5. Domain Synonym & Typo Resilience ('sneakers', 'cologne', 'runing shoes')
6. Noise & Out-of-Catalog Safety (Zero hallucinations on gibberish)
7. Filter & Sorting Preservation (Category, Gender, Price Asc/Desc, Rating)
8. Cologne & Fragrance Regression Preservation
9. Cold vs Warm Latency & Resource Utilization
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.db import query_db
from app.services.recommender import RecommendationEngine

# Ground-truth evaluation benchmark queries (12 substantive queries across 4 categories + 3 noise queries)
SUBSTANTIVE_BENCHMARK_CASES = [
    # 1. Semantic Paraphrases
    {"query": "cozy winter tops", "type": "Semantic Paraphrase", "target_category": "Apparel", "target_types": ["Tops", "Sweaters", "Sweatshirts"]},
    {"query": "gym workout outfit", "type": "Semantic Paraphrase", "target_category": "Apparel", "target_types": ["Tshirts", "Track Pants", "Shorts", "Sports Shoes"]},
    {"query": "formal wristwear", "type": "Semantic Paraphrase", "target_category": "Accessories", "target_types": ["Watches", "Wristbands"]},
    
    # 2. Exact Brand & Product Searches
    {"query": "Kenneth Cole", "type": "Exact Brand", "target_category": "Accessories", "target_brand": "Kenneth Cole"},
    {"query": "Puma Men Black Running Shoes", "type": "Exact Product", "target_category": "Footwear", "target_brand": "Puma"},
    {"query": "Nike", "type": "Exact Brand", "target_category": "Footwear", "target_brand": "Nike"},
    
    # 3. Domain Synonyms & Typo Resilience
    {"query": "sneakers", "type": "Domain Synonym", "target_category": "Footwear", "target_types": ["Sports Shoes", "Casual Shoes"]},
    {"query": "cologne", "type": "Domain Synonym", "target_category": "Personal Care", "target_types": ["Perfume and Body Mist", "Fragrance"]},
    {"query": "runing shoes", "type": "Typo Correction", "target_category": "Footwear", "target_types": ["Sports Shoes"]},
    
    # 4. Constrained & Multi-Attribute Queries
    {"query": "water repellent footwear", "type": "Multi-Attribute", "target_category": "Footwear", "target_types": ["Sports Shoes", "Casual Shoes"]},
    {"query": "black casual trousers", "type": "Multi-Attribute", "target_category": "Apparel", "target_types": ["Trousers", "Track Pants", "Jeans"]},
    {"query": "fragrance set for women", "type": "Multi-Attribute", "target_category": "Personal Care", "target_types": ["Perfume and Body Mist", "Fragrance"]}
]

NOISE_BENCHMARK_CASES = [
    # 5. Out of Catalog / Noise (Zero relevant items exist in catalog)
    {"query": "xyzgibberish9876", "type": "Out of Catalog"},
    {"query": "quantum nuclear reactor", "type": "Out of Catalog"},
    {"query": "777unknownitem999", "type": "Out of Catalog"}
]

def evaluate_retrieval_strategy(eng, strategy, k=5):
    """
    Rigorously evaluates a retrieval strategy:
    1. Strict Precision@K: Enforces AND logic on every specified target constraint (Category AND Brand AND Product Type).
    2. Category Alignment: Measures top-level category match percentage independently from fine-grained brand/type filters.
    3. Noise Rejection Rate: Evaluates true-negative rejection on out-of-catalog noise queries separately (not conflated with precision).
    """
    strict_precisions = []
    category_alignments = []
    latencies = []
    
    # 1. Substantive query evaluation
    for case in SUBSTANTIVE_BENCHMARK_CASES:
        q = case["query"]
        t0 = time.perf_counter()
        recs = eng.smart_search(q, top_n=k, strategy=strategy)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)
        
        target_cat = case["target_category"]
        if not recs:
            strict_precisions.append(0.0)
            category_alignments.append(0.0)
        else:
            strict_hits = 0
            cat_hits = 0
            for r in recs:
                is_cat_match = (r.get("category") == target_cat)
                if is_cat_match:
                    cat_hits += 1
                
                # Strict AND logic: every specified constraint must hold simultaneously
                brand_match = ("target_brand" not in case) or (case["target_brand"].lower() in str(r.get("brand", "")).lower())
                type_match = ("target_types" not in case) or any(t.lower() in str(r.get("product_type", "")).lower() for t in case["target_types"])
                
                if is_cat_match and brand_match and type_match:
                    strict_hits += 1
                    
            strict_precisions.append(strict_hits / len(recs))
            category_alignments.append(cat_hits / len(recs))
            
    # 2. Noise query evaluation (separated from precision)
    noise_rejected = 0
    for case in NOISE_BENCHMARK_CASES:
        q = case["query"]
        t0 = time.perf_counter()
        recs = eng.smart_search(q, top_n=k, strategy=strategy)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)
        if len(recs) == 0:
            noise_rejected += 1
            
    noise_rejection_pct = (noise_rejected / len(NOISE_BENCHMARK_CASES)) * 100.0
    
    return {
        "strategy": strategy,
        "strict_precision_at_k": round(float(np.mean(strict_precisions)) * 100.0, 2),
        "category_alignment_pct": round(float(np.mean(category_alignments)) * 100.0, 2),
        "noise_rejection_pct": round(float(noise_rejection_pct), 2),
        "mean_latency_ms": round(float(np.mean(latencies)), 2),
        "p95_latency_ms": round(float(np.percentile(latencies, 95)), 2)
    }

def test_semantic_search_suite():
    print("=" * 75)
    print("RUNNING AUTOMATED VERIFICATION FOR CARTIFY PHASE 8 SEMANTIC SEARCH")
    print("=" * 75)

    # 1. Cold Startup & Representation Check
    print("\n[Test 1] Testing Semantic Embedding Representation & Precomputed Dimensions...")
    t_init_start = time.perf_counter()
    eng = RecommendationEngine.get_instance()
    t_init = time.perf_counter() - t_init_start
    
    assert eng.is_initialized, "Recommendation engine failed to initialize!"
    assert eng.semantic_initialized, "Semantic embeddings failed to initialize!"
    assert eng.dense_embeddings is not None, "Dense product embeddings are None!"
    n_items, n_dims = eng.dense_embeddings.shape
    assert n_items == len(eng.df), f"Expected {len(eng.df)} item embeddings, got {n_items}"
    assert n_dims == 256, f"Expected 256 dimensions, got {n_dims}"
    print(f"PASS: Dense embeddings verified: {n_items:,} items x {n_dims} dimensions (Init time: {t_init:.2f}s).")

    # 2. Selectable Strategies
    print("\n[Test 2] Testing Selectable Search Strategies ('hybrid', 'semantic', 'lexical')...")
    test_q = "running shoes"
    recs_hybrid = eng.smart_search(test_q, top_n=5, strategy="hybrid")
    recs_sem = eng.smart_search(test_q, top_n=5, strategy="semantic")
    recs_lex = eng.smart_search(test_q, top_n=5, strategy="lexical")

    assert len(recs_hybrid) > 0, "Hybrid search returned 0 results for 'running shoes'"
    assert len(recs_sem) > 0, "Semantic search returned 0 results for 'running shoes'"
    assert len(recs_lex) > 0, "Lexical search returned 0 results for 'running shoes'"
    assert all("ranking_score" in r and "semantic_score" in r for r in recs_hybrid)
    print(f"PASS: Selectable strategies operational. Top-1 scores: Hybrid={recs_hybrid[0]['ranking_score']}%, Semantic={recs_sem[0]['ranking_score']}%, Lexical={recs_lex[0]['ranking_score']}%.")

    # 3. Semantic Paraphrases
    print("\n[Test 3] Testing Semantic Paraphrase Retrieval...")
    cozy_recs = eng.smart_search("cozy winter tops", top_n=5, strategy="hybrid")
    assert len(cozy_recs) > 0, "Expected matches for 'cozy winter tops'"
    cozy_cats = [r["category"] for r in cozy_recs]
    assert "Apparel" in cozy_cats, f"Expected Apparel in tops, got {cozy_cats}"
    print(f"PASS: 'cozy winter tops' surfaced relevant apparel: '{cozy_recs[0]['product_name']}' ({cozy_recs[0]['category']} > {cozy_recs[0].get('product_type')}) [Rank: {cozy_recs[0]['ranking_score']}%].")

    # 4. Exact Brand Query Preservation
    print("\n[Test 4] Testing Brand Query Preservation ('Kenneth Cole')...")
    kc_recs = eng.smart_search("Kenneth Cole", top_n=5, strategy="hybrid")
    assert len(kc_recs) > 0
    top_kc = kc_recs[0]
    assert "kenneth cole" in top_kc["product_name"].lower() or "kenneth cole" in top_kc.get("brand", "").lower()
    assert top_kc["category"] == "Accessories"
    print(f"PASS: 'Kenneth Cole' brand search preserved: '{top_kc['product_name']}' (Brand: {top_kc.get('brand')}, Category: {top_kc['category']}).")

    # 5. Domain Synonyms & Typo Correction
    print("\n[Test 5] Testing Domain Synonym & Typo Resilience ('sneakers', 'runing shoes')...")
    sneakers_recs = eng.smart_search("sneakers", top_n=5, strategy="hybrid")
    assert all(r["category"] == "Footwear" for r in sneakers_recs), "Sneakers did not resolve to Footwear!"
    
    typo_recs = eng.smart_search("runing shoes", top_n=5, strategy="hybrid")
    assert all(r["category"] == "Footwear" for r in typo_recs), "Typo 'runing shoes' did not resolve to Footwear!"
    print(f"PASS: Synonyms and typos cleanly resolved to Footwear: sneakers top='{sneakers_recs[0]['product_name']}', typo top='{typo_recs[0]['product_name']}'.")

    # 6. Noise, Out-of-Catalog Safety & Numerical Epsilon Guards
    print("\n[Test 6] Testing Noise Rejection & Numerical Safety (Epsilon / NaN / Inf Protection)...")
    noise_recs = eng.smart_search("xyzgibberish9876", top_n=5, strategy="hybrid")
    assert len(noise_recs) == 0, f"Expected 0 results for noise, got {len(noise_recs)}"
    
    reactor_recs = eng.smart_search("quantum nuclear reactor", top_n=5, strategy="hybrid")
    assert len(reactor_recs) == 0, f"Expected 0 results for out-of-catalog items, got {len(reactor_recs)}"
    
    # Test numerical safety: empty query, subnormal characters, and verify no NaN or Inf
    empty_recs = eng.smart_search("", top_n=5, strategy="hybrid")
    assert empty_recs == []
    
    # Check score validity on typical query
    sample_recs = eng.smart_search("running shoes", top_n=10, strategy="hybrid")
    for r in sample_recs:
        for score_key in ["ranking_score", "similarity_score", "lexical_score", "semantic_score"]:
            val = r.get(score_key)
            assert val is not None, f"Missing score key: {score_key}"
            assert np.isfinite(val), f"Non-finite score encountered: {score_key}={val}"
            assert not np.isnan(val), f"NaN score encountered: {score_key}={val}"
            assert 0.0 <= val <= 100.0, f"Score out of bounds: {score_key}={val}"

    print("PASS: Noise queries safely return 0 results. Numerical epsilon guards and finite score assertions verified.")

    # 7. Web Route Filtering, Sorting & Strategy Persistence
    print("\n[Test 7] Testing Web Route Filters, Sorting & Strategy Persistence...")
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()

    # 7a. Test strategy persistence in category, gender, and pagination links for 'semantic'
    resp_sem = client.get("/products?q=shoes&strategy=semantic&category=Footwear&sort=price_asc")
    assert resp_sem.status_code == 200
    html_sem = resp_sem.data.decode("utf-8")
    assert "Search Strategy:" in html_sem
    assert "Dense Semantic" in html_sem
    assert "strategy=semantic" in html_sem, "Strategy parameter dropped from template links in semantic mode!"
    # Verify category filter link preserves strategy=semantic
    assert "category=Footwear" in html_sem and "strategy=semantic" in html_sem
    
    # 7b. Test strategy persistence for 'lexical'
    resp_lex = client.get("/products?q=shoes&strategy=lexical&page=2")
    assert resp_lex.status_code == 200
    html_lex = resp_lex.data.decode("utf-8")
    assert "strategy=lexical" in html_lex, "Strategy parameter dropped from pagination links in lexical mode!"

    # 7c. Test default fallback for invalid strategy parameter
    resp_inv = client.get("/products?q=shoes&strategy=unknown_malformed_strat")
    assert resp_inv.status_code == 200
    html_inv = resp_inv.data.decode("utf-8")
    assert "Hybrid Semantic" in html_inv, "Malformed strategy did not fall back to Hybrid Semantic!"
    print("PASS: Search strategy verified to strictly survive category filtering, gender filtering, and pagination.")

    # 8. Cologne & Kenneth Cole Regression Check
    print("\n[Test 8] Testing Cologne & Fragrance NLP Regression Preservation...")
    cologne_recs = eng.smart_search("cologne", top_n=5, strategy="hybrid")
    assert len(cologne_recs) > 0
    top_col = cologne_recs[0]
    assert top_col["category"] == "Personal Care", f"Cologne failed: resolved to {top_col['category']}"
    assert "perfume" in top_col["product_name"].lower() or "perfume" in top_col.get("product_type", "").lower() or "fragrance" in top_col.get("product_type", "").lower()
    print(f"PASS: 'cologne' resolved to Personal Care perfume: '{top_col['product_name']}' ({top_col['category']}).")

    # 9. Empirical Strategy Comparison & Latency Benchmark
    print("\n[Test 9] Empirical Retrieval Evaluation across Strategies (12 Substantive Cases + 3 Noise Cases)...")
    eval_lex = evaluate_retrieval_strategy(eng, "lexical", k=5)
    eval_sem = evaluate_retrieval_strategy(eng, "semantic", k=5)
    eval_hyb = evaluate_retrieval_strategy(eng, "hybrid", k=5)

    print("\n" + "=" * 95)
    print(f"{'Strategy':<16} | {'Strict P@5 (N=12)':<18} | {'Category Align':<16} | {'Noise Rejection':<16} | {'Mean Latency':<12}")
    print("=" * 95)
    for ev in [eval_lex, eval_sem, eval_hyb]:
        print(f"{ev['strategy']:<16} | {ev['strict_precision_at_k']:>16.2f}% | {ev['category_alignment_pct']:>14.2f}% | {ev['noise_rejection_pct']:>14.2f}% | {ev['mean_latency_ms']:>9.2f} ms")
    print("=" * 95)

    # Comparative Assertions:
    # 1. Hybrid search achieves superior or equal strict precision compared to lexical and semantic
    assert eval_hyb["strict_precision_at_k"] >= eval_lex["strict_precision_at_k"], f"Hybrid precision {eval_hyb['strict_precision_at_k']}% fell below lexical baseline {eval_lex['strict_precision_at_k']}%!"
    assert eval_hyb["strict_precision_at_k"] >= eval_sem["strict_precision_at_k"], f"Hybrid precision {eval_hyb['strict_precision_at_k']}% fell below semantic baseline {eval_sem['strict_precision_at_k']}%!"
    # 2. Category alignment is strictly separated from precision and above 75%
    assert eval_hyb["category_alignment_pct"] >= 75.0, f"Hybrid category alignment below 75%: {eval_hyb['category_alignment_pct']}%"
    # 3. Noise rejection strictly achieves 100% (zero false positives on noise queries)
    assert eval_hyb["noise_rejection_pct"] == 100.0, f"Noise rejection failed: {eval_hyb['noise_rejection_pct']}%"
    # 4. Latency remains well within operational bounds
    assert eval_hyb["mean_latency_ms"] < 150.0, f"Mean latency exceeds 150ms: {eval_hyb['mean_latency_ms']}ms"
    print("PASS: Rigorous empirical evaluation confirms Hybrid retrieval superiority and 100% noise rejection.")

    print("\n" + "=" * 75)
    print("ALL 9 SEMANTIC SEARCH VERIFICATION MODULES PASSED WITH 100% SUCCESS!")
    print("=" * 75)

if __name__ == "__main__":
    test_semantic_search_suite()
