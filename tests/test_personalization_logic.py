import sys
import os
import numpy as np
from collections import defaultdict, Counter
sys.path.insert(0, ".")
from app.db import query_db
from app.services.recommender import RecommendationEngine

eng = RecommendationEngine.get_instance()

# Defined Event Weights
EVENT_WEIGHTS = {
    "purchase": 5.0,
    "add_to_cart": 3.0,
    "wishlist": 2.0,
    "click": 1.2,
    "view": 1.0
}

def get_personalized_recommendations_v2(user_id=None, limit=8):
    if not user_id:
        return eng.get_popular_products(limit=limit)

    # 1. Fetch user's interactions from Oracle DB (up to 100 recent interactions)
    interactions = query_db("""
        SELECT product_id, event_type
        FROM interactions
        WHERE user_id = :1
        ORDER BY event_timestamp DESC
        FETCH FIRST 100 ROWS ONLY
    """, (user_id,))

    # Also fetch purchased items from orders/order_items to ensure complete purchase coverage
    purchased_rows = query_db("""
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.user_id = :1
    """, (user_id,))
    purchased_ids = {r["product_id"] for r in purchased_rows}

    if not interactions and not purchased_ids:
        # Cold start fallback for new user with zero history
        return eng.get_popular_products(limit=limit)

    # 2. Accumulate weights per product
    item_weights = defaultdict(float)
    
    # Interactions weights
    for row in interactions:
        pid = row["product_id"]
        etype = row.get("event_type", "view").lower()
        w = EVENT_WEIGHTS.get(etype, 1.0)
        item_weights[pid] += w
        if etype == "purchase":
            purchased_ids.add(pid)

    # Ensure all direct order purchases also have the highest purchase weight (5.0)
    for pid in purchased_ids:
        item_weights[pid] = max(item_weights[pid], EVENT_WEIGHTS["purchase"])

    # 3. Build User Profile Vector in TF-IDF space
    # Sum weighted vectors of products in user's history
    user_vector = np.zeros(eng.tfidf_matrix.shape[1], dtype=np.float64)
    valid_history_count = 0
    top_categories = Counter()

    for pid, weight in item_weights.items():
        if pid in eng.id_to_idx:
            idx = eng.id_to_idx[pid]
            # Add sparse vector row
            user_vector += weight * eng.tfidf_matrix[idx].toarray().flatten()
            valid_history_count += 1
            # Track user category preferences
            p_cat = eng.df.iloc[idx]["category"]
            p_type = eng.df.iloc[idx]["product_type"]
            top_categories[p_cat] += weight
            top_categories[p_type] += weight

    if valid_history_count == 0 or np.linalg.norm(user_vector) == 0:
        return eng.get_popular_products(limit=limit)

    # Normalize user profile vector
    user_vector /= np.linalg.norm(user_vector)

    # 4. Compute similarity of User Profile Vector against all 34,190 active products
    raw_scores = eng.tfidf_matrix.dot(user_vector)

    # 5. Apply category affinity weighting based on user's demonstrated tastes
    most_favored_cat = top_categories.most_common(1)[0][0] if top_categories else None
    cat_multiplier = np.ones(len(eng.df), dtype=np.float64)
    if most_favored_cat:
        is_favored_cat = (eng.df["category"] == most_favored_cat).values
        cat_multiplier = np.where(is_favored_cat, 1.15, 1.0)

    adjusted_scores = raw_scores * cat_multiplier

    # 6. Rank products and filter out ALREADY PURCHASED items
    ranked_indices = np.argsort(adjusted_scores)[::-1]

    recommendations = []
    seen_ids = set()

    for idx in ranked_indices:
        item = eng.df.iloc[idx].to_dict()
        pid = item["product_id"]

        # Avoid recommending products customer has already purchased
        if pid in purchased_ids:
            continue

        if pid in seen_ids:
            continue

        seen_ids.add(pid)
        score = round(float(raw_scores[idx]) * 100, 1)
        item["similarity_score"] = score
        recommendations.append(item)

        if len(recommendations) >= limit:
            break

    return recommendations

print("Testing User Personalization:")
for uid in [644, 3274, 10000, 99999]: # 99999 is nonexistent/new user
    recs = get_personalized_recommendations_v2(user_id=uid, limit=5)
    u_info = query_db("SELECT first_name, gender FROM users WHERE user_id = :1", (uid,), one=True)
    name = f"{u_info['first_name']} ({u_info['gender']})" if u_info else "New User (Cold-Start)"
    print(f"\nUser #{uid} [{name}] Top 5 Recommendations:")
    for r in recs:
        print(f"  - [{r.get('similarity_score', 0)}%] {r['product_name']} ({r.get('category')} > {r.get('product_type')})")
