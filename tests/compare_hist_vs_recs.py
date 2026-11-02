import sys
sys.path.insert(0, ".")
from collections import defaultdict, Counter
from app.db import query_db
from app.services.recommender import RecommendationEngine, EVENT_WEIGHTS

eng = RecommendationEngine.get_instance()

for uid in [644, 3274, 10000]:
    u = query_db("SELECT first_name, last_name FROM users WHERE user_id = :1", (uid,), one=True)
    
    interactions = query_db("""
        SELECT product_id, event_type
        FROM interactions
        WHERE user_id = :1
        ORDER BY event_timestamp DESC
        FETCH FIRST 100 ROWS ONLY
    """, (uid,))

    purchased_rows = query_db("""
        SELECT DISTINCT oi.product_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.user_id = :1
    """, (uid,))
    purchased_ids = {r["product_id"] for r in purchased_rows}

    item_weights = {}
    for row in interactions:
        pid = row["product_id"]
        etype = (row.get("event_type") or "view").lower()
        w = EVENT_WEIGHTS.get(etype, 1.0)
        item_weights[pid] = item_weights.get(pid, 0.0) + w
        if etype == "purchase":
            purchased_ids.add(pid)

    for pid in purchased_ids:
        item_weights[pid] = max(item_weights.get(pid, 0.0), EVENT_WEIGHTS["purchase"])

    type_weights = defaultdict(float)
    cat_weights = defaultdict(float)

    for pid, weight in item_weights.items():
        if pid in eng.id_to_idx:
            row = eng.df.iloc[eng.id_to_idx[pid]]
            type_weights[row["product_type"]] += weight
            cat_weights[row["category"]] += weight

    print(f"\n=== USER #{uid} ({u['first_name']} {u['last_name']}) ===")
    print("Historical Category Weights:", dict(sorted(cat_weights.items(), key=lambda x: -x[1])))
    print("Top 5 Historical Product Types:", dict(sorted(type_weights.items(), key=lambda x: -x[1])[:5]))

    # Compare with current recommended categories
    recs = eng.get_personalized_recommendations(user_id=uid, limit=8)
    rec_cats = [r.get("category") for r in recs]
    rec_types = [r.get("product_type") for r in recs]
    print("Recommended Categories (8 items):", Counter(rec_cats))
    print("Recommended Product Types (8 items):", Counter(rec_types))
