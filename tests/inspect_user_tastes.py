import sys
sys.path.insert(0, ".")
from app.db import query_db

for uid in [644, 3274, 10000]:
    u = query_db("SELECT user_id, first_name, last_name, email, gender FROM users WHERE user_id = :1", (uid,), one=True)
    print(f"\n=== User #{uid}: {u['first_name']} {u['last_name']} ({u['gender']}) ===")
    
    # Purchases
    purchases = query_db("""
        SELECT p.product_id, p.product_name, p.category, p.subcategory, p.product_type, p.brand, oi.order_id
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE o.user_id = :1
        FETCH FIRST 5 ROWS ONLY
    """, (uid,))
    print(f"Purchased products ({len(purchases)}):")
    for p in purchases:
        print(f"  - [Order {p['order_id']}] {p['product_name']} ({p['category']} > {p['product_type']})")

    # Recent interactions breakdown
    int_summary = query_db("""
        SELECT event_type, COUNT(*) as cnt
        FROM interactions
        WHERE user_id = :1
        GROUP BY event_type
    """, (uid,))
    print(f"Interaction counts: {int_summary}")
