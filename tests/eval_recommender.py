import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import query_db
from app.services.recommender import RecommendationEngine

def main():
    print("=== Category Distribution in Oracle 26ai ===")
    cats = query_db("SELECT category, COUNT(*) as cnt FROM products GROUP BY category ORDER BY cnt DESC")
    for c in cats:
        print(f" - {c['category']}: {c['cnt']:,} products")

    print("\n=== Shortest Descriptions in Database ===")
    min_desc = query_db("SELECT product_id, product_name, category, LENGTH(product_description) as len_desc, product_description FROM products WHERE is_active = 1 ORDER BY len_desc ASC FETCH FIRST 5 ROWS ONLY")
    for p in min_desc:
        print(f" - ID {p['product_id']} ({p['category']}): len={p['len_desc']}, '{p['product_name']}'")

    print("\n=== Inactive & Out-of-Stock Status ===")
    inactive = query_db("SELECT COUNT(*) as cnt FROM products WHERE is_active = 0", one=True)
    zero_stock = query_db("SELECT COUNT(*) as cnt FROM products WHERE stock_quantity = 0", one=True)
    print(f" - Inactive products (is_active = 0): {inactive['cnt']}")
    print(f" - Out of stock products (stock_quantity = 0): {zero_stock['cnt']}")

    # Check some inactive product IDs
    inactive_pids = query_db("SELECT product_id, product_name, category FROM products WHERE is_active = 0 FETCH FIRST 3 ROWS ONLY")
    print(f" - Sample inactive IDs: {[p['product_id'] for p in inactive_pids]}")

if __name__ == "__main__":
    main()
