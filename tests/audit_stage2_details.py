import sys
sys.path.insert(0, ".")
from collections import defaultdict
from app.db import query_db

def audit_user(uid):
    u = query_db("SELECT user_id, first_name, last_name, gender, city FROM users WHERE user_id = :1", (uid,), one=True)
    print("=" * 80)
    print(f"USER #{uid}: {u['first_name']} {u['last_name']} ({u['gender']}, {u['city']})")
    print("=" * 80)

    # 1. Direct Purchases from ORDERS & ORDER_ITEMS
    purchases = query_db("""
        SELECT p.product_id, p.product_name, p.category, p.subcategory, p.product_type, p.brand,
               oi.order_id, o.order_date
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE o.user_id = :1
        ORDER BY o.order_date DESC
    """, (uid,))
    print(f"\n[A] Confirmed Orders ({len(purchases)} items purchased):")
    p_by_type = defaultdict(int)
    p_by_cat = defaultdict(int)
    for p in purchases:
        p_by_type[p['product_type']] += 1
        p_by_cat[p['category']] += 1
        print(f"   Order #{p['order_id']} ({p['order_date']}): {p['product_name']} [{p['category']} > {p['product_type']}]")
    print(f"   Purchase summary by Product Type: {dict(p_by_type)}")
    print(f"   Purchase summary by Category: {dict(p_by_cat)}")

    # 2. Interactions breakdown
    inter_summary = query_db("""
        SELECT i.event_type, p.category, p.product_type, COUNT(*) as cnt
        FROM interactions i
        JOIN products p ON i.product_id = p.product_id
        WHERE i.user_id = :1
        GROUP BY i.event_type, p.category, p.product_type
        ORDER BY i.event_type, cnt DESC
    """, (uid,))
    
    events_by_type = defaultdict(lambda: defaultdict(int))
    events_by_cat = defaultdict(lambda: defaultdict(int))
    for r in inter_summary:
        events_by_type[r['event_type']][r['product_type']] += r['cnt']
        events_by_cat[r['event_type']][r['category']] += r['cnt']

    print(f"\n[B] Interactions Breakdown:")
    for etype in ["purchase", "add_to_cart", "wishlist", "click", "view"]:
        if etype in events_by_cat:
            print(f"   -- {etype.upper()} by Category: {dict(events_by_cat[etype])}")
            print(f"      Top Product Types: {dict(list(sorted(events_by_type[etype].items(), key=lambda x: -x[1]))[:4])}")

if __name__ == "__main__":
    for uid in [644, 3274, 10000]:
        audit_user(uid)
