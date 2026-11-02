import sys
import os
import re
import difflib
from collections import Counter
sys.path.insert(0, ".")
from app.services.recommender import RecommendationEngine

eng = RecommendationEngine.get_instance()

# 1. Build high-frequency catalog vocabulary for spelling
all_words = Counter()
for doc in eng.df["features"]:
    words = re.findall(r"\b[a-z]{3,}\b", doc.lower())
    all_words.update(words)

# Terms that appear at least 30 times in the catalog
valid_vocab = {w for w, cnt in all_words.items() if cnt >= 30}
vocab_list = list(valid_vocab)

# Synonyms dictionary
SYNONYMS = {
    "sneakers": ["sports shoes", "casual shoes", "sneakers"],
    "sneaker": ["sports shoes", "casual shoes", "sneaker"],
    "trainers": ["running shoes", "sports shoes"],
    "trainer": ["running shoes", "sports shoes"],
    "shades": ["sunglasses"],
    "goggles": ["sunglasses"],
    "tee": ["tshirt", "t-shirt"],
    "tees": ["tshirt", "t-shirts"],
    "pants": ["trousers", "jeans"],
    "trousers": ["trousers", "pants"],
    "cologne": ["perfume", "fragrance"],
    "scent": ["perfume", "fragrance"],
    "slippers": ["flip flops", "sandals"],
    "chappal": ["flip flops", "sandals"],
    "hoodie": ["sweatshirt", "sweatshirts"],
    "lipstick": ["lip gloss", "lipstick"],
}

def correct_and_expand_query(raw_query):
    tokens = re.findall(r"\b[a-z0-9\'-]+\b", raw_query.lower())
    corrected_tokens = []
    
    for t in tokens:
        if t in valid_vocab:
            corrected_tokens.append(t)
        else:
            # Check for close matches in high-frequency catalog words
            matches = difflib.get_close_matches(t, vocab_list, n=3, cutoff=0.72)
            if matches:
                # Rank matches by catalog frequency
                best_match = max(matches, key=lambda w: all_words.get(w, 0))
                corrected_tokens.append(best_match)
            else:
                corrected_tokens.append(t)
                
    base_query = " ".join(corrected_tokens)
    
    # Synonym expansion
    expanded_parts = [base_query]
    for word in corrected_tokens:
        if word in SYNONYMS:
            expanded_parts.extend(SYNONYMS[word])
            
    expanded_query = " ".join(expanded_parts)
    return base_query, expanded_query

test_queries = [
    "runing shoes",
    "running sheo",
    "sneakers",
    "sports shoes",
    "red dres",
    "perfum",
    "xyznonexistentquery123"
]

print("=== SPELLING & SYNONYM QUERY EXPANSION TEST ===")
for q in test_queries:
    base, expanded = correct_and_expand_query(q)
    print(f"Original: '{q}' -> Corrected: '{base}' -> Expanded: '{expanded}'")
    
    # Test vector search
    q_vec = eng.vectorizer.transform([expanded])
    sims = (q_vec * eng.tfidf_matrix.T).toarray().flatten()
    matching = np.where(sims > 0.05)[0] if "np" in globals() else []
    # Using numpy
    import numpy as np
    matching = np.where(sims > 0.05)[0]
    sorted_idx = matching[np.argsort(sims[matching])[::-1]][:3]
    print(f"Results ({len(matching)} matches):")
    for i in sorted_idx:
        p = eng.df.iloc[i]
        print(f"  - [{sims[i]*100:.1f}%] {p['product_name']} ({p['category']} > {p['product_type']})")
    print()
