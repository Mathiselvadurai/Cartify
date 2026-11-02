import sys
import math
import numpy as np
from collections import defaultdict, Counter
sys.path.insert(0, ".")
from app.db import query_db
from app.services.recommender import RecommendationEngine

eng = RecommendationEngine.get_instance()

EVENT_BASE_WEIGHTS = {
    "purchase": 5.0,
    "add_to_cart": 3.0,
    "wishlist": 2.0,
    "click": 1.2,
    "view": 1.0
}

def simulate_improved_personalization(user_id, limit=8, max_per_type=3):
    if not user_id:
        return eng.get_popular_products(limit=limit)

    # 1. Fetch user's interactions (all available or up to 200)
    interactions = query_db("""
        SELECT product_id, event_type
        FROM interactions
        WHERE user_id = :1
        ORDER BY event_timestamp DESC
        FETCH FIRST 200 ROWS ONLY
    """, (user_id,))

    # 2. Fetch all completed purchases
    purchased_rows = query_db("""
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.user_id = :1
    """, (user_id,))
    purchased_ids = {r["product_id"] for r in purchased_rows}

    if not interactions and not purchased_ids:
        return eng.get_popular_products(limit=limit)

    # 3. Intent-Bounded Product Weighting:
    # Base weight = highest intent achieved (purchase 5.0 > cart 3.0 > wishlist 2.0 > click 1.2 > view 1.0)
    # Plus sublinear bonus for frequency: 0.15 * log(1 + count)
    product_highest_intent = defaultdict(lambda: "view")
    product_event_counts = defaultdict(int)

    intent_priority = {"purchase": 5, "add_to_cart": 4, "wishlist": 3, "click": 2, "view": 1}

    for row in interactions:
        pid = row["product_id"]
        etype = (row.get("event_type") or "view").lower()
        product_event_counts[pid] += 1
        if intent_priority.get(etype, 1) > intent_priority.get(product_highest_intent[pid], 1):
            product_highest_intent[pid] = etype
        if etype == "purchase":
            purchased_ids.add(pid)

    for pid in purchased_ids:
        product_highest_intent[pid] = "purchase"

    item_weights = {}
    user_categories = Counter()
    user_types = Counter()

    for pid, intent in product_highest_intent.items():
        base = EVENT_BASE_WEIGHTS.get(intent, 1.0)
        cnt = product_event_counts[pid]
        # Frequency bonus is capped so views can NEVER exceed a purchase
        freq_bonus = 0.15 * math.log(1 + cnt)
        final_weight = base + freq_bonus
        item_weights[pid] = final_weight

    # 4. Construct User Profile Vector
    user_vector = np.zeros(eng.tfidf_matrix.shape[1], dtype=np.float64)
    valid_items = 0

    for pid, weight in item_weights.items():
        if pid in eng.id_to_idx:
            idx = eng.id_to_idx[pid]
            user_vector += weight * eng.tfidf_matrix[idx].toarray().flatten()
            valid_items += 1
            cat = eng.df.iloc[idx]["category"]
            ptype = eng.df.iloc[idx]["product_type"]
            user_categories[cat] += weight
            user_types[ptype] += weight

    norm = np.linalg.norm(user_vector)
    if valid_items == 0 or norm == 0:
        return eng.get_popular_products(limit=limit)

    user_vector /= norm

    # 5. Raw dot-product
    raw_scores = eng.tfidf_matrix.dot(user_vector)

    # 6. Multi-Category Affinity Multiplier:
    # Instead of single-winner boost, grant proportional affinity to user's top demonstrated categories!
    total_cat_weight = sum(user_categories.values())
    cat_multiplier = np.ones(len(eng.df), dtype=np.float64)
    for cat, w in user_categories.items():
        share = w / total_cat_weight
        # If user has >= 15% interest in this category, give a proportional affinity boost (up to 1.15x)
        if share >= 0.15:
            cat_mask = (eng.df["category"] == cat).values
            boost = 1.0 + (0.15 * (share / max(user_categories.values()) * total_cat_weight / total_cat_weight))
            cat_multiplier = np.where(cat_mask, boost, cat_multiplier)

    adjusted_scores = raw_scores * cat_multiplier
    ranked_indices = np.argsort(adjusted_scores)[::-1]

    # 7. Diversity-Preserving Selection:
    # Limit max items per product_type (e.g. max 3 shorts, max 3 perfumes) to avoid single-type monopolization!
    recommendations = []
    seen_ids = set()
    type_counts = defaultdict(int)

    for idx in ranked_indices:
        item = eng.df.iloc[idx].to_dict()
        pid = item["product_id"]
        ptype = item.get("product_type", "Other")

        if pid in purchased_ids or pid in seen_ids:
            continue

        # Prevent single product_type monopolization
        if type_counts[ptype] >= max_per_type:
            continue

        seen_ids.add(pid)
        type_counts[ptype] += 1
        item["similarity_score"] = round(float(raw_scores[idx]) * 100, 1)
        item["ranking_score"] = round(float(adjusted_scores[idx]) * 100, 1)
        recommendations.append(item)

        if len(recommendations) >= limit:
            break

    return recommendations

print("=== TESTING PROPOSED FIX ACROSS 3 USERS ===")
for uid in [644, 3274, 10000]:
    u = query_db("SELECT first_name, last_name FROM users WHERE user_id = :1", (uid,), one=True)
    recs = simulate_improved_personalization(uid, limit=8, max_per_type=3)
    print(f"\nUser #{uid} ({u['first_name']} {u['last_name']}) Top 8 Recommendations:")
    for rank, r in enumerate(recs, 1):
        print(f"  {rank}. [{r['similarity_score']}% Match | RankScore: {r['ranking_score']}%] {r['product_name']} ({r['category']} > {r['product_type']})")
