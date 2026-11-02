"""
Store Owner Management Routes & Operations Controller (Phase 7).
Provides role-authorized access to real-time Oracle Database 26ai commerce metrics,
inventory management, product lifecycle administration, and order fulfillment.
"""

from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify, abort
from app.db import query_db, execute_db
from app.security import owner_required, is_store_owner, validate_csrf
import math

owner_bp = Blueprint("owner", __name__, url_prefix="/owner")

LOW_STOCK_THRESHOLD = 35

VALID_ORDER_STATUSES = ["Confirmed", "Processing", "Shipped", "Delivered", "Cancelled", "Returned"]

ALLOWED_STATUS_TRANSITIONS = {
    "Confirmed": {"Processing", "Cancelled"},
    "Processing": {"Shipped", "Cancelled"},
    "Shipped": {"Delivered", "Returned"},
    "Delivered": {"Returned"},
    "Cancelled": set(),  # Terminal
    "Returned": set(),   # Terminal
}


# ==============================================================================
# Screen 2: Store Owner Executive Dashboard
# ==============================================================================

@owner_bp.route("/")
@owner_bp.route("/dashboard")
@owner_required
def dashboard():
    """
    Renders the executive Store Owner Dashboard (Stitch Screen 2).
    Aggregates real Oracle Database 26ai performance metrics, stock alerts, and sales volume.
    """
    # 1. Core Summary Metrics
    total_products_row = query_db("SELECT COUNT(*) as c FROM products", one=True)
    total_products = total_products_row["c"] if total_products_row else 0

    active_products_row = query_db("SELECT COUNT(*) as c FROM products WHERE is_active = 1", one=True)
    active_products = active_products_row["c"] if active_products_row else 0

    total_orders_row = query_db("SELECT COUNT(*) as c FROM orders", one=True)
    total_orders = total_orders_row["c"] if total_orders_row else 0

    revenue_row = query_db("SELECT COALESCE(SUM(total_amount), 0) as rev, COALESCE(AVG(total_amount), 0) as aov FROM orders", one=True)
    total_revenue = float(revenue_row["rev"]) if revenue_row else 0.0
    avg_order_value = float(revenue_row["aov"]) if revenue_row else 0.0

    warehouse_units_row = query_db("SELECT COALESCE(SUM(stock_quantity), 0) as units FROM products", one=True)
    total_warehouse_units = warehouse_units_row["units"] if warehouse_units_row else 0

    # Mutually exclusive stock health classification:
    # 1. Healthy: is_active = 1 and stock_quantity > threshold
    healthy_stock_row = query_db("SELECT COUNT(*) as c FROM products WHERE is_active = 1 AND stock_quantity > :1", (LOW_STOCK_THRESHOLD,), one=True)
    healthy_stock_count = healthy_stock_row["c"] if healthy_stock_row else 0

    # 2. Low Stock: is_active = 1 and stock_quantity > 0 and stock_quantity <= threshold
    low_stock_count_row = query_db("SELECT COUNT(*) as c FROM products WHERE is_active = 1 AND stock_quantity > 0 AND stock_quantity <= :1", (LOW_STOCK_THRESHOLD,), one=True)
    low_stock_count = low_stock_count_row["c"] if low_stock_count_row else 0

    # 3. Active Zero Stock: is_active = 1 and stock_quantity = 0
    zero_stock_active_row = query_db("SELECT COUNT(*) as c FROM products WHERE is_active = 1 AND stock_quantity = 0", one=True)
    zero_stock_active_count = zero_stock_active_row["c"] if zero_stock_active_row else 0

    # 4. Inactive SKUs: is_active = 0
    inactive_products_row = query_db("SELECT COUNT(*) as c FROM products WHERE is_active = 0", one=True)
    inactive_products_count = inactive_products_row["c"] if inactive_products_row else 0

    # Out of Stock (total quantity = 0 across all items)
    out_of_stock_row = query_db("SELECT COUNT(*) as c FROM products WHERE stock_quantity = 0", one=True)
    out_of_stock_count = out_of_stock_row["c"] if out_of_stock_row else 0

    # 2. Critical Stock Vigilance Items (Safety Threshold <= 35)
    low_stock_sql = """
        SELECT product_id, product_name, brand, category, stock_quantity, price_inr, image_url
        FROM products
        WHERE is_active = 1 AND stock_quantity <= :1
        ORDER BY stock_quantity ASC, product_name ASC
        FETCH FIRST 6 ROWS ONLY
    """
    low_stock_items = query_db(low_stock_sql, (LOW_STOCK_THRESHOLD,)) or []

    # 3. Recent Real Commerce Transactions
    recent_orders_sql = """
        SELECT o.order_id, o.user_id, o.order_date, o.order_status, o.total_amount, o.num_items,
               u.first_name, u.last_name, u.email
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        ORDER BY o.order_date DESC, o.order_id DESC
        FETCH FIRST 8 ROWS ONLY
    """
    recent_orders = query_db(recent_orders_sql) or []

    # 4. Order Status Distribution (For Donut Chart)
    status_distribution = query_db("""
        SELECT order_status, COUNT(*) as count
        FROM orders
        GROUP BY order_status
        ORDER BY count DESC
    """) or []

    # 5. Monthly Sales & Order Velocity (Past 12 Months)
    monthly_trend = query_db("""
        SELECT TO_CHAR(order_date, 'YYYY-MM') as month,
               COUNT(*) as orders_count,
               ROUND(SUM(total_amount), 2) as revenue
        FROM orders
        WHERE order_date IS NOT NULL
        GROUP BY TO_CHAR(order_date, 'YYYY-MM')
        ORDER BY month ASC
        FETCH FIRST 12 ROWS ONLY
    """) or []

    # 6. Top Catalog Categories by Sales Volume
    top_categories = query_db("""
        SELECT category, COUNT(*) as product_count, SUM(sales_count) as total_sales
        FROM products
        WHERE is_active = 1
        GROUP BY category
        ORDER BY total_sales DESC
        FETCH FIRST 6 ROWS ONLY
    """) or []

    metrics = {
        "total_products": total_products,
        "active_products": active_products,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "avg_order_value": avg_order_value,
        "total_warehouse_units": total_warehouse_units,
        "healthy_stock_count": healthy_stock_count,
        "low_stock_count": low_stock_count,
        "zero_stock_active_count": zero_stock_active_count,
        "inactive_products_count": inactive_products_count,
        "out_of_stock_count": out_of_stock_count,
        "low_stock_threshold": LOW_STOCK_THRESHOLD
    }

    return render_template(
        "owner/dashboard.html",
        active_page="dashboard",
        metrics=metrics,
        low_stock_items=low_stock_items,
        recent_orders=recent_orders,
        status_distribution=status_distribution,
        monthly_trend=monthly_trend,
        top_categories=top_categories
    )


# ==============================================================================
# Screen 5: Store Owner Inventory Management
# ==============================================================================

@owner_bp.route("/inventory")
@owner_required
def inventory():
    """
    Renders Screen 5: Inventory Management.
    Provides real-time stock listing, product search, taxonomy filters, and low-stock vigilance.
    """
    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all").strip().lower()
    category_filter = request.args.get("category", "").strip()
    brand_filter = request.args.get("brand", "").strip()
    sort_by = request.args.get("sort", "stock_asc").strip().lower()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 25
    offset = (page - 1) * per_page

    # 1. Summary KPI cards for inventory
    total_skus = query_db("SELECT COUNT(*) as c FROM products", one=True)["c"]
    in_stock_count = query_db("SELECT COUNT(*) as c FROM products WHERE is_active = 1 AND stock_quantity > :1", (LOW_STOCK_THRESHOLD,), one=True)["c"]
    low_stock_count = query_db("SELECT COUNT(*) as c FROM products WHERE is_active = 1 AND stock_quantity > 0 AND stock_quantity <= :1", (LOW_STOCK_THRESHOLD,), one=True)["c"]
    out_of_stock_count = query_db("SELECT COUNT(*) as c FROM products WHERE stock_quantity = 0", one=True)["c"]

    # 2. Build parameterized dynamic query
    where_clauses = ["1=1"]
    params = {}

    if search_query:
        # Check if search is numeric product_id or text
        if search_query.isdigit():
            where_clauses.append("(product_id = :p_id OR LOWER(product_name) LIKE :q OR LOWER(brand) LIKE :q)")
            params["p_id"] = int(search_query)
            params["q"] = f"%{search_query.lower()}%"
        else:
            where_clauses.append("(LOWER(product_name) LIKE :q OR LOWER(brand) LIKE :q)")
            params["q"] = f"%{search_query.lower()}%"

    if category_filter:
        where_clauses.append("category = :cat")
        params["cat"] = category_filter

    if brand_filter:
        where_clauses.append("brand = :brand")
        params["brand"] = brand_filter

    if status_filter == "in_stock":
        where_clauses.append("is_active = 1 AND stock_quantity > :thresh_high")
        params["thresh_high"] = LOW_STOCK_THRESHOLD
    elif status_filter == "low_stock":
        where_clauses.append("is_active = 1 AND stock_quantity > 0 AND stock_quantity <= :thresh_low")
        params["thresh_low"] = LOW_STOCK_THRESHOLD
    elif status_filter == "out_of_stock":
        where_clauses.append("stock_quantity = 0")
    elif status_filter == "inactive":
        where_clauses.append("is_active = 0")

    where_sql = " AND ".join(where_clauses)

    # Count matching items
    count_sql = f"SELECT COUNT(*) as c FROM products WHERE {where_sql}"
    total_matching = query_db(count_sql, params, one=True)["c"]
    total_pages = max(1, math.ceil(total_matching / per_page))

    # Order By Clause
    sort_mapping = {
        "stock_asc": "stock_quantity ASC, product_id ASC",
        "stock_desc": "stock_quantity DESC, product_id ASC",
        "price_asc": "price_inr ASC, product_id ASC",
        "price_desc": "price_inr DESC, product_id ASC",
        "id_asc": "product_id ASC",
        "id_desc": "product_id DESC",
        "name_asc": "product_name ASC",
    }
    order_clause = sort_mapping.get(sort_by, "stock_quantity ASC, product_id ASC")

    # Select matching items
    data_sql = f"""
        SELECT product_id, product_name, brand, category, subcategory, product_type,
               price_inr, sale_price_inr, stock_quantity, is_active, image_url
        FROM products
        WHERE {where_sql}
        ORDER BY {order_clause}
        OFFSET :offset ROWS FETCH NEXT :per_page ROWS ONLY
    """
    query_params = dict(params)
    query_params["offset"] = offset
    query_params["per_page"] = per_page
    inventory_items = query_db(data_sql, query_params) or []

    # Dropdown filter lists
    categories = query_db("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category ASC") or []
    top_brands = query_db("SELECT brand, COUNT(*) as c FROM products WHERE brand IS NOT NULL GROUP BY brand ORDER BY c DESC FETCH FIRST 20 ROWS ONLY") or []

    return render_template(
        "owner/inventory.html",
        active_page="inventory",
        inventory_items=inventory_items,
        total_skus=total_skus,
        in_stock_count=in_stock_count,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        total_matching=total_matching,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        search_query=search_query,
        status_filter=status_filter,
        category_filter=category_filter,
        brand_filter=brand_filter,
        sort_by=sort_by,
        categories=categories,
        top_brands=top_brands,
        low_stock_threshold=LOW_STOCK_THRESHOLD
    )


@owner_bp.route("/inventory/update-stock", methods=["POST"])
@owner_required
def update_stock():
    """
    Server-side validated stock level modification.
    Supports adjustment types: 'add', 'remove', 'exact'.
    Enforces non-negative stock, CSRF validation, and transactional row locking (FOR UPDATE).
    """
    if not validate_csrf():
        if request.is_json:
            return jsonify({"success": False, "error": "CSRF token missing or invalid", "code": "CSRF_FAILED"}), 400
        flash("Security token expired. Please try again.", "danger")
        return redirect(url_for("owner.inventory"))

    data = request.get_json(silent=True) or request.form

    try:
        product_id = int(data.get("product_id", 0))
    except (ValueError, TypeError):
        product_id = 0

    if product_id <= 0:
        if request.is_json:
            return jsonify({"success": False, "error": "Invalid product ID", "code": "INVALID_ID"}), 400
        flash("Invalid product ID specified.", "danger")
        return redirect(url_for("owner.inventory"))

    adjustment_type = str(data.get("adjustment_type", "exact")).strip().lower()
    if adjustment_type not in ("add", "remove", "exact"):
        if request.is_json:
            return jsonify({"success": False, "error": "Unknown adjustment type", "code": "INVALID_MODE"}), 400
        flash("Invalid adjustment type specified.", "danger")
        return redirect(url_for("owner.inventory"))

    try:
        quantity_input = int(data.get("quantity", 0))
        if quantity_input < 0:
            raise ValueError("Negative quantity")
    except (ValueError, TypeError):
        if request.is_json:
            return jsonify({"success": False, "error": "Quantity must be a non-negative integer", "code": "INVALID_QTY"}), 400
        flash("Stock quantity must be a valid non-negative integer.", "danger")
        return redirect(url_for("owner.inventory"))

    # Execute serialized update with row locking to prevent lost concurrent updates
    from app.db import get_db
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT product_id, product_name, stock_quantity, is_active FROM products WHERE product_id = :1 FOR UPDATE", (product_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            if request.is_json:
                return jsonify({"success": False, "error": "Product not found", "code": "NOT_FOUND"}), 404
            flash(f"Product #{product_id} does not exist in the catalog.", "danger")
            return redirect(url_for("owner.inventory"))

        prod_id, prod_name, current_stock_raw, is_active = row
        current_stock = int(current_stock_raw or 0)

        if adjustment_type == "add":
            new_stock = current_stock + quantity_input
        elif adjustment_type == "remove":
            new_stock = max(0, current_stock - quantity_input)
        elif adjustment_type == "exact":
            new_stock = quantity_input

        cursor.execute("UPDATE products SET stock_quantity = :1 WHERE product_id = :2", (new_stock, product_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        if request.is_json:
            return jsonify({"success": False, "error": str(e), "code": "SERVER_ERROR"}), 500
        flash("Failed to update stock due to a database error.", "danger")
        return redirect(url_for("owner.inventory"))
    finally:
        cursor.close()
        conn.close()

    status_label = "In Stock" if new_stock > LOW_STOCK_THRESHOLD else ("Low Stock" if new_stock > 0 else "Out of Stock")

    if request.is_json:
        return jsonify({
            "success": True,
            "product_id": product_id,
            "product_name": prod_name,
            "previous_stock": current_stock,
            "new_stock": new_stock,
            "status": status_label,
            "message": f"Stock for #{product_id} updated to {new_stock} units."
        })

    flash(f"Stock for '{prod_name}' successfully updated to {new_stock} units.", "success")
    return redirect(url_for("owner.inventory"))


# ==============================================================================
# Screen 6: Store Owner Product Lifecycle & Catalog Administration
# ==============================================================================

@owner_bp.route("/products")
@owner_required
def products():
    """
    Renders Screen 6 Product Catalog Listing.
    Lists all products with search, taxonomy filtering, status toggling, and CRUD entry points.
    """
    search_query = request.args.get("q", "").strip()
    category_filter = request.args.get("category", "").strip()
    active_filter = request.args.get("active", "all").strip().lower()
    sort_by = request.args.get("sort", "id_desc").strip().lower()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 25
    offset = (page - 1) * per_page

    where_clauses = ["1=1"]
    params = {}

    if search_query:
        if search_query.isdigit():
            where_clauses.append("(product_id = :p_id OR LOWER(product_name) LIKE :q OR LOWER(brand) LIKE :q)")
            params["p_id"] = int(search_query)
            params["q"] = f"%{search_query.lower()}%"
        else:
            where_clauses.append("(LOWER(product_name) LIKE :q OR LOWER(brand) LIKE :q)")
            params["q"] = f"%{search_query.lower()}%"

    if category_filter:
        where_clauses.append("category = :cat")
        params["cat"] = category_filter

    if active_filter == "1" or active_filter == "active":
        where_clauses.append("is_active = 1")
    elif active_filter == "0" or active_filter == "inactive":
        where_clauses.append("is_active = 0")

    where_sql = " AND ".join(where_clauses)

    total_matching = query_db(f"SELECT COUNT(*) as c FROM products WHERE {where_sql}", params, one=True)["c"]
    total_pages = max(1, math.ceil(total_matching / per_page))

    sort_mapping = {
        "id_desc": "product_id DESC",
        "id_asc": "product_id ASC",
        "name_asc": "product_name ASC",
        "price_asc": "price_inr ASC",
        "price_desc": "price_inr DESC",
        "stock_asc": "stock_quantity ASC",
        "stock_desc": "stock_quantity DESC",
    }
    order_clause = sort_mapping.get(sort_by, "product_id DESC")

    data_params = dict(params)
    data_params["offset"] = offset
    data_params["per_page"] = per_page

    products_list = query_db(f"""
        SELECT product_id, product_name, brand, category, subcategory, product_type,
               price_inr, sale_price_inr, stock_quantity, is_active, image_url,
               rating, review_count, sales_count
        FROM products
        WHERE {where_sql}
        ORDER BY {order_clause}
        OFFSET :offset ROWS FETCH NEXT :per_page ROWS ONLY
    """, data_params) or []

    categories = query_db("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category ASC") or []

    return render_template(
        "owner/products.html",
        active_page="products",
        products=products_list,
        total_matching=total_matching,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        search_query=search_query,
        category_filter=category_filter,
        active_filter=active_filter,
        sort_by=sort_by,
        categories=categories
    )


@owner_bp.route("/products/new", methods=["GET", "POST"])
@owner_required
def product_new():
    """
    Renders Screen 6 Add New Product Form (GET) and processes creation (POST).
    Uses safe Oracle sequence 'seq_product_id.NEXTVAL' for atomic ID assignment.
    """
    if request.method == "POST":
        if not validate_csrf():
            flash("Session security token expired. Please try again.", "danger")
            return redirect(url_for("owner.product_new"))

        # Input sanitization and extraction
        name = request.form.get("product_name", "").strip()
        brand = request.form.get("brand", "").strip()
        category = request.form.get("category", "").strip()
        subcategory = request.form.get("subcategory", "").strip() or None
        product_type = request.form.get("product_type", "").strip() or None
        description = request.form.get("product_description", "").strip() or None
        keywords = request.form.get("search_keywords", "").strip() or None
        image_url = request.form.get("image_url", "").strip() or "https://placehold.co/400x400/192D32/20B8A9?text=Product"
        is_active = 1 if request.form.get("is_active") in ["1", "on", "true"] else 0

        # Server-side validation
        errors = []
        if not name or len(name) < 2:
            errors.append("Product name is required (minimum 2 characters).")
        if not brand:
            errors.append("Brand / Artisan maker is required.")
        if not category:
            errors.append("Category classification is required.")

        try:
            price = float(request.form.get("price_inr", 0))
            if price <= 0:
                errors.append("Retail price must be a positive number greater than 0.")
        except (ValueError, TypeError):
            errors.append("Please enter a valid retail price.")
            price = 0.0

        sale_price_raw = request.form.get("sale_price_inr", "").strip()
        sale_price = None
        if sale_price_raw:
            try:
                sale_price = float(sale_price_raw)
                if sale_price < 0:
                    errors.append("Sale price cannot be negative.")
                elif price > 0 and sale_price > price:
                    errors.append("Sale price cannot be higher than regular retail price.")
            except (ValueError, TypeError):
                errors.append("Please enter a valid sale price.")

        try:
            stock = int(request.form.get("stock_quantity", 0))
            if stock < 0:
                errors.append("Stock quantity must be a non-negative integer.")
        except (ValueError, TypeError):
            errors.append("Please enter a valid stock quantity.")
            stock = 0

        if errors:
            for err in errors:
                flash(err, "danger")
            categories = query_db("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category ASC") or []
            return render_template("owner/product_form.html", active_page="products", mode="create", form_data=request.form, categories=categories)

        # Concurrency-safe atomic insertion via seq_product_id.NEXTVAL
        insert_sql = """
            INSERT INTO products (
                product_id, product_name, brand, category, subcategory, product_type,
                product_description, search_keywords, price_inr, sale_price_inr,
                stock_quantity, is_active, image_url, rating, review_count, sales_count
            ) VALUES (
                seq_product_id.NEXTVAL, :1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, 4.0, 1, 0
            )
        """
        execute_db(insert_sql, (
            name, brand, category, subcategory, product_type,
            description, keywords, price, sale_price, stock, is_active, image_url
        ))

        # Retrieve the newly created product ID for audit verification
        new_row = query_db("SELECT MAX(product_id) as id FROM products", one=True)
        new_id = new_row["id"] if new_row else "New"

        flash(f"Product '{name}' (#{new_id}) successfully published to Oracle Database 26ai.", "success")
        return redirect(url_for("owner.products"))

    categories = query_db("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category ASC") or []
    return render_template("owner/product_form.html", active_page="products", mode="create", categories=categories, form_data={})


@owner_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@owner_required
def product_edit(product_id):
    """
    Renders Screen 6 Edit Product Form (GET) and processes update (POST).
    """
    product = query_db("SELECT * FROM products WHERE product_id = :1", (product_id,), one=True)
    if not product:
        flash(f"Product #{product_id} not found in database.", "danger")
        return redirect(url_for("owner.products"))

    if request.method == "POST":
        if not validate_csrf():
            flash("Session security token expired. Please try again.", "danger")
            return redirect(url_for("owner.product_edit", product_id=product_id))

        name = request.form.get("product_name", "").strip()
        brand = request.form.get("brand", "").strip()
        category = request.form.get("category", "").strip()
        subcategory = request.form.get("subcategory", "").strip() or None
        product_type = request.form.get("product_type", "").strip() or None
        description = request.form.get("product_description", "").strip() or None
        keywords = request.form.get("search_keywords", "").strip() or None
        image_url = request.form.get("image_url", "").strip() or product["image_url"]
        is_active = 1 if request.form.get("is_active") in ["1", "on", "true"] else 0

        errors = []
        if not name:
            errors.append("Product name is required.")
        if not brand:
            errors.append("Brand is required.")
        if not category:
            errors.append("Category is required.")

        try:
            price = float(request.form.get("price_inr", 0))
            if price <= 0:
                errors.append("Price must be greater than zero.")
        except (ValueError, TypeError):
            errors.append("Invalid retail price.")
            price = product["price_inr"]

        sale_price_raw = request.form.get("sale_price_inr", "").strip()
        sale_price = None
        if sale_price_raw:
            try:
                sale_price = float(sale_price_raw)
                if sale_price < 0 or (price > 0 and sale_price > price):
                    errors.append("Sale price must be non-negative and less than or equal to regular price.")
            except (ValueError, TypeError):
                errors.append("Invalid sale price.")

        try:
            stock = int(request.form.get("stock_quantity", 0))
            if stock < 0:
                errors.append("Stock quantity must be non-negative.")
        except (ValueError, TypeError):
            errors.append("Invalid stock quantity.")
            stock = product["stock_quantity"]

        if errors:
            for err in errors:
                flash(err, "danger")
            categories = query_db("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category ASC") or []
            return render_template("owner/product_form.html", active_page="products", mode="edit", product=product, form_data=request.form, categories=categories)

        update_sql = """
            UPDATE products SET
                product_name = :1,
                brand = :2,
                category = :3,
                subcategory = :4,
                product_type = :5,
                product_description = :6,
                search_keywords = :7,
                price_inr = :8,
                sale_price_inr = :9,
                stock_quantity = :10,
                is_active = :11,
                image_url = :12
            WHERE product_id = :13
        """
        execute_db(update_sql, (
            name, brand, category, subcategory, product_type,
            description, keywords, price, sale_price, stock, is_active, image_url, product_id
        ))

        flash(f"Product #{product_id} ('{name}') updated successfully.", "success")
        return redirect(url_for("owner.products"))

    categories = query_db("SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category ASC") or []
    return render_template("owner/product_form.html", active_page="products", mode="edit", product=product, categories=categories, form_data={})


@owner_bp.route("/products/<int:product_id>/toggle-active", methods=["POST"])
@owner_required
def product_toggle_active(product_id):
    """
    Toggles the active state of a catalog product (1 <-> 0).
    """
    is_ajax = request.is_json or "application/json" in request.headers.get("Accept", "")
    if not validate_csrf():
        if is_ajax:
            return jsonify({"success": False, "error": "CSRF validation failed"}), 400
        flash("Security token expired.", "danger")
        return redirect(url_for("owner.products"))

    product = query_db("SELECT product_id, product_name, is_active FROM products WHERE product_id = :1", (product_id,), one=True)
    if not product:
        if is_ajax:
            return jsonify({"success": False, "error": "Product not found"}), 404
        flash("Product not found.", "danger")
        return redirect(url_for("owner.products"))

    new_state = 0 if product["is_active"] == 1 else 1
    execute_db("UPDATE products SET is_active = :1 WHERE product_id = :2", (new_state, product_id))

    state_label = "Active" if new_state == 1 else "Inactive"
    if is_ajax:
        return jsonify({"success": True, "product_id": product_id, "is_active": new_state, "label": state_label})

    flash(f"Product #{product_id} status changed to {state_label}.", "success")
    return redirect(url_for("owner.products"))


# ==============================================================================
# Screen 7: Store Owner Order Management & Fulfillment Center
# ==============================================================================

@owner_bp.route("/orders")
@owner_required
def orders():
    """
    Renders Screen 7 Order Management & Master-Detail Drawer.
    Lists orders with search, status filters, financial breakdown, and fulfillment tracking.
    """
    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all").strip()
    selected_order_id = request.args.get("selected", "").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 15
    offset = (page - 1) * per_page

    # 1. Discrete KPI Metrics for all 6 individual order statuses
    total_orders = query_db("SELECT COUNT(*) as c FROM orders", one=True)["c"]
    status_counts_rows = query_db("SELECT order_status, COUNT(*) as c FROM orders GROUP BY order_status") or []
    status_counts = {row["order_status"].lower(): row["c"] for row in status_counts_rows}

    confirmed_count = status_counts.get("confirmed", 0)
    processing_count = status_counts.get("processing", 0)
    shipped_count = status_counts.get("shipped", 0)
    delivered_count = status_counts.get("delivered", 0)
    cancelled_count = status_counts.get("cancelled", 0)
    returned_count = status_counts.get("returned", 0)

    # 2. Build parameterized dynamic query
    where_clauses = ["1=1"]
    params = {}

    if search_query:
        if search_query.isdigit():
            where_clauses.append("(o.order_id = :o_id OR LOWER(u.first_name) LIKE :q OR LOWER(u.last_name) LIKE :q OR LOWER(u.email) LIKE :q)")
            params["o_id"] = int(search_query)
            params["q"] = f"%{search_query.lower()}%"
        else:
            where_clauses.append("(LOWER(u.first_name) LIKE :q OR LOWER(u.last_name) LIKE :q OR LOWER(u.email) LIKE :q)")
            params["q"] = f"%{search_query.lower()}%"

    if status_filter and status_filter.lower() != "all":
        where_clauses.append("LOWER(o.order_status) = :st")
        params["st"] = status_filter.lower()

    where_sql = " AND ".join(where_clauses)

    count_sql = f"""
        SELECT COUNT(*) as c
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        WHERE {where_sql}
    """
    total_matching = query_db(count_sql, params, one=True)["c"]
    total_pages = max(1, math.ceil(total_matching / per_page))

    orders_sql = f"""
        SELECT o.order_id, o.user_id, o.order_date, o.order_status, o.subtotal, o.discount_amount,
               o.shipping_fee, o.total_amount, o.payment_method, o.coupon_code, o.num_items,
               o.shipping_city, o.shipping_state, o.delivery_date,
               u.first_name, u.last_name, u.email
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        WHERE {where_sql}
        ORDER BY o.order_date DESC, o.order_id DESC
        OFFSET :offset ROWS FETCH NEXT :per_page ROWS ONLY
    """
    data_params = dict(params)
    data_params["offset"] = offset
    data_params["per_page"] = per_page
    orders_list = query_db(orders_sql, data_params) or []

    # 3. Selected Order Details for Master-Detail View
    selected_order = None
    selected_items = []

    if selected_order_id.isdigit():
        target_id = int(selected_order_id)
    elif orders_list:
        target_id = orders_list[0]["order_id"]
    else:
        target_id = None

    if target_id:
        selected_order = query_db("""
            SELECT o.order_id, o.user_id, o.order_date, o.order_status, o.subtotal, o.discount_amount,
                   o.shipping_fee, o.total_amount, o.payment_method, o.coupon_code, o.num_items,
                   o.shipping_city, o.shipping_state, o.delivery_date,
                   u.first_name, u.last_name, u.email
            FROM orders o
            LEFT JOIN users u ON o.user_id = u.user_id
            WHERE o.order_id = :1
        """, (target_id,), one=True)

        if selected_order:
            selected_items = query_db("""
                SELECT oi.order_item_id, oi.order_id, oi.product_id, oi.quantity, oi.unit_price, oi.line_total,
                       p.product_name, p.brand, p.category, p.image_url
                FROM order_items oi
                LEFT JOIN products p ON oi.product_id = p.product_id
                WHERE oi.order_id = :1
                ORDER BY oi.order_item_id ASC
            """, (target_id,)) or []

    return render_template(
        "owner/orders.html",
        active_page="orders",
        orders=orders_list,
        selected_order=selected_order,
        selected_items=selected_items,
        total_orders=total_orders,
        confirmed_count=confirmed_count,
        processing_count=processing_count,
        shipped_count=shipped_count,
        delivered_count=delivered_count,
        cancelled_count=cancelled_count,
        returned_count=returned_count,
        pending_count=confirmed_count,
        completed_count=delivered_count,
        total_matching=total_matching,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        search_query=search_query,
        status_filter=status_filter,
        valid_statuses=VALID_ORDER_STATUSES,
        allowed_transitions=ALLOWED_STATUS_TRANSITIONS
    )


@owner_bp.route("/orders/<int:order_id>")
@owner_required
def order_detail_api(order_id):
    """
    JSON endpoint returning order information and line items for dynamic drawer updates.
    """
    order = query_db("""
        SELECT o.order_id, o.user_id, o.order_date, o.order_status, o.subtotal, o.discount_amount,
               o.shipping_fee, o.total_amount, o.payment_method, o.coupon_code, o.num_items,
               o.shipping_city, o.shipping_state, o.delivery_date,
               u.first_name, u.last_name, u.email
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        WHERE o.order_id = :1
    """, (order_id,), one=True)

    if not order:
        return jsonify({"success": False, "error": "Order not found"}), 404

    items = query_db("""
        SELECT oi.order_item_id, oi.product_id, oi.quantity, oi.unit_price, oi.line_total,
               p.product_name, p.brand, p.category, p.image_url
        FROM order_items oi
        LEFT JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = :1
        ORDER BY oi.order_item_id ASC
    """, (order_id,)) or []

    # Format order date
    date_str = order["order_date"].strftime("%b %d, %Y · %H:%M") if order.get("order_date") else "Recent"

    return jsonify({
        "success": True,
        "order": {
            "order_id": order["order_id"],
            "status": order["order_status"],
            "date": date_str,
            "customer_name": f"{order.get('first_name') or 'Customer'} {order.get('last_name') or ''}".strip(),
            "customer_email": order.get("email") or "customer@cartify.com",
            "city": order.get("shipping_city") or "Standard Delivery",
            "state": order.get("shipping_state") or "",
            "payment_method": order.get("payment_method") or "Credit Card",
            "subtotal": float(order["subtotal"] or 0),
            "discount": float(order["discount_amount"] or 0),
            "shipping_fee": float(order["shipping_fee"] or 0),
            "total": float(order["total_amount"] or 0),
            "coupon_code": order.get("coupon_code"),
            "num_items": int(order["num_items"] or len(items))
        },
        "items": [
            {
                "product_id": it["product_id"],
                "product_name": it["product_name"] or f"Product #{it['product_id']}",
                "brand": it["brand"] or "Cartify Catalog",
                "category": it["category"] or "Storefront Item",
                "quantity": int(it["quantity"]),
                "unit_price": float(it["unit_price"]),
                "line_total": float(it["line_total"]),
                "image_url": it["image_url"] or ""
            }
            for it in items
        ]
    })


@owner_bp.route("/orders/<int:order_id>/status", methods=["POST"])
@owner_required
def order_update_status(order_id):
    """
    Validated status transitions for order fulfillment lifecycle.
    Guarantees atomic execution, concurrency protection, and inventory restoration on cancellation.
    """
    if not validate_csrf():
        if request.is_json:
            return jsonify({"success": False, "error": "CSRF validation failed"}), 400
        flash("Session security token expired.", "danger")
        return redirect(url_for("owner.orders", selected=order_id))

    data = request.get_json(silent=True) or request.form
    new_status = data.get("new_status", "").strip()

    from app.services.order_service import transition_order_status
    result, status_code = transition_order_status(order_id, new_status, actor_type="owner")

    if request.is_json:
        return jsonify(result), status_code

    if result.get("success"):
        flash(result.get("message", "Order status successfully updated."), "success")
    else:
        flash(result.get("error", "Status transition failed."), "danger")

    return redirect(url_for("owner.orders", selected=order_id))
