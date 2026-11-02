import sys
sys.path.insert(0, ".")
from collections import defaultdict
from app.db import query_db
from app.services.recommender import RecommendationEngine, EVENT_WEIGHTS

eng = RecommendationEngine.get_instance()
uid = 644

# Run the exact weighting logic from get_personalized_recommendations
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

print("=== WEIGHT SUMMARY FOR USER #644 IN CURRENT LOGIC ===")
print("By Category:", dict(sorted(cat_weights.items(), key=lambda x: -x[1])))
print("By Product Type (Top 10):", dict(sorted(type_weights.items(), key=lambda x: -x[1])[:10]))
