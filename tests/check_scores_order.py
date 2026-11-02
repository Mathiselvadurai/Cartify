import sys
sys.path.insert(0, ".")
from app.services.recommender import RecommendationEngine

eng = RecommendationEngine.get_instance()

for uid in [644, 3274, 10000]:
    recs = eng.get_personalized_recommendations(user_id=uid, limit=8)
    print(f"\n=== User #{uid} Recommendations ===")
    for rank, r in enumerate(recs, 1):
        print(f"  {rank}. [{r.get('similarity_score')}%] {r['product_name']} ({r.get('category')} > {r.get('product_type')})")
