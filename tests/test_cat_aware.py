import sys
sys.path.insert(0, ".")
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from app.services.recommender import RecommendationEngine

eng = RecommendationEngine.get_instance()
pid = 1571 # Kalenji Sports Shoes
idx = eng.id_to_idx[pid]
src = eng.df.iloc[idx]
print(f"Source: {src['product_name']} | {src['category']} > {src['subcategory']} > {src['product_type']}")

target_vec = eng.tfidf_matrix[idx]
sim_scores = cosine_similarity(target_vec, eng.tfidf_matrix).flatten()

# Compare Raw vs Category-Aware
# Raw:
top_raw = sim_scores.argsort()[::-1]
raw_recs = []
for i in top_raw:
    if i == idx:
        continue
    raw_recs.append(eng.df.iloc[i])
    if len(raw_recs) == 5:
        break

print("\n--- RAW (Existing) ---")
for r in raw_recs:
    score = sim_scores[eng.id_to_idx[r['product_id']]] * 100
    print(f" - [{score:.1f}%] {r['product_name']} ({r['category']} > {r['product_type']})")

# Category-Aware:
cat_scores = sim_scores.copy()
is_same_cat = (eng.df["category"] == src["category"]).values
is_same_sub = (eng.df["subcategory"] == src["subcategory"]).values
is_same_type = (eng.df["product_type"] == src["product_type"]).values

# Apply modest boost for category hierarchy and modest penalty for different top-level category
multiplier = np.where(is_same_type, 1.25,
             np.where(is_same_sub, 1.15,
             np.where(is_same_cat, 1.10, 0.70)))

adj_scores = cat_scores * multiplier
top_adj = adj_scores.argsort()[::-1]

adj_recs = []
for i in top_adj:
    if i == idx:
        continue
    adj_recs.append((eng.df.iloc[i], sim_scores[i] * 100))
    if len(adj_recs) == 5:
        break

print("\n--- CATEGORY-AWARE (Improved) ---")
for r, sc in adj_recs:
    print(f" - [{sc:.1f}%] {r['product_name']} ({r['category']} > {r['product_type']})")
