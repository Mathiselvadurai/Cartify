"""
Order Service for Cartify E-Commerce System.
Provides transactional order operations including concurrency-safe order cancellation
and inventory restoration for pre-shipment orders.
"""

from app.db import get_db

VALID_ORDER_STATUSES = ["Confirmed", "Processing", "Shipped", "Delivered", "Cancelled", "Returned"]

ALLOWED_STATUS_TRANSITIONS = {
    "Confirmed": {"Processing", "Cancelled"},
    "Processing": {"Shipped", "Cancelled"},
    "Shipped": {"Delivered", "Returned"},
    "Delivered": {"Returned"},
    "Cancelled": set(),  # Terminal state
    "Returned": set(),   # Terminal state
}

def cancel_order_and_restore_stock(order_id, actor_type="owner", actor_id=None):
    """
    Cancels an order before shipment and restores reserved stock exactly once.
    Operates inside an isolated Oracle transaction with row-level locking (FOR UPDATE).
    
    Guarantees:
    - Atomicity: Status transition and stock restoration commit together or roll back together.
    - Concurrency Safety: Row locking on the order prevents double-restoration from concurrent requests.
    - State Machine Enforcement: Only Confirmed and Processing orders can be cancelled.
    - Ownership Preservation: If actor_type == 'customer', verifies order belongs to actor_id.
    - Returns policy: Never restores stock automatically for Shipped or Delivered orders transitioning to Returned.
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. Lock the order row to serialize concurrent cancellation requests
        cursor.execute("""
            SELECT order_id, user_id, order_status 
            FROM orders 
            WHERE order_id = :1 
            FOR UPDATE
        """, (order_id,))
        order_row = cursor.fetchone()
        
        if not order_row:
            conn.rollback()
            return {"success": False, "error": f"Order #{order_id} not found", "code": "NOT_FOUND"}, 404
            
        current_status = order_row[2]
        owner_id = order_row[1]
        
        # 2. Authorization / Ownership check
        if actor_type == "customer" and actor_id != owner_id:
            conn.rollback()
            return {"success": False, "error": "Access denied. You do not own this order.", "code": "FORBIDDEN"}, 403

        # 3. Check for already cancelled (idempotency / repeat protection)
        if current_status == "Cancelled":
            conn.rollback()
            return {"success": False, "error": f"Order #{order_id} is already Cancelled. Stock has already been restored.", "code": "ALREADY_CANCELLED"}, 400

        # 4. State validation: only pre-shipment states can be cancelled
        if current_status not in ("Confirmed", "Processing"):
            conn.rollback()
            return {
                "success": False, 
                "error": f"Cannot cancel order in status '{current_status}'. Only pre-shipment orders (Confirmed, Processing) can be cancelled.", 
                "code": "INVALID_STATE"
            }, 400

        # 5. Retrieve line items to restore reserved inventory
        cursor.execute("""
            SELECT product_id, quantity 
            FROM order_items 
            WHERE order_id = :1
        """, (order_id,))
        items = cursor.fetchall()

        # 6. Restore stock for each product atomically
        for p_id, qty in items:
            cursor.execute("""
                UPDATE products 
                SET stock_quantity = stock_quantity + :1 
                WHERE product_id = :2
            """, (qty, p_id))

        # 7. Update order status to Cancelled
        cursor.execute("""
            UPDATE orders 
            SET order_status = 'Cancelled' 
            WHERE order_id = :1
        """, (order_id,))

        conn.commit()
        return {
            "success": True, 
            "order_id": order_id, 
            "previous_status": current_status, 
            "new_status": "Cancelled", 
            "restored_items_count": len(items),
            "message": f"Order #{order_id} successfully cancelled. Reserved inventory restored to catalog."
        }, 200

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e), "code": "SERVER_ERROR"}, 500
    finally:
        cursor.close()
        conn.close()


def transition_order_status(order_id, new_status, actor_type="owner", actor_id=None):
    """
    Executes validated order status transitions.
    If transitioning to 'Cancelled', delegates to cancel_order_and_restore_stock.
    Otherwise, executes serialized transition with FOR UPDATE row locking without modifying inventory.
    """
    if new_status not in VALID_ORDER_STATUSES:
        return {"success": False, "error": f"Unsupported order status '{new_status}'.", "code": "INVALID_STATUS"}, 400

    if new_status == "Cancelled":
        return cancel_order_and_restore_stock(order_id, actor_type=actor_type, actor_id=actor_id)

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Lock order row
        cursor.execute("""
            SELECT order_id, user_id, order_status 
            FROM orders 
            WHERE order_id = :1 
            FOR UPDATE
        """, (order_id,))
        order_row = cursor.fetchone()
        
        if not order_row:
            conn.rollback()
            return {"success": False, "error": f"Order #{order_id} not found", "code": "NOT_FOUND"}, 404

        current_status = order_row[2]
        owner_id = order_row[1]

        if actor_type == "customer" and actor_id != owner_id:
            conn.rollback()
            return {"success": False, "error": "Access denied.", "code": "FORBIDDEN"}, 403

        if current_status.lower() == new_status.lower():
            conn.rollback()
            return {"success": True, "order_id": order_id, "status": new_status, "message": "Status unchanged"}, 200

        allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            conn.rollback()
            return {
                "success": False,
                "error": f"Invalid status transition from '{current_status}' to '{new_status}'. Allowed next states: {', '.join(allowed) if allowed else 'None (Terminal state)'}.",
                "code": "INVALID_TRANSITION"
            }, 400

        # Update order status without modifying stock
        cursor.execute("""
            UPDATE orders 
            SET order_status = :1 
            WHERE order_id = :2
        """, (new_status, order_id))

        conn.commit()
        return {
            "success": True, 
            "order_id": order_id, 
            "previous_status": current_status, 
            "new_status": new_status, 
            "message": f"Order #{order_id} status transitioned from '{current_status}' to '{new_status}'."
        }, 200

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e), "code": "SERVER_ERROR"}, 500
    finally:
        cursor.close()
        conn.close()
