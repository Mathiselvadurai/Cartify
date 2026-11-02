import sys
sys.path.insert(0, ".")
from collections import Counter
import re
from app.services.recommender import RecommendationEngine

eng = RecommendationEngine.get_instance()
# Build a word frequency counter from all features
all_words = Counter()
for doc in eng.df["features"]:
    words = re.findall(r"\b[a-z]{2,}\b", doc.lower())
    all_words.update(words)

print("Top 20 words in catalog:", all_words.most_common(20))
print("Freq of 'shoes':", all_words.get("shoes", 0))
print("Freq of 'shoe':", all_words.get("shoe", 0))
print("Freq of 'sho':", all_words.get("sho", 0))
