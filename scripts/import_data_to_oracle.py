"""
Safe, fast, chunked CSV to Oracle Database 26ai migration script.
Loads:
1. products.csv
2. users.csv (with password_hash for web login)
3. orders.csv
4. order_items.csv
5. reviews.csv
6. interactions.csv (optional full or sampled)
"""

import os
import time
import pandas as pd
import numpy as np
import oracledb
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

USER = os.getenv("ORACLE_USER", "ecomm_user")
PASSWORD = os.getenv("ORACLE_PASSWORD")
if not PASSWORD:
    raise RuntimeError("Set ORACLE_PASSWORD in .env before connecting")
DSN = os.getenv("ORACLE_DSN", "localhost:1521/freepdb1")
BATCH_SIZE = 5000

def get_connection():
    return oracledb.connect(user=USER, password=PASSWORD, dsn=DSN)

def clean_row_value(val):
    if pd.isna(val) or val is np.nan:
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        return float(val)
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    return val

def import_products(conn):
    print("\n[1/6] Importing products.csv ...")
    start = time.time()
    df = pd.read_csv("data/raw/products.csv")
    
    # Rename 'usage' to 'product_usage'
    df = df.rename(columns={"usage": "product_usage"})
    
    # Fill defaults/cleaning
    df["metrics_synthetic"] = df["metrics_synthetic"].fillna(1).astype(int)
    df["is_active"] = df["is_active"].fillna(1).astype(int)
    
    cols = [
        "product_id", "product_name", "brand", "variant", "category",
        "subcategory", "product_type", "gender", "age_group", "product_usage",
        "season", "color", "product_description", "search_keywords", "price_inr",
        "sale_price_inr", "discount_percent", "rating", "review_count", "stock_quantity",
        "sales_count", "metrics_synthetic", "is_active", "image_url", "source_dataset"
    ]
    
    sql = f"""
    INSERT INTO products ({', '.join(cols)})
    VALUES ({', '.join([':' + str(i+1) for i in range(len(cols))])})
    """
    
    rows = []
    for r in df[cols].itertuples(index=False):
        cleaned = [clean_row_value(v) for v in r]
        rows.append(cleaned)
        
    cur = conn.cursor()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        cur.executemany(sql, batch)
        conn.commit()
    print(f"Products imported: {len(rows):,} rows in {time.time() - start:.2f}s")

def import_users(conn):
    print("\n[2/6] Importing users.csv ...")
    start = time.time()
    df = pd.read_csv("data/raw/users.csv")
    
    # Default password hash for all demo users ('password123')
    default_hash = generate_password_hash("password123")
    df["password_hash"] = default_hash
    df["signup_date"] = pd.to_datetime(df["signup_date"]).dt.date
    df["last_active_date"] = pd.to_datetime(df["last_active_date"]).dt.date
    df["is_active"] = df["is_active"].fillna(1).astype(int)
    
    cols = [
        "user_id", "first_name", "last_name", "email", "password_hash",
        "gender", "age", "city", "state", "signup_date",
        "membership_tier", "primary_device", "acquisition_channel", "last_active_date", "is_active"
    ]
    
    sql = f"""
    INSERT INTO users ({', '.join(cols)})
    VALUES ({', '.join([':' + str(i+1) for i in range(len(cols))])})
    """
    
    rows = []
    for r in df[cols].itertuples(index=False):
        cleaned = [clean_row_value(v) for v in r]
        rows.append(cleaned)
        
    cur = conn.cursor()
    cur.executemany(sql, rows)
    conn.commit()
    print(f"Users imported: {len(rows):,} rows in {time.time() - start:.2f}s")

def import_orders(conn):
    print("\n[3/6] Importing orders.csv ...")
    start = time.time()
    df = pd.read_csv("data/raw/orders.csv")
    
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["delivery_date"] = pd.to_datetime(df["delivery_date"]).dt.date
    
    cols = [
        "order_id", "user_id", "order_date", "order_status", "payment_method",
        "coupon_code", "num_items", "subtotal", "discount_amount", "shipping_fee",
        "total_amount", "shipping_city", "shipping_state", "delivery_date"
    ]
    
    sql = f"""
    INSERT INTO orders ({', '.join(cols)})
    VALUES ({', '.join([':' + str(i+1) for i in range(len(cols))])})
    """
    
    rows = []
    for r in df[cols].itertuples(index=False):
        cleaned = [clean_row_value(v) for v in r]
        rows.append(cleaned)
        
    cur = conn.cursor()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        cur.executemany(sql, batch)
        conn.commit()
    print(f"Orders imported: {len(rows):,} rows in {time.time() - start:.2f}s")

def import_order_items(conn):
    print("\n[4/6] Importing order_items.csv ...")
    start = time.time()
    df = pd.read_csv("data/raw/order_items.csv")
    
    cols = ["order_item_id", "order_id", "product_id", "quantity", "unit_price", "line_total"]
    sql = f"""
    INSERT INTO order_items ({', '.join(cols)})
    VALUES ({', '.join([':' + str(i+1) for i in range(len(cols))])})
    """
    
    rows = []
    for r in df[cols].itertuples(index=False):
        cleaned = [clean_row_value(v) for v in r]
        rows.append(cleaned)
        
    cur = conn.cursor()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        cur.executemany(sql, batch)
        conn.commit()
    print(f"Order Items imported: {len(rows):,} rows in {time.time() - start:.2f}s")

def import_reviews(conn):
    print("\n[5/6] Importing reviews.csv ...")
    start = time.time()
    df = pd.read_csv("data/raw/reviews.csv")
    
    df["review_date"] = pd.to_datetime(df["review_date"])
    df["verified_purchase"] = df["verified_purchase"].fillna(1).astype(int)
    df["helpful_votes"] = df["helpful_votes"].fillna(0).astype(int)
    
    cols = [
        "review_id", "user_id", "product_id", "order_id", "rating",
        "review_title", "review_text", "review_date", "verified_purchase", "helpful_votes"
    ]
    
    sql = f"""
    INSERT INTO reviews ({', '.join(cols)})
    VALUES ({', '.join([':' + str(i+1) for i in range(len(cols))])})
    """
    
    rows = []
    for r in df[cols].itertuples(index=False):
        cleaned = [clean_row_value(v) for v in r]
        rows.append(cleaned)
        
    cur = conn.cursor()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        cur.executemany(sql, batch)
        conn.commit()
    print(f"Reviews imported: {len(rows):,} rows in {time.time() - start:.2f}s")

def import_interactions(conn, sample_limit=50000):
    """
    Imports interactions. Since interactions has 541,827 rows,
    importing a representative recent sample (e.g., 50,000 rows) keeps import fast
    and provides plenty of interaction events for recommender models.
    Pass sample_limit=None to import all 541k rows.
    """
    print(f"\n[6/6] Importing interactions.csv (limit: {sample_limit or 'ALL'}) ...")
    start = time.time()
    
    if sample_limit:
        df = pd.read_csv("data/raw/interactions.csv", nrows=sample_limit)
    else:
        df = pd.read_csv("data/raw/interactions.csv")
        
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    
    cols = [
        "interaction_id", "user_id", "session_id", "product_id", "event_type",
        "event_timestamp", "device_type", "referrer", "order_id"
    ]
    
    sql = f"""
    INSERT INTO interactions ({', '.join(cols)})
    VALUES ({', '.join([':' + str(i+1) for i in range(len(cols))])})
    """
    
    rows = []
    for r in df[cols].itertuples(index=False):
        cleaned = [clean_row_value(v) for v in r]
        rows.append(cleaned)
        
    cur = conn.cursor()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        cur.executemany(sql, batch)
        conn.commit()
    print(f"Interactions imported: {len(rows):,} rows in {time.time() - start:.2f}s")

def main():
    print("Connecting to Oracle Database 26ai...")
    conn = get_connection()
    try:
        import_products(conn)
        import_users(conn)
        import_orders(conn)
        import_order_items(conn)
        import_reviews(conn)
        import_interactions(conn, sample_limit=50000)
        
        print("\nAll datasets successfully imported into Oracle Database 26ai!")
        cur = conn.cursor()
        print("\nFinal row count verification in Oracle:")
        for tbl in ["PRODUCTS", "USERS", "ORDERS", "ORDER_ITEMS", "REVIEWS", "INTERACTIONS"]:
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            count = cur.fetchone()[0]
            print(f" - {tbl}: {count:,} rows")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
