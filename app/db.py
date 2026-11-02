import os
import oracledb
from dotenv import load_dotenv

load_dotenv()

USER = os.getenv("ORACLE_USER", "ecomm_user")
PASSWORD = os.getenv("ORACLE_PASSWORD")
if not PASSWORD:
    raise RuntimeError("Set ORACLE_PASSWORD in .env before connecting")
DSN = os.getenv("ORACLE_DSN", "localhost:1521/freepdb1")

def get_db():
    """
    Returns an active Oracle connection.
    Thin mode is used by default in python-oracledb.
    """
    conn = oracledb.connect(user=USER, password=PASSWORD, dsn=DSN)
    return conn

# Alias for compatibility
get_connection = get_db

def query_db(query, args=(), one=False):
    """
    Helper function to query Oracle and return results as Python dictionaries.
    Column names are returned in lower_case for template friendliness.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(query, args)
        if cursor.description is None:
            conn.commit()
            return None
        
        columns = [col[0].lower() for col in cursor.description]
        rows = cursor.fetchall()
        result = [dict(zip(columns, row)) for row in rows]
        return (result[0] if result else None) if one else result
    finally:
        cursor.close()
        conn.close()

def execute_db(query, args=(), commit=True):
    """
    Helper function to execute INSERT/UPDATE/DELETE.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(query, args)
        if commit:
            conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()
