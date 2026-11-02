import time
import math
import re
import difflib
from collections import Counter, defaultdict
import pandas as pd
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics.pairwise import cosine_similarity
from app.db import query_db, get_db

# Curated domain synonyms mapping for fashion & e-commerce
SYNONYMS = {
    "sneakers": ["sports shoes", "casual shoes", "sneakers"],
    "sneaker": ["sports shoes", "casual shoes", "sneaker"],
    "trainers": ["running shoes", "sports shoes"],
    "trainer": ["running shoes", "sports shoes"],
    "shades": ["sunglasses"],
    "goggles": ["sunglasses"],
    "tee": ["tshirt", "t-shirt"],
    "tees": ["tshirt", "t-shirts"],
    "pants": ["trousers", "jeans", "track pants"],
    "trousers": ["trousers", "pants"],
    "cologne": ["perfume", "fragrance"],
    "scent": ["perfume", "fragrance"],
    "slippers": ["flip flops", "sandals"],
    "chappal": ["flip flops", "sandals"],
    "hoodie": ["sweatshirt", "sweatshirts"],
    "lipstick": ["lip gloss", "lipstick"],
    "lip color": ["lip gloss", "lipstick"],
}

# Interaction event weights for personalization
EVENT_WEIGHTS = {
    "purchase": 5.0,     # Strongest explicit signal (completed order)
    "add_to_cart": 3.0,  # High consideration intent
    "wishlist": 2.0,     # Expressed interest
    "click": 1.2,        # Catalog exploration
    "view": 1.0          # Basic product browsing
}

class RecommendationEngine:
    _instance = None
    
    def __init__(self):
        self.df = None
        self.id_to_idx = {}
        self.idx_to_id = {}
        self.vectorizer = None
        self.tfidf_matrix = None
        self.is_initialized = False
        self.word_freq = Counter()
        self.high_freq_vocab = set()
        self.vocab_list = []
        self.R_sparse = None
        self.user_to_idx = {}
        self.item_norms = None
        self.cf_initialized = False
        self.svd = None
        self.dense_embeddings = None
        self.semantic_initialized = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = RecommendationEngine()
            cls._instance.initialize()
        return cls._instance

    def initialize(self):
        print("Initializing TF-IDF Recommendation Engine...")
        start_time = time.time()
        
        # Load active products directly from Oracle database
        sql = """
            SELECT product_id, product_name, brand, category, subcategory, 
                   product_type, gender, color, search_keywords, product_description,
                   price_inr, sale_price_inr, discount_percent, rating, review_count, 
                   stock_quantity, sales_count, is_active, image_url
            FROM products
            WHERE is_active = 1
            ORDER BY product_id
        """
        rows = query_db(sql)
        if not rows:
            print("Warning: No products found in Oracle DB! Falling back to raw CSV.")
            self.df = pd.read_csv("data/raw/products.csv")
            self.df = self.df[self.df["is_active"] == 1].copy()
        else:
            self.df = pd.DataFrame(rows)

        # Mapping dictionaries for quick O(1) index lookup
        self.id_to_idx = {int(pid): idx for idx, pid in enumerate(self.df["product_id"])}
        self.idx_to_id = {idx: int(pid) for idx, pid in enumerate(self.df["product_id"])}

        # Build feature text for content-based TF-IDF
        # Give title tokens increased prominence to prevent long generic descriptions from diluting key item terms
        self.df["features"] = (
            self.df["product_name"].fillna("") + " " +
            self.df["product_name"].fillna("") + " " +
            self.df["brand"].fillna("") + " " +
            self.df["category"].fillna("") + " " +
            self.df["subcategory"].fillna("") + " " +
            self.df["product_type"].fillna("") + " " +
            self.df["gender"].fillna("") + " " +
            self.df["color"].fillna("") + " " +
            self.df["search_keywords"].fillna("") + " " +
            self.df["product_description"].fillna("")
        )

        # Build high-frequency vocabulary for spelling correction
        self.word_freq = Counter()
        for doc in self.df["features"]:
            words = re.findall(r"\b[a-z]{3,}\b", doc.lower())
            self.word_freq.update(words)
            
        # Keep tokens with meaningful catalog frequency (>= 30 occurrences)
        # Always include curated domain synonyms so recognized terms are never misclassified as typos
        synonym_words = set(SYNONYMS.keys())
        for syn_list in SYNONYMS.values():
            for s in syn_list:
                synonym_words.update(re.findall(r"\b[a-z]{3,}\b", s.lower()))

        self.high_freq_vocab = {w for w, cnt in self.word_freq.items() if cnt >= 30} | synonym_words
        self.vocab_list = list(self.high_freq_vocab)

        # Fit TF-IDF Vectorizer
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=12000,
            ngram_range=(1, 2)
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.df["features"])
        self.is_initialized = True
        
        # Build lightweight Collaborative Filtering interaction matrix
        self._init_collaborative_matrix()
        
        # Build dense semantic concept embeddings for semantic product search
        self._init_semantic_embeddings()
        print(f"TF-IDF Engine ready with {len(self.df):,} products in {time.time() - start_time:.2f}s!")

    def _init_collaborative_matrix(self, max_timestamp=None):
        """
        Constructs a lightweight sparse user-item interaction matrix R from Oracle interactions.
        Uses intent-bounded diminishing weights: w(u, i) = base_intent + 0.15 * ln(1 + count).
        Optionally filters by max_timestamp to strictly enforce temporal holdout boundaries during offline evaluation.
        """
        if self.cf_initialized and max_timestamp is None:
            return self.R_sparse, self.user_to_idx, self.item_norms

        if max_timestamp:
            sql = """
                SELECT user_id, product_id, event_type, event_timestamp
                FROM interactions
                WHERE event_timestamp <= :1
                ORDER BY user_id, event_timestamp ASC
            """
            events = query_db(sql, (max_timestamp,))
        else:
            sql = """
                SELECT user_id, product_id, event_type
                FROM interactions
                ORDER BY user_id
            """
            events = query_db(sql)

        if not events or self.df is None:
            return None, {}, None

        user_item_intents = defaultdict(lambda: defaultdict(float))
        user_item_counts = defaultdict(lambda: defaultdict(int))
        user_set = set()

        for ev in events:
            uid = ev["user_id"]
            pid = ev["product_id"]
            et = (ev.get("event_type") or "view").lower()
            w = EVENT_WEIGHTS.get(et, 1.0)
            user_item_intents[uid][pid] = max(user_item_intents[uid][pid], w)
            user_item_counts[uid][pid] += 1
            user_set.add(uid)

        user_list = sorted(list(user_set))
        u_to_idx = {uid: idx for idx, uid in enumerate(user_list)}

        rows, cols, data = [], [], []
        for uid in user_list:
            u_idx = u_to_idx[uid]
            for pid, max_intent in user_item_intents[uid].items():
                if pid in self.id_to_idx:
                    p_idx = self.id_to_idx[pid]
                    cnt = user_item_counts[uid][pid]
                    val = max_intent + 0.15 * math.log(1 + cnt)
                    rows.append(u_idx)
                    cols.append(p_idx)
                    data.append(val)

        n_users = len(user_list)
        n_items = len(self.df)
        R_mat = csr_matrix((data, (rows, cols)), shape=(n_users, n_items), dtype=np.float32)

        # Precompute L2 norms of item columns for cosine normalization in Item-based CF
        item_matrix = R_mat.tocsc()
        item_sq_sum = np.array(item_matrix.power(2).sum(axis=0)).flatten()
        norms = np.sqrt(item_sq_sum)
        norms[norms == 0] = 1.0

        if max_timestamp is None:
            self.R_sparse = R_mat
            self.user_to_idx = u_to_idx
            self.item_norms = norms
            self.cf_initialized = True

        return R_mat, u_to_idx, norms

    def _init_semantic_embeddings(self, n_components=256):
        """
        Fits a dense semantic concept embedding model (TruncatedSVD / Latent Semantic Analysis)
        over the catalog TF-IDF space. Precomputes unit-normalized 256-dimensional dense vectors
        for all 34,190 active catalog products for fast O(1) runtime query inference.
        """
        if self.semantic_initialized and self.dense_embeddings is not None:
            return self.svd, self.dense_embeddings

        if self.tfidf_matrix is None:
            return None, None

        self.svd = TruncatedSVD(n_components=n_components, algorithm="randomized", random_state=42)
        raw_embeddings = self.svd.fit_transform(self.tfidf_matrix)

        # L2-normalize all product embeddings for cosine similarity via dot product
        norms = np.linalg.norm(raw_embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.dense_embeddings = (raw_embeddings / norms).astype(np.float32)
        self.semantic_initialized = True
        return self.svd, self.dense_embeddings

    def _correct_and_expand_query(self, query):
        """
        Corrects common spelling mistakes using catalog vocabulary
        and expands domain synonyms (e.g. sneakers -> sports shoes).
        """
        if not query:
            return "", ""
            
        tokens = re.findall(r"\b[a-z0-9\'-]+\b", query.lower())
        corrected_tokens = []
        
        for t in tokens:
            if t in self.high_freq_vocab or t in self.vectorizer.vocabulary_:
                corrected_tokens.append(t)
            else:
                # Look for close spelling matches in high-frequency catalog vocabulary
                matches = difflib.get_close_matches(t, self.vocab_list, n=5, cutoff=0.75)
                # Filter out candidates with excessive length disparity (> 2 chars) to avoid substring traps
                plausible_matches = [m for m in matches if abs(len(t) - len(m)) <= 2]
                if plausible_matches:
                    best_match = max(plausible_matches, key=lambda w: self.word_freq.get(w, 0))
                    corrected_tokens.append(best_match)
                elif matches:
                    best_match = max(matches, key=lambda w: self.word_freq.get(w, 0))
                    corrected_tokens.append(best_match)
                else:
                    corrected_tokens.append(t)
                    
        base_query = " ".join(corrected_tokens)
        
        # Expand synonyms
        expanded_parts = [base_query]
        for word in corrected_tokens:
            if word in SYNONYMS:
                expanded_parts.extend(SYNONYMS[word])
                
        expanded_query = " ".join(expanded_parts)
        return base_query, expanded_query

    def get_similar_products(self, product_id, top_n=6):
        """
        Calculates cosine similarity between a target product and all products in catalog.
        Uses category-aware affinity re-ranking to prioritize same-category / same-product-type
        items while penalizing unrelated cross-category suggestions.
        """
        if not self.is_initialized or product_id not in self.id_to_idx:
            return self.get_popular_products(limit=top_n)

        idx = self.id_to_idx[product_id]
        target_vec = self.tfidf_matrix[idx]
        target_row = self.df.iloc[idx]
        
        # Fast cosine similarity vector dot-product
        sim_scores = cosine_similarity(target_vec, self.tfidf_matrix).flatten()
        
        # Category-aware affinity weighting:
        # Boost same product_type (1.25x), same subcategory (1.15x), same category (1.10x)
        # Apply 0.70x dampening factor to different top-level categories to avoid brand leapfrogging
        is_same_cat = (self.df["category"] == target_row["category"]).values
        is_same_sub = (self.df["subcategory"] == target_row["subcategory"]).values
        is_same_type = (self.df["product_type"] == target_row["product_type"]).values

        category_multiplier = np.where(is_same_type, 1.25,
                              np.where(is_same_sub, 1.15,
                              np.where(is_same_cat, 1.10, 0.70)))
                              
        adjusted_scores = sim_scores * category_multiplier
        
        # Sort scores in descending order
        top_indices = adjusted_scores.argsort()[::-1]
        
        results = []
        for i in top_indices:
            if i == idx:
                continue
            item = self.df.iloc[i].to_dict()
            # Preserve the true raw cosine similarity percentage for display
            score = round(float(sim_scores[i]) * 100, 1)
            adj_score = round(float(adjusted_scores[i]) * 100, 1)
            item["similarity_score"] = score
            item["ranking_score"] = adj_score
            
            # Recommendation explainability
            if item.get("product_type") == target_row.get("product_type"):
                item["recommendation_reason"] = f"Similar {item.get('product_type')} to viewed item"
            elif item.get("category") == target_row.get("category"):
                item["recommendation_reason"] = f"Related {item.get('category')} product"
            else:
                item["recommendation_reason"] = "Contextually related style"

            results.append(item)
            if len(results) >= top_n:
                break
                
        return results

    def smart_search(self, query, top_n=24, strategy="hybrid", beta=0.20):
        """
        Multimodal search retrieval supporting:
        1. 'hybrid' (default): Linear combination of lexical TF-IDF + domain expansion (1 - beta = 0.80)
           and dense continuous concept embeddings (beta = 0.20).
        2. 'semantic': Dense vector space retrieval using precomputed 256-dimensional SVD embeddings.
        3. 'lexical': Classical tokenized TF-IDF with typo-correction and synonym expansion.
        """
        if not query or not self.is_initialized:
            return []

        # 1. Spelling correction & domain synonym expansion
        base_query, expanded_query = self._correct_and_expand_query(query)
        query_vec = self.vectorizer.transform([expanded_query])
        
        # 2. Lexical TF-IDF scores
        lex_scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        lex_max = float(np.max(lex_scores))
        lex_norm = lex_scores / lex_max if lex_max > 1e-9 else np.zeros_like(lex_scores)

        # 3. Dense Semantic Embeddings (TruncatedSVD Latent Semantic Analysis)
        sem_norm = np.zeros(len(self.df), dtype=np.float32)
        if self.semantic_initialized and self.dense_embeddings is not None:
            q_emb = self.svd.transform(query_vec)
            q_norm_val = float(np.linalg.norm(q_emb))
            if q_norm_val > 1e-9:
                q_emb = q_emb / q_norm_val
                sem_scores = self.dense_embeddings.dot(q_emb.T).flatten()
                sem_scores = np.maximum(sem_scores, 0.0)  # clip negative cosine distance
                sem_max = float(np.max(sem_scores))
                if sem_max > 1e-9:
                    sem_norm = (sem_scores / sem_max).astype(np.float32)

        # 4. Strategy selection & Score Blending
        if strategy in ("lexical", "tfidf"):
            ranking_scores = lex_scores
            raw_scores = lex_scores
        elif strategy == "semantic":
            # For pure semantic, require a minimum threshold to avoid hallucinations on gibberish
            if np.max(sem_norm) > 0.10:
                ranking_scores = sem_norm
                raw_scores = sem_norm
            else:
                ranking_scores = np.zeros(len(self.df), dtype=np.float32)
                raw_scores = np.zeros(len(self.df), dtype=np.float32)
        else:  # strategy == "hybrid" (default)
            if lex_max > 1e-9 and np.max(sem_norm) > 1e-9:
                # Balanced linear blend: (1 - beta) * lex + beta * sem
                ranking_scores = (1.0 - beta) * lex_norm + beta * sem_norm
                raw_scores = lex_scores
            elif lex_max > 1e-9:
                ranking_scores = lex_norm
                raw_scores = lex_scores
            elif np.max(sem_norm) > 0.15:
                # Pure semantic fallback when no exact token matches exist
                ranking_scores = sem_norm
                raw_scores = sem_norm
            else:
                ranking_scores = np.zeros(len(self.df), dtype=np.float32)
                raw_scores = np.zeros(len(self.df), dtype=np.float32)

        # Guarantee finite numerical values (NaN/Inf protection)
        ranking_scores = np.nan_to_num(ranking_scores, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        raw_scores = np.nan_to_num(raw_scores, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

        # 5. Candidate selection & non-zero filtering
        # Threshold: ensure out-of-vocabulary or gibberish queries return 0 results
        matching_indices = np.where(ranking_scores > 0.08)[0]
        if len(matching_indices) == 0:
            matching_indices = np.where(ranking_scores > 0.04)[0]
            if len(matching_indices) == 0:
                return []

        sorted_indices = matching_indices[np.argsort(ranking_scores[matching_indices])[::-1]][:top_n]

        results = []
        for i in sorted_indices:
            item = self.df.iloc[i].to_dict()
            raw_s = round(float(raw_scores[i]) * 100, 1)
            adj_s = round(float(ranking_scores[i]) * 100, 1)
            item["similarity_score"] = raw_s
            item["ranking_score"] = adj_s
            item["lexical_score"] = round(float(lex_scores[i]) * 100, 1)
            item["semantic_score"] = round(float(sem_norm[i]) * 100, 1)
            
            # Explainability reason
            if strategy == "hybrid" and item["semantic_score"] >= 60.0 and item["lexical_score"] >= 20.0:
                item["recommendation_reason"] = f"Hybrid search: Token match ({item['lexical_score']}%) + Semantic concept ({item['semantic_score']}%)"
            elif strategy == "semantic" or (item["lexical_score"] < 5.0 and item["semantic_score"] >= 50.0):
                item["recommendation_reason"] = f"Semantic match: Relevant to conceptual intent in {item['category']}"
            elif item["lexical_score"] >= 40.0:
                item["recommendation_reason"] = f"Strong keyword relevance ({item['lexical_score']}% match)"
            else:
                item["recommendation_reason"] = "Matched query keywords"

            results.append(item)

        return results

    def get_popular_products(self, limit=8, category=None):
        """
        Returns highest-rated and top-selling products.
        Useful for Cold-Start problem when user has no browsing history.
        """
        if self.df is None or len(self.df) == 0:
            return []
            
        df_sub = self.df
        if category:
            df_sub = df_sub[df_sub["category"].str.lower() == category.lower()]
            
        popular = df_sub.sort_values(by=["rating", "sales_count"], ascending=[False, False]).head(limit)
        pop_list = popular.to_dict(orient="records")
        for p in pop_list:
            p["recommendation_reason"] = "Trending customer favorite"
        return pop_list

    def get_personalized_recommendations(self, user_id=None, limit=8, strategy="hybrid", alpha=0.20):
        """
        Builds personalized recommendations combining:
        1. Content-based User Profile Vector in 12,000-dimensional TF-IDF space
           weighted by user interactions (purchase: 5.0, cart: 3.0, wishlist: 2.0, click: 1.2, view: 1.0)
           and proportional multi-category affinity.
        2. Lightweight Item-based Collaborative Filtering using historical interaction co-occurrence.
        3. Diversity constraint: strict maximum of 3 recommendations per product_type in top recommendations.
        4. Selectable strategy: 'hybrid' (default), 'content' (TF-IDF only baseline), or 'collaborative'.
        """
        if not user_id or not self.is_initialized:
            return self.get_popular_products(limit=limit)

        # 1. Fetch user interactions & completed purchases in a single pooled connection
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT product_id, event_type
                FROM interactions
                WHERE user_id = :1
                ORDER BY event_timestamp DESC
                FETCH FIRST 100 ROWS ONLY
            """, (user_id,))
            cols = [c[0].lower() for c in cur.description]
            interactions = [dict(zip(cols, r)) for r in cur.fetchall()]

            cur.execute("""
                SELECT DISTINCT oi.product_id
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.order_id
                WHERE o.user_id = :1
            """, (user_id,))
            purchased_ids = {r[0] for r in cur.fetchall()}
        finally:
            cur.close()
            conn.close()

        if not interactions and not purchased_ids:
            # Fallback for new user with zero history (Cold Start)
            return self.get_popular_products(limit=limit)

        # 3. Calculate intent-bounded weights with diminishing frequency
        product_highest_intent = {}
        product_event_counts = Counter()

        for row in interactions:
            pid = row["product_id"]
            etype = (row.get("event_type") or "view").lower()
            intent = EVENT_WEIGHTS.get(etype, 1.0)
            product_highest_intent[pid] = max(product_highest_intent.get(pid, 1.0), intent)
            product_event_counts[pid] += 1
            if etype == "purchase":
                purchased_ids.add(pid)

        # Ensure all direct order purchases carry full purchase intent
        for pid in purchased_ids:
            product_highest_intent[pid] = max(product_highest_intent.get(pid, 1.0), EVENT_WEIGHTS["purchase"])

        # Intent-bounded weight formula: base_intent + 0.15 * ln(1 + count)
        item_weights = {}
        for pid, base_intent in product_highest_intent.items():
            count = product_event_counts.get(pid, 0)
            item_weights[pid] = base_intent + 0.15 * math.log(1 + count)

        # 4. Construct the weighted User Profile Vector in TF-IDF space
        user_vector = np.zeros(self.tfidf_matrix.shape[1], dtype=np.float64)
        valid_items_count = 0
        user_categories = Counter()

        for pid, weight in item_weights.items():
            if pid in self.id_to_idx:
                idx = self.id_to_idx[pid]
                user_vector += weight * self.tfidf_matrix[idx].toarray().flatten()
                valid_items_count += 1
                
                # Track user category affinity
                cat = self.df.iloc[idx]["category"]
                user_categories[cat] += weight

        norm = np.linalg.norm(user_vector)
        if valid_items_count == 0 or norm == 0:
            return self.get_popular_products(limit=limit)

        # Normalize user profile vector to unit length
        user_vector /= norm

        # 5. Fast dot-product against all 34,190 active product vectors
        raw_scores = self.tfidf_matrix.dot(user_vector)

        # 6. Apply proportional multi-category affinity multiplier
        # Any category with >= 15% share of user weight gets a proportional boost: 1.0 + 0.15 * share
        total_cat_weight = sum(user_categories.values())
        cat_multipliers = {}
        if total_cat_weight > 0:
            for cat, cat_w in user_categories.items():
                share = cat_w / total_cat_weight
                if share >= 0.15:
                    cat_multipliers[cat] = 1.0 + 0.15 * share
                else:
                    cat_multipliers[cat] = 1.0

        cat_multiplier_arr = np.array([cat_multipliers.get(c, 1.0) for c in self.df["category"].values], dtype=np.float64)
        content_scores = raw_scores * cat_multiplier_arr

        # 7. Selectable Ranking Strategy (Hybrid Blending vs Content Baseline vs Collaborative)
        cf_scores = np.zeros(len(self.df), dtype=np.float64)
        if strategy == "hybrid" and self.cf_initialized:
            if user_id in self.user_to_idx and self.R_sparse is not None:
                u_row = self.R_sparse[self.user_to_idx[user_id]]
                user_user_proj = u_row.dot(self.R_sparse.T)
                cf_raw = user_user_proj.dot(self.R_sparse).toarray().flatten()
                cf_scores = cf_raw / self.item_norms
                cf_max = np.max(cf_scores)
                if cf_max > 0:
                    cf_scores /= cf_max

            c_max = np.max(content_scores)
            c_norm = content_scores / c_max if c_max > 0 else content_scores

            if np.max(cf_scores) > 0:
                adjusted_scores = (1.0 - alpha) * c_norm + alpha * cf_scores
            else:
                adjusted_scores = content_scores
        elif strategy == "collaborative" and self.cf_initialized and user_id in self.user_to_idx:
            u_row = self.R_sparse[self.user_to_idx[user_id]]
            user_user_proj = u_row.dot(self.R_sparse.T)
            cf_raw = user_user_proj.dot(self.R_sparse).toarray().flatten()
            cf_scores = cf_raw / self.item_norms
            adjusted_scores = cf_scores if np.max(cf_scores) > 0 else content_scores
        else:
            adjusted_scores = content_scores

        # 8. Candidate ranking with diversity cap (max 3 per product_type in top recommendations)
        ranked_indices = np.argsort(adjusted_scores)[::-1]

        recommendations = []
        seen_ids = set()
        type_counts = Counter()
        max_per_type = 3

        # Pass 1: Select top candidates respecting the max_per_type cap
        for idx in ranked_indices:
            pid = int(self.df.iloc[idx]["product_id"])

            if pid in purchased_ids or pid in seen_ids:
                continue

            ptype = self.df.iloc[idx].get("product_type") or "other"
            if type_counts[ptype] >= max_per_type:
                continue

            seen_ids.add(pid)
            type_counts[ptype] += 1
            item = self.df.iloc[idx].to_dict()
            raw = float(raw_scores[idx])
            adj = float(adjusted_scores[idx])
            item["similarity_score"] = round(raw * 100, 1)
            item["ranking_score"] = round(adj * 100, 1)
            
            # Recommendation explainability
            cat_share = (user_categories.get(item["category"], 0) / total_cat_weight) * 100.0 if total_cat_weight > 0 else 0.0
            if strategy == "hybrid" and cf_scores[idx] > 0.15:
                item["recommendation_reason"] = f"Hybrid pick: Matches your {item['category']} tastes & peer browsing patterns"
            elif cat_share >= 15.0:
                item["recommendation_reason"] = f"Matches your interest in {item['category']} ({int(cat_share)}% of profile)"
            elif raw >= 0.45:
                item["recommendation_reason"] = f"Strong content match ({round(raw * 100, 1)}% cosine similarity)"
            else:
                item["recommendation_reason"] = "Personalized recommendation based on your browsing profile"

            recommendations.append(item)

            if len(recommendations) >= limit:
                break

        # Pass 2: Safely handle edge cases with fewer than limit products meeting cap
        if len(recommendations) < limit:
            for idx in ranked_indices:
                pid = int(self.df.iloc[idx]["product_id"])
                if pid in purchased_ids or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                item = self.df.iloc[idx].to_dict()
                raw = float(raw_scores[idx])
                adj = float(adjusted_scores[idx])
                item["similarity_score"] = round(raw * 100, 1)
                item["ranking_score"] = round(adj * 100, 1)
                item["recommendation_reason"] = "Personalized alternative recommendation"
                recommendations.append(item)
                if len(recommendations) >= limit:
                    break

        return recommendations
