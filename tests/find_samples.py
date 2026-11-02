import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import query_db

samples = [
    # Category, subcategory or search hint
    ("Footwear", "Sports Shoes"),
    ("Footwear", "Formal Shoes"),
    ("Footwear", "Flats"),
    ("Apparel", "Topwear"),
    ("Apparel", "Bottomwear"),
    ("Apparel", "Dress"),
    ("Accessories", "Watches"),
    ("Accessories", "Wallets"),
    ("Personal Care", "Fragrance"),
    ("Personal Care", "Lips")
]

print("Selecting 10 diverse test products:")
chosen_products = []
for cat, sub in samples:
    sql = """
        SELECT product_id, product_name, brand, category, subcategory, product_type, gender,
               LENGTH(product_description) as desc_len, stock_quantity, is_active
        FROM products
        WHERE category = :1 AND subcategory = :2 AND is_active = 1
        ORDER BY sales_count DESC
        FETCH FIRST 1 ROW ONLY
    """
    row = query_db(sql, (cat, sub), one=True)
    if row:
        chosen_products.append(row)
        print(f"[{cat} | {sub}] ID {row['product_id']}: '{row['product_name']}' (Brand: {row['brand']}, desc_len: {row['desc_len']})")
    else:
        # Fallback by category
        fallback = query_db("SELECT product_id, product_name, brand, category, subcategory, product_type, gender, LENGTH(product_description) as desc_len FROM products WHERE category = :1 AND is_active = 1 FETCH FIRST 1 ROW ONLY", (cat,), one=True)
        chosen_products.append(fallback)
        print(f"[{cat} fallback] ID {fallback['product_id']}: '{fallback['product_name']}'")
