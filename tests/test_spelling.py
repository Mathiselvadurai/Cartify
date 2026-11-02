import difflib
import sys
sys.path.insert(0, ".")
from app.services.recommender import RecommendationEngine

eng = RecommendationEngine.get_instance()
vocab = [word for word in eng.vectorizer.vocabulary_.keys() if " " not in word]
print("Single word vocab count:", len(vocab))

typos = ["runing", "sheo", "shert", "watche", "lether", "adiddas", "pumma", "tshrt"]
for t in typos:
    m = difflib.get_close_matches(t, vocab, n=1, cutoff=0.75)
    print(f"Typo: '{t}' -> Corrected: {m}")
