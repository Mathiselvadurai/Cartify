from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.db import query_db, execute_db, get_connection
from app.security import validate_csrf

cart_bp = Blueprint("cart", __name__)

def calculate_cart_totals(cart, coupon_code=""):
    subtotal = sum(float(item["price"]) * int(item["quantity"]) for item in cart.values())
    
    # Coupon Discount logic
    discount = 0.0
    code = (coupon_code or "").strip().upper()
    if code in ("WELCOME10", "CARTIFY10"):
        discount = subtotal * 0.10
    elif code == "FESTIVE15":
        discount = subtotal * 0.15
    elif code == "SAVE20":
        discount = subtotal * 0.20
    elif code == "FLAT100":
        discount = min(100.0, subtotal)
        
    # Free shipping on orders over 999
    shipping = 0.0 if (subtotal >= 999 or subtotal == 0) else 99.0
    total = max(0.0, subtotal - discount + shipping)
    
    return {
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "shipping": round(shipping, 2),
        "total": round(total, 2),
        "coupon_code": code
    }

@cart_bp.route("/cart")
def view_cart():
    cart = session.get("cart", {})
    coupon = session.get("coupon_code", "")
    totals = calculate_cart_totals(cart, coupon)
    return render_template("cart.html", cart=cart, totals=totals)

@cart_bp.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    if not validate_csrf():
        if request.is_json or request.headers.get("Accept") == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Invalid CSRF token", "code": "CSRF_ERROR"}), 403
        flash("Session security token expired. Please try again.", "danger")
        return redirect(request.referrer or url_for("cart.view_cart"))

    try:
        quantity = max(1, int(request.form.get("quantity", 1)))
    except (ValueError, TypeError):
        quantity = 1
    
    # Fetch product details from Oracle
    sql = "SELECT product_id, product_name, brand, sale_price_inr, price_inr, image_url, stock_quantity FROM products WHERE product_id = :1"
    product = query_db(sql, (product_id,), one=True)
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("main.products"))
        
    cart = session.get("cart", {})
    pid_str = str(product_id)
    price = float(product["sale_price_inr"] or product["price_inr"] or 0)
    
    if pid_str in cart:
        cart[pid_str]["quantity"] += quantity
    else:
        cart[pid_str] = {
            "id": product["product_id"],
            "name": product["product_name"],
            "brand": product["brand"],
            "price": price,
            "image_url": product["image_url"],
            "quantity": quantity
        }
        
    session["cart"] = cart
    session.modified = True
    
    # Record add_to_cart interaction in Oracle if user is logged in
    user = session.get("user")
    if user:
        try:
            inter_sql = """
                INSERT INTO interactions (
                    interaction_id, user_id, product_id, event_type, event_timestamp, device_type
                ) VALUES (
                    seq_interaction_id.NEXTVAL, :1, :2, 'add_to_cart', SYSTIMESTAMP, 'Web'
                )
            """
            execute_db(inter_sql, (user["id"], product_id))
        except Exception as e:
            print(f"Error logging cart interaction: {e}")
            
    flash(f"Added {product['product_name']} to your cart!", "success")
    return redirect(request.referrer or url_for("cart.view_cart"))

@cart_bp.route("/cart/update", methods=["POST"])
def update_cart():
    if not validate_csrf():
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"error": "Invalid CSRF token", "code": "CSRF_ERROR"}), 403
        flash("Session security token expired. Please try again.", "danger")
        return redirect(url_for("cart.view_cart"))

    cart = session.get("cart", {})
    action = request.form.get("action")
    
    if action == "clear":
        session.pop("cart", None)
        session.pop("coupon_code", None)
        session.modified = True
        flash("Your shopping cart has been cleared.", "info")
        return redirect(url_for("cart.view_cart"))

    product_id = str(request.form.get("product_id"))
    
    if product_id in cart:
        if action == "increase":
            cart[product_id]["quantity"] += 1
        elif action == "decrease":
            cart[product_id]["quantity"] -= 1
            if cart[product_id]["quantity"] <= 0:
                del cart[product_id]
        elif action == "remove":
            del cart[product_id]
        elif action == "set":
            try:
                new_qty = int(request.form.get("quantity", 1))
                if new_qty <= 0:
                    del cart[product_id]
                else:
                    cart[product_id]["quantity"] = new_qty
            except (ValueError, TypeError):
                pass
            
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart.view_cart"))

@cart_bp.route("/cart/apply-coupon", methods=["POST"])
def apply_coupon():
    if not validate_csrf():
        flash("Session security token expired. Please try again.", "danger")
        return redirect(url_for("cart.view_cart"))

    coupon = request.form.get("coupon_code", "").strip().upper()
    valid_coupons = ["WELCOME10", "CARTIFY10", "FESTIVE15", "SAVE20", "FLAT100"]
    if coupon in valid_coupons:
        session["coupon_code"] = coupon
        flash(f"Coupon '{coupon}' applied successfully!", "success")
    else:
        flash(f"Invalid coupon code '{coupon}'. Try CARTIFY10 or FESTIVE15", "warning")
    return redirect(url_for("cart.view_cart"))

@cart_bp.route("/cart/remove-coupon", methods=["GET", "POST"])
def remove_coupon():
    # Enforce CSRF protection on state mutation: GET requests are safely rejected from modifying session state
    if request.method == "GET":
        flash("Coupon removal requires a secure form submission.", "warning")
        return redirect(url_for("cart.view_cart"))

    if not validate_csrf():
        flash("Session security token expired. Please try again.", "danger")
        return redirect(url_for("cart.view_cart"))

    session.pop("coupon_code", None)
    session.modified = True
    flash("Coupon removed successfully.", "info")
    return redirect(url_for("cart.view_cart"))

@cart_bp.route("/checkout", methods=["GET"])
def checkout():
    user = session.get("user")
    if not user:
        flash("Please log in to proceed to checkout.", "warning")
        return redirect(url_for("auth.login", next=url_for("cart.checkout")))
        
    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty.", "info")
        return redirect(url_for("main.products"))
        
    coupon = session.get("coupon_code", "")
    totals = calculate_cart_totals(cart, coupon)
    
    # Pre-fetch user details for shipping address from Oracle
    user_data = query_db("SELECT first_name, last_name, email, city, state FROM users WHERE user_id = :1", (user["id"],), one=True)
    
    return render_template("checkout.html", cart=cart, totals=totals, user=user_data)

@cart_bp.route("/checkout/place_order", methods=["POST"])
def place_order():
    if not validate_csrf():
        flash("Session security token expired. Please try again.", "danger")
        return redirect(url_for("cart.view_cart"))

    user = session.get("user")
    if not user:
        flash("Please log in to complete your order.", "danger")
        return redirect(url_for("auth.login"))
        
    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("main.products"))

    # 1. Quantity Validation & Product ID Aggregation (Handles duplicates & rejects invalid values)
    aggregated = {}
    for item in cart.values():
        try:
            pid = int(item["id"])
            qty = int(item["quantity"])
            if qty <= 0:
                flash("Invalid product quantity in cart.", "danger")
                return redirect(url_for("cart.view_cart"))
        except (ValueError, TypeError, KeyError):
            flash("Invalid product quantity in cart.", "danger")
            return redirect(url_for("cart.view_cart"))

        if pid not in aggregated:
            aggregated[pid] = {
                "id": pid,
                "name": item.get("name", f"Product #{pid}"),
                "brand": item.get("brand", "Cartify"),
                "price": float(item.get("price", 0.0)),
                "quantity": 0
            }
        aggregated[pid]["quantity"] += qty

    if not aggregated:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("main.products"))

    coupon = session.get("coupon_code", "")
    totals = calculate_cart_totals(cart, coupon)
    
    payment_method = request.form.get("payment_method", "Credit/Debit Card")
    city = request.form.get("city", "Mumbai").strip()
    state = request.form.get("state", "Maharashtra").strip()
    delivery_date = (datetime.now() + timedelta(days=4)).date()

    # 2. Deterministic product-ID order to eliminate deadlock risk in concurrent checkouts
    sorted_pids = sorted(aggregated.keys())
    
    # 3. Perform atomic transaction in Oracle Database 26ai (Single Session)
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Step A: Conditional stock decrement
        # Atomically decreases stock ONLY IF product is active and sufficient stock exists
        stock_update_sql = """
            UPDATE products
            SET stock_quantity = stock_quantity - :1,
                sales_count = sales_count + :2
            WHERE product_id = :3
              AND is_active = 1
              AND stock_quantity >= :4
        """
        for pid in sorted_pids:
            item = aggregated[pid]
            qty = item["quantity"]
            cur.execute(stock_update_sql, (qty, qty, pid, qty))
            if cur.rowcount == 0:
                conn.rollback()
                # Query state to present precise message to customer
                cur.execute("SELECT product_name, stock_quantity, is_active FROM products WHERE product_id = :1", (pid,))
                check_row = cur.fetchone()
                if not check_row or check_row[2] != 1:
                    flash(f"Item '{item['name']}' is currently unavailable.", "warning")
                else:
                    avail = check_row[1]
                    flash(f"Insufficient stock for '{check_row[0]}'. Only {avail} units available.", "warning")
                return redirect(url_for("cart.view_cart"))

        # Step B: Get next order ID from Oracle sequence
        cur.execute("SELECT seq_order_id.NEXTVAL FROM dual")
        order_id = cur.fetchone()[0]
        
        # Step C: Insert into ORDERS table
        num_items = sum(item["quantity"] for item in aggregated.values())
        order_sql = """
            INSERT INTO orders (
                order_id, user_id, order_date, order_status, payment_method,
                coupon_code, num_items, subtotal, discount_amount, shipping_fee,
                total_amount, shipping_city, shipping_state, delivery_date
            ) VALUES (
                :1, :2, SYSTIMESTAMP, 'Confirmed', :3,
                :4, :5, :6, :7, :8,
                :9, :10, :11, :12
            )
        """
        cur.execute(order_sql, (
            order_id, user["id"], payment_method,
            coupon, num_items, totals["subtotal"], totals["discount"], totals["shipping"],
            totals["total"], city, state, delivery_date
        ))
        
        # Step D: Insert into ORDER_ITEMS and record 'purchase' interactions
        item_sql = """
            INSERT INTO order_items (
                order_item_id, order_id, product_id, quantity, unit_price, line_total
            ) VALUES (
                seq_order_item_id.NEXTVAL, :1, :2, :3, :4, :5
            )
        """
        inter_sql = """
            INSERT INTO interactions (
                interaction_id, user_id, product_id, event_type, event_timestamp, device_type, order_id
            ) VALUES (
                seq_interaction_id.NEXTVAL, :1, :2, 'purchase', SYSTIMESTAMP, 'Web', :3
            )
        """
        for pid in sorted_pids:
            item = aggregated[pid]
            line_total = round(item["price"] * item["quantity"], 2)
            cur.execute(item_sql, (order_id, pid, item["quantity"], item["price"], line_total))
            cur.execute(inter_sql, (user["id"], pid, order_id))
            
        # Step E: Commit atomic transaction only after every step succeeded
        conn.commit()
        
        # Step F: Clear cart and coupon upon successful order
        session.pop("cart", None)
        session.pop("coupon_code", None)
        session.modified = True
        
        flash(f"Order #{order_id} placed successfully!", "success")
        return redirect(url_for("cart.order_success", order_id=order_id))
        
    except Exception as e:
        conn.rollback()
        flash(f"An error occurred while placing your order: {str(e)}", "danger")
        return redirect(url_for("cart.view_cart"))
    finally:
        cur.close()
        conn.close()

@cart_bp.route("/order_success/<int:order_id>")
@cart_bp.route("/order/<int:order_id>")
def order_success(order_id):
    order = query_db("SELECT * FROM orders WHERE order_id = :1", (order_id,), one=True)
    if not order:
        flash("Order not found.", "danger")
        return redirect(url_for("main.index"))
        
    # Privacy & IDOR Guard: Verify order belongs to current user or authorized admin/evaluator
    user = session.get("user")
    if not user:
        flash("Please log in to view order details.", "warning")
        return redirect(url_for("auth.login"))
    if order.get("user_id") != user["id"] and not (session.get("is_admin") or session.get("is_evaluator")):
        flash("You do not have permission to view this order confirmation.", "danger")
        return redirect(url_for("main.index"))
        
    items = query_db("""
        SELECT oi.*, p.product_name, p.brand, p.image_url
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = :1
    """, (order_id,))
    
    return render_template("order_success.html", order=order, items=items)

@cart_bp.route("/my-orders")
def my_orders():
    user = session.get("user")
    if not user:
        flash("Please log in to view your order history.", "warning")
        return redirect(url_for("auth.login"))
        
    orders = query_db("""
        SELECT * FROM orders 
        WHERE user_id = :1 
        ORDER BY order_date DESC
    """, (user["id"],))
    
    return render_template("orders.html", orders=orders)


@cart_bp.route("/order/<int:order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    """
    Customer-initiated pre-shipment order cancellation.
    Restores reserved product stock atomically in a single Oracle transaction.
    """
    user = session.get("user")
    if not user:
        if request.is_json:
            return jsonify({"success": False, "error": "Authentication required", "code": "AUTH_REQUIRED"}), 401
        flash("Please log in to manage your orders.", "warning")
        return redirect(url_for("auth.login"))

    if not validate_csrf():
        if request.is_json:
            return jsonify({"success": False, "error": "Security token expired", "code": "CSRF_ERROR"}), 400
        flash("Session security token expired. Please try again.", "danger")
        return redirect(url_for("cart.order_success", order_id=order_id))

    from app.services.order_service import cancel_order_and_restore_stock
    result, status_code = cancel_order_and_restore_stock(order_id, actor_type="customer", actor_id=user["id"])

    if request.is_json:
        return jsonify(result), status_code

    if result.get("success"):
        flash("Your order has been cancelled and reserved items restored.", "success")
    else:
        flash(result.get("error", "Failed to cancel order."), "danger")

    return redirect(url_for("cart.order_success", order_id=order_id))
