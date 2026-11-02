from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import query_db, execute_db
from app.security import login_required, validate_csrf

auth_bp = Blueprint("auth", __name__)

def get_demo_users():
    """Fetch seeded demo users from Oracle Database 26ai for presentation / viva demo."""
    return query_db("""
        SELECT user_id, first_name, last_name, email, city, membership_tier
        FROM users
        WHERE ROWNUM <= 4
        ORDER BY user_id ASC
    """)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    demo_users = get_demo_users()
    if request.method == "POST":
        if not validate_csrf():
            flash("Session security token expired. Please try again.", "danger")
            return render_template("login.html", demo_users=demo_users)

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html", demo_users=demo_users)

        sql = """
            SELECT user_id, first_name, last_name, email, password_hash, membership_tier
            FROM users
            WHERE LOWER(email) = :1
        """
        user = query_db(sql, (email,), one=True)

        if user and check_password_hash(user["password_hash"], password):
            session["user"] = {
                "id": user["user_id"],
                "name": f"{user['first_name']} {user['last_name']}",
                "email": user["email"],
                "tier": user["membership_tier"]
            }
            # Synchronize active wishlist for this customer
            sync_user_wishlist(user["user_id"])

            flash(f"Welcome back, {user['first_name']}!", "success")
            next_url = request.args.get("next") or url_for("main.index")
            return redirect(next_url)
        else:
            flash("Invalid email or password. (Hint: Default password for seeded users is 'password123')", "danger")

    return render_template("login.html", demo_users=demo_users)

@auth_bp.route("/demo-login/<int:user_id>")
def demo_login(user_id):
    """Convenient 1-click login for viva/presentation demo."""
    sql = "SELECT user_id, first_name, last_name, email, membership_tier FROM users WHERE user_id = :1"
    user = query_db(sql, (user_id,), one=True)
    if user:
        session["user"] = {
            "id": user["user_id"],
            "name": f"{user['first_name']} {user['last_name']}",
            "email": user["email"],
            "tier": user["membership_tier"]
        }
        sync_user_wishlist(user["user_id"])
        flash(f"Logged in as Demo User: {user['first_name']} ({user['membership_tier'] or 'Standard'} Member)", "info")
    return redirect(url_for("main.index"))

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    demo_users = get_demo_users()
    if request.method == "POST":
        if not validate_csrf():
            flash("Session security token expired. Please try again.", "danger")
            return render_template("login.html", demo_users=demo_users, active_tab="register")

        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        gender = request.form.get("gender", "Unspecified")
        city = request.form.get("city", "Mumbai").strip()
        state = request.form.get("state", "Maharashtra").strip()

        if not first_name or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template("login.html", demo_users=demo_users, active_tab="register")

        if confirm_password and password != confirm_password:
            flash("Passwords do not match. Please re-enter.", "warning")
            return render_template("login.html", demo_users=demo_users, active_tab="register")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return render_template("login.html", demo_users=demo_users, active_tab="register")

        # Check if email already exists in Oracle DB
        existing = query_db("SELECT user_id FROM users WHERE LOWER(email) = :1", (email,), one=True)
        if existing:
            flash("An account with this email already exists. Please log in.", "warning")
            return render_template("login.html", demo_users=demo_users)

        pwd_hash = generate_password_hash(password)

        # Insert new user using Oracle sequence seq_user_id
        insert_sql = """
            INSERT INTO users (
                user_id, first_name, last_name, email, password_hash,
                gender, city, state, signup_date, membership_tier, is_active
            ) VALUES (
                seq_user_id.NEXTVAL, :1, :2, :3, :4, :5, :6, :7, TRUNC(SYSDATE), 'Standard', 1
            )
        """
        execute_db(insert_sql, (first_name, last_name, email, pwd_hash, gender, city, state))

        # Fetch created user
        new_user = query_db("SELECT user_id, first_name, last_name, email, membership_tier FROM users WHERE LOWER(email) = :1", (email,), one=True)
        session["user"] = {
            "id": new_user["user_id"],
            "name": f"{new_user['first_name']} {new_user['last_name']}",
            "email": new_user["email"],
            "tier": new_user["membership_tier"]
        }
        session["wishlist"] = []
        flash(f"Account successfully created! Welcome to Cartify, {first_name}.", "success")
        return redirect(url_for("main.index"))

    return redirect(url_for("auth.login"))

@auth_bp.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("wishlist", None)
    session.pop("is_evaluator", None)
    session.pop("is_admin", None)
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))

# ==============================================================================
# CUSTOMER PROFILE & WISHLIST CONTROLLER (Phase 3)
# ==============================================================================

def sync_user_wishlist(user_id):
    """Loads active wishlist product IDs from Oracle into session."""
    active_rows = query_db("""
        SELECT w.product_id
        FROM (
            SELECT product_id, event_type,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY event_timestamp DESC, interaction_id DESC) as rn
            FROM interactions
            WHERE user_id = :1 AND referrer = 'storefront_wishlist'
        ) w
        WHERE w.rn = 1 AND w.event_type = 'wishlist'
    """, (user_id,))
    session["wishlist"] = [r["product_id"] for r in active_rows]
    return session["wishlist"]

@auth_bp.route("/profile", methods=["GET"])
@login_required
def profile():
    """
    Customer Profile Command Center (Stitch Screen 11).
    Displays verified Oracle account information, recent order history with status stepper,
    and persistent active wishlist items.
    """
    user_session = session.get("user")
    user_id = user_session["id"]

    # 1. Fetch live customer profile from Oracle USERS table
    user_data = query_db("""
        SELECT user_id, first_name, last_name, email, city, state,
               membership_tier, gender,
               TO_CHAR(signup_date, 'Mon YYYY') as member_since
        FROM users
        WHERE user_id = :1
    """, (user_id,), one=True)

    if not user_data:
        flash("Customer profile record not found.", "danger")
        return redirect(url_for("auth.logout"))

    # 2. Lifetime Order Aggregations
    order_stats = query_db("""
        SELECT COUNT(order_id) as total_orders,
               NVL(SUM(total_amount), 0) as total_spent
        FROM orders
        WHERE user_id = :1
    """, (user_id,), one=True)

    active_orders_count = query_db("""
        SELECT COUNT(order_id) as cnt
        FROM orders
        WHERE user_id = :1 AND UPPER(order_status) IN ('PENDING', 'PROCESSING', 'CONFIRMED', 'SHIPPED')
    """, (user_id,), one=True)

    # 3. Recent Orders History (Latest 5 orders)
    recent_orders = query_db("""
        SELECT o.order_id,
               TO_CHAR(o.order_date, 'Mon DD, YYYY') as formatted_date,
               o.total_amount,
               o.order_status,
               o.payment_method,
               (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id) as item_count
        FROM orders o
        WHERE o.user_id = :1
        ORDER BY o.order_date DESC, o.order_id DESC
        FETCH FIRST 5 ROWS ONLY
    """, (user_id,))

    # 4. Most Recent Order for Active Delivery Progress Stepper
    active_order = None
    if recent_orders:
        active_order = recent_orders[0]
        # Fetch items preview for this order
        active_order_items = query_db("""
            SELECT oi.product_id, oi.quantity, oi.unit_price, p.product_name, p.image_url
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            WHERE oi.order_id = :1
            FETCH FIRST 3 ROWS ONLY
        """, (active_order["order_id"],))
        active_order["items_preview"] = active_order_items

    # 5. Persistent Active Wishlist Products
    # Strictly isolates active storefront items from historical recommendation telemetry
    wishlist_products = query_db("""
        SELECT p.product_id, p.product_name, p.brand, p.category, p.subcategory,
               p.price_inr, p.sale_price_inr, p.discount_percent, p.image_url,
               p.rating, p.review_count, p.stock_quantity
        FROM (
            SELECT product_id, event_type,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY event_timestamp DESC, interaction_id DESC) as rn
            FROM interactions
            WHERE user_id = :1 AND referrer = 'storefront_wishlist'
        ) w
        JOIN products p ON w.product_id = p.product_id
        WHERE w.rn = 1 AND w.event_type = 'wishlist' AND p.is_active = 1
        ORDER BY p.product_name ASC
    """, (user_id,))

    # Synchronize session wishlist cache
    session["wishlist"] = [p["product_id"] for p in wishlist_products]

    return render_template(
        "profile.html",
        user=user_data,
        order_stats=order_stats,
        active_orders_count=active_orders_count["cnt"] if active_orders_count else 0,
        recent_orders=recent_orders,
        active_order=active_order,
        wishlist_products=wishlist_products
    )

@auth_bp.route("/wishlist/toggle/<int:product_id>", methods=["POST"])
@login_required
def wishlist_toggle(product_id):
    """
    Toggles a product's presence in the customer's active wishlist.
    Guarantees:
      1. Prevents duplicate active entries.
      2. Appends 'wishlist' or 'wishlist_remove' event with referrer='storefront_wishlist'.
      3. Preserves all historical recommendation telemetry intact.
      4. Validates product exists and is active.
      5. Validates CSRF token.
    """
    if not validate_csrf():
        if request.is_json or request.headers.get("Accept") == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Invalid CSRF token", "code": "CSRF_ERROR"}), 403
        flash("Session security token expired. Please try again.", "danger")
        return redirect(request.referrer or url_for("auth.profile"))

    # Validate product exists
    product = query_db("SELECT product_id, product_name, is_active FROM products WHERE product_id = :1", (product_id,), one=True)
    if not product or product.get("is_active") == 0:
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"error": "Product not found or inactive", "code": "NOT_FOUND"}), 404
        flash("Product could not be found or is no longer active.", "danger")
        return redirect(request.referrer or url_for("auth.profile"))

    user_id = session["user"]["id"]

    # Check current active state in Oracle
    latest = query_db("""
        SELECT event_type
        FROM (
            SELECT event_type,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY event_timestamp DESC, interaction_id DESC) as rn
            FROM interactions
            WHERE user_id = :1 AND product_id = :2 AND referrer = 'storefront_wishlist'
        )
        WHERE rn = 1
    """, (user_id, product_id), one=True)

    is_currently_active = latest and latest.get("event_type") == "wishlist"

    if is_currently_active:
        # Action: Remove from active wishlist
        execute_db("""
            INSERT INTO interactions (
                interaction_id, user_id, product_id, event_type, referrer, event_timestamp
            ) VALUES (
                seq_interaction_id.NEXTVAL, :1, :2, :3, :4, CURRENT_TIMESTAMP
            )
        """, (user_id, product_id, "wishlist_remove", "storefront_wishlist"))
        action = "removed"
        active = False
        msg = f"Removed '{product['product_name']}' from your wishlist."
    else:
        # Action: Add to active wishlist (prevents duplicate active state)
        execute_db("""
            INSERT INTO interactions (
                interaction_id, user_id, product_id, event_type, referrer, event_timestamp
            ) VALUES (
                seq_interaction_id.NEXTVAL, :1, :2, :3, :4, CURRENT_TIMESTAMP
            )
        """, (user_id, product_id, "wishlist", "storefront_wishlist"))
        action = "added"
        active = True
        msg = f"Added '{product['product_name']}' to your wishlist!"

    # Refresh session cache
    sync_user_wishlist(user_id)
    new_count = len(session.get("wishlist", []))

    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({
            "success": True,
            "action": action,
            "active": active,
            "product_id": product_id,
            "wishlist_count": new_count,
            "message": msg
        })

    flash(msg, "info" if not active else "success")
    return redirect(request.referrer or url_for("auth.profile"))

@auth_bp.route("/wishlist/remove/<int:product_id>", methods=["POST"])
@login_required
def wishlist_remove(product_id):
    """Explicitly removes a product from the active wishlist."""
    if not validate_csrf():
        if request.is_json or request.headers.get("Accept") == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Invalid CSRF token", "code": "CSRF_ERROR"}), 403
        flash("Session security token expired. Please try again.", "danger")
        return redirect(url_for("auth.profile"))

    user_id = session["user"]["id"]
    execute_db("""
        INSERT INTO interactions (
            interaction_id, user_id, product_id, event_type, referrer, event_timestamp
        ) VALUES (
            seq_interaction_id.NEXTVAL, :1, :2, :3, :4, CURRENT_TIMESTAMP
        )
    """, (user_id, product_id, "wishlist_remove", "storefront_wishlist"))

    sync_user_wishlist(user_id)
    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({"success": True, "action": "removed", "product_id": product_id})

    flash("Item removed from your wishlist.", "info")
    return redirect(request.referrer or url_for("auth.profile"))

@auth_bp.route("/wishlist/add/<int:product_id>", methods=["POST"])
@login_required
def wishlist_add(product_id):
    """Explicitly adds a product to the active wishlist, avoiding duplicates."""
    if not validate_csrf():
        if request.is_json or request.headers.get("Accept") == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": "Invalid CSRF token", "code": "CSRF_ERROR"}), 403
        flash("Session security token expired. Please try again.", "danger")
        return redirect(request.referrer or url_for("main.products"))

    product = query_db("SELECT product_id, product_name FROM products WHERE product_id = :1 AND is_active = 1", (product_id,), one=True)
    if not product:
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"error": "Product not found or inactive", "code": "NOT_FOUND"}), 404
        flash("Product not found.", "danger")
        return redirect(request.referrer or url_for("main.products"))

    user_id = session["user"]["id"]

    # Check if already in active wishlist
    latest = query_db("""
        SELECT event_type
        FROM (
            SELECT event_type,
                   ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY event_timestamp DESC, interaction_id DESC) as rn
            FROM interactions
            WHERE user_id = :1 AND product_id = :2 AND referrer = 'storefront_wishlist'
        )
        WHERE rn = 1
    """, (user_id, product_id), one=True)

    if latest and latest.get("event_type") == "wishlist":
        msg = f"'{product['product_name']}' is already in your wishlist."
        already_active = True
    else:
        execute_db("""
            INSERT INTO interactions (
                interaction_id, user_id, product_id, event_type, referrer, event_timestamp
            ) VALUES (
                seq_interaction_id.NEXTVAL, :1, :2, :3, :4, CURRENT_TIMESTAMP
            )
        """, (user_id, product_id, "wishlist", "storefront_wishlist"))
        msg = f"Added '{product['product_name']}' to your wishlist!"
        already_active = False

    sync_user_wishlist(user_id)
    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({
            "success": True,
            "action": "already_active" if already_active else "added",
            "active": True,
            "product_id": product_id,
            "message": msg
        })

    flash(msg, "info" if already_active else "success")
    return redirect(request.referrer or url_for("auth.profile"))
