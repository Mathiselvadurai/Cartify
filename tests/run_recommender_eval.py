import sys
import os
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import query_db
from app.services.recommender import RecommendationEngine

def evaluate():
    print("=" * 80)
    print("EVALUATING CARTIFY RECOMMENDATION ENGINE (TF-IDF + COSINE SIMILARITY)")
    print("=" * 80)

    engine = RecommendationEngine.get_instance()

    # 10 Diverse Test Products across Categories and Product Types
    test_products = [
        # 1. Footwear: Sports Shoes
        1571,
        # 2. Footwear: Formal Shoes
        query_db("SELECT product_id FROM products WHERE category = 'Footwear' AND product_type = 'Formal Shoes' AND is_active = 1 FETCH FIRST 1 ROW ONLY", one=True)["product_id"],
        # 3. Footwear: Flip Flops
        query_db("SELECT product_id FROM products WHERE category = 'Footwear' AND product_type = 'Flip Flops' AND is_active = 1 FETCH FIRST 1 ROW ONLY", one=True)["product_id"],
        # 4. Apparel: Men's Checked Shirt
        2134,
        # 5. Apparel: Bottomwear / Shorts
        22590,
        # 6. Apparel: Women's Dress
        37198,
        # 7. Accessories: Chronograph Watch
        46309,
        # 8. Accessories: Wallet (Short Description)
        32606,
        # 9. Personal Care: Fragrance Gift Set
        41906,
        # 10. Personal Care: Lip Color / Makeup
        56058
    ]

    results = []

    for idx, pid in enumerate(test_products, 1):
        source = query_db("""
            SELECT product_id, product_name, brand, category, subcategory, product_type, gender,
                   LENGTH(product_description) as desc_len, product_description, search_keywords
            FROM products WHERE product_id = :1
        """, (pid,), one=True)

        recommendations = engine.get_similar_products(pid, top_n=5)

        # Integrity checks
        rec_ids = [r["product_id"] for r in recommendations]
        is_self_excluded = pid not in rec_ids
        is_unique = len(rec_ids) == len(set(rec_ids))
        same_category_count = sum(1 for r in recommendations if r.get("category") == source["category"])
        category_relevance = f"{same_category_count}/5 match source category ({source['category']})"

        res_entry = {
            "test_num": idx,
            "source": source,
            "recommendations": recommendations,
            "checks": {
                "self_excluded": is_self_excluded,
                "all_unique": is_unique,
                "same_category_ratio": same_category_count / len(recommendations) if recommendations else 0
            }
        }
        results.append(res_entry)

        print(f"\n[{idx}/10] SOURCE: ID {source['product_id']} | {source['product_name']}")
        print(f"      Category: {source['category']} > {source['subcategory']} > {source['product_type']} | Brand: {source['brand']} | Desc Len: {source['desc_len']}")
        print(f"      Checks: Self-Excluded={is_self_excluded}, Unique={is_unique}, Category Match={same_category_count}/5")
        print("      Top 5 Recommended Products:")
        for r_rank, r in enumerate(recommendations, 1):
            score = r.get("similarity_score", 0)
            print(f"        {r_rank}. [ID {r['product_id']}] {r['product_name']}")
            print(f"           Cat: {r.get('category')} > {r.get('product_type')} | Brand: {r.get('brand')} | Score: {score}%")

    print("\n" + "=" * 80)
    print("EDGE CASE 1: Inactive Product as Target")
    print("=" * 80)
    inactive_p = query_db("SELECT product_id, product_name, is_active FROM products WHERE is_active = 0 FETCH FIRST 1 ROW ONLY", one=True)
    if inactive_p:
        in_pid = inactive_p["product_id"]
        in_recs = engine.get_similar_products(in_pid, top_n=5)
        print(f"Target is Inactive Product ID {in_pid} ('{inactive_p['product_name']}'):")
        print(f"Number of recommendations returned: {len(in_recs)}")
        print(f"Are recommended products active? {[r.get('is_active', 1) for r in in_recs]}")
        print(f"Fallback triggered? {in_pid not in engine.id_to_idx}")

    print("\n" + "=" * 80)
    print("EDGE CASE 2: Non-existent Product ID (e.g. ID 999999)")
    print("=" * 80)
    non_rec = engine.get_similar_products(999999, top_n=5)
    print(f"Recommendations for non-existent ID 999999: {len(non_rec)} items returned (Cold-start popular fallback)")

    print("\n" + "=" * 80)
    print("SEARCH EVALUATION (smart_search vs similar_products)")
    print("=" * 80)
    test_queries = [
        "running shoes",
        "red dress for women",
        "analog watch",
        "perfume gift set",
        "xyznonexistentquery123"
    ]
    for q in test_queries:
        s_res = engine.smart_search(q, top_n=3)
        print(f"\nQuery: '{q}' -> {len(s_res)} results returned")
        for sr in s_res:
            print(f" - [Score: {sr['similarity_score']}%] ID {sr['product_id']}: {sr['product_name']} ({sr.get('category')})")

    # Save detailed evaluation JSON
    with open("tests/eval_report.json", "w") as f:
        # Convert non-serializable objects
        def json_serial(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)
        json.dump(results, f, indent=2, default=json_serial)
    print("\nFull evaluation report saved to tests/eval_report.json")

if __name__ == "__main__":
    evaluate()
