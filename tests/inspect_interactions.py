import sys
sys.path.insert(0, ".")
from app.db import query_db

print("--- INTERACTIONS columns ---")
cols = query_db("SELECT column_name, data_type FROM user_tab_cols WHERE table_name = 'INTERACTIONS'")
for c in cols:
    print(f"  {c['column_name']} ({c['data_type']})")

print("\n--- Distinct event types in INTERACTIONS ---")
evs = query_db("SELECT event_type, COUNT(*) as cnt FROM interactions GROUP BY event_type ORDER BY cnt DESC")
for e in evs:
    print(f"  {e['event_type']}: {e['cnt']:,}")

print("\n--- Check Users with Rich History in Oracle ---")
active_users = query_db("""
    SELECT user_id, 
           COUNT(*) as total_events,
           SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) as purchases,
           SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) as carts,
           SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) as views
    FROM interactions
    GROUP BY user_id
    HAVING SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) >= 2
    ORDER BY total_events DESC
    FETCH FIRST 5 ROWS ONLY
""")
for u in active_users:
    print(f"User #{u['user_id']}: Total={u['total_events']}, Purchases={u['purchases']}, Carts={u['carts']}, Views={u['views']}")

print("\n--- Check how interactions are recorded in Flask routes ---")
