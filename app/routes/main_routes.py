import math
from flask import Blueprint, render_template, request, session
from app.db import query_db, execute_db
from app.services.recommender import RecommendationEngine

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def index():
    engine = RecommendationEngine.get_instance()
    user = session.get("user")
    user_id = user["id"] if user else None
    
    # 1. Fetch top categories with product counts from Oracle
    categories = query_db("""
        SELECT category, COUNT(*) as count 
        FROM products 
        WHERE is_active = 1 
        GROUP BY category 
        ORDER BY count DESC
        FETCH FIRST 6 ROWS ONLY
    """)
    
    # 2. Trending / Best Sellers
    trending = engine.get_popular_products(limit=8)
    
    # 3. Personalized recommendations (or cold-start top rated if guest)
    recommended = engine.get_personalized_recommendations(user_id=user_id, limit=8)

    # 4. Featured Flagship Hero Product
    hero_product = None
    if trending:
        hero_product = trending[0]
    
    return render_template("index.html", 
                           categories=categories, 
                           trending=trending, 
                           recommended=recommended,
                           hero_product=hero_product)

@main_bp.route("/products")
def products():
    search_query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    subcategory = request.args.get("subcategory", "").strip()
    brand = request.args.get("brand", "").strip()
    gender = request.args.get("gender", "").strip()
    min_price = request.args.get("min_price", "").strip()
    max_price = request.args.get("max_price", "").strip()
    min_rating = request.args.get("min_rating", "").strip()
    sort_by = request.args.get("sort", "popular").strip()
    search_strategy = request.args.get("strategy", "hybrid").strip()
    if search_strategy not in ("hybrid", "semantic", "lexical"):
        search_strategy = "hybrid"
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 24
    
    engine = RecommendationEngine.get_instance()
    
    # If a search query is provided, use Hybrid Semantic / TF-IDF Search for ranking!
    if search_query:
        smart_results = engine.smart_search(search_query, top_n=300, strategy=search_strategy)
        
        # Apply facet filters if set
        filtered = smart_results
        if category:
            filtered = [p for p in filtered if str(p.get("category", "")).lower() == category.lower()]
        if subcategory:
            filtered = [p for p in filtered if str(p.get("subcategory", "")).lower() == subcategory.lower()]
        if brand:
            filtered = [p for p in filtered if str(p.get("brand", "")).lower() == brand.lower()]
        if gender:
            filtered = [p for p in filtered if str(p.get("gender", "")).lower() == gender.lower()]
        if min_price:
            try:
                min_p = float(min_price)
                filtered = [p for p in filtered if float(p.get("sale_price_inr") or p.get("price_inr") or 0) >= min_p]
            except ValueError:
                pass
        if max_price:
            try:
                max_p = float(max_price)
                filtered = [p for p in filtered if float(p.get("sale_price_inr") or p.get("price_inr") or 0) <= max_p]
            except ValueError:
                pass
        if min_rating:
            try:
                min_r = float(min_rating)
                filtered = [p for p in filtered if float(p.get("rating") or 0) >= min_r]
            except ValueError:
                pass
            
        # Apply sorting to search results if explicitly requested
        if sort_by == "price_asc":
            filtered = sorted(filtered, key=lambda x: float(x.get("sale_price_inr") or x.get("price_inr") or 0))
        elif sort_by == "price_desc":
            filtered = sorted(filtered, key=lambda x: float(x.get("sale_price_inr") or x.get("price_inr") or 0), reverse=True)
        elif sort_by == "rating":
            filtered = sorted(filtered, key=lambda x: (float(x.get("rating") or 0), int(x.get("sales_count") or 0)), reverse=True)
        # Otherwise keep algorithm relevance ordering (default: popular/relevance)

        total_items = len(filtered)
        total_pages = math.ceil(total_items / per_page) or 1
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        items = filtered[start_idx:end_idx]
    else:
        # Standard Oracle SQL query with dynamic filters and pagination
        where_clauses = ["is_active = 1"]
        params = []
        
        if category:
            where_clauses.append("LOWER(category) = LOWER(:cat)")
            params.append(category)
        if subcategory:
            where_clauses.append("LOWER(subcategory) = LOWER(:subcat)")
            params.append(subcategory)
        if brand:
            where_clauses.append("LOWER(brand) = LOWER(:brand)")
            params.append(brand)
        if gender:
            where_clauses.append("LOWER(gender) = LOWER(:gen)")
            params.append(gender)
        if min_price:
            try:
                where_clauses.append("COALESCE(sale_price_inr, price_inr) >= :min_p")
                params.append(float(min_price))
            except ValueError:
                pass
        if max_price:
            try:
                where_clauses.append("COALESCE(sale_price_inr, price_inr) <= :max_p")
                params.append(float(max_price))
            except ValueError:
                pass
        if min_rating:
            try:
                where_clauses.append("rating >= :min_r")
                params.append(float(min_rating))
            except ValueError:
                pass
            
        where_str = " AND ".join(where_clauses)
        
        # Count total matches
        count_sql = f"SELECT COUNT(*) as total FROM products WHERE {where_str}"
        total_row = query_db(count_sql, tuple(params), one=True)
        total_items = total_row["total"] if total_row else 0
        total_pages = math.ceil(total_items / per_page) or 1
        
        # Ordering
        order_by = "sales_count DESC, rating DESC"
        if sort_by == "price_asc":
            order_by = "COALESCE(sale_price_inr, price_inr) ASC"
        elif sort_by == "price_desc":
            order_by = "COALESCE(sale_price_inr, price_inr) DESC"
        elif sort_by == "rating":
            order_by = "rating DESC, review_count DESC"
        elif sort_by == "newest":
            order_by = "product_id DESC"
            
        offset = (page - 1) * per_page
        sql = f"""
            SELECT product_id, product_name, brand, category, subcategory, 
                   product_type, gender, color, price_inr, sale_price_inr, 
                   discount_percent, rating, review_count, stock_quantity, sales_count, image_url
            FROM products
            WHERE {where_str}
            ORDER BY {order_by}
            OFFSET {offset} ROWS FETCH NEXT {per_page} ROWS ONLY
        """
        items = query_db(sql, tuple(params))
        
    # Fetch facet choices for sidebar filter
    categories = query_db("""
        SELECT category, COUNT(*) as count 
        FROM products 
        WHERE is_active = 1 
        GROUP BY category 
        ORDER BY count DESC 
        FETCH FIRST 8 ROWS ONLY
    """)
    brands = query_db("""
        SELECT brand, COUNT(*) as count 
        FROM products 
        WHERE is_active = 1 AND brand IS NOT NULL 
        GROUP BY brand 
        ORDER BY count DESC 
        FETCH FIRST 10 ROWS ONLY
    """)
    genders = query_db("SELECT DISTINCT gender FROM products WHERE is_active = 1 AND gender IS NOT NULL ORDER BY gender")
    
    return render_template("products.html",
                           items=items,
                           total_items=total_items,
                           page=page,
                           total_pages=total_pages,
                           search_query=search_query,
                           selected_category=category,
                           selected_subcategory=subcategory,
                           selected_brand=brand,
                           selected_gender=gender,
                           selected_min_price=min_price,
                           selected_max_price=max_price,
                           selected_min_rating=min_rating,
                           selected_sort=sort_by,
                           search_strategy=search_strategy,
                           categories=categories,
                           brands=brands,
                           genders=genders)

@main_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    # 1. Fetch product details from Oracle
    sql = """
        SELECT product_id, product_name, brand, variant, category, subcategory, 
               product_type, gender, age_group, product_usage, season, color, 
               product_description, search_keywords, price_inr, sale_price_inr, 
               discount_percent, rating, review_count, stock_quantity, sales_count, image_url
        FROM products
        WHERE product_id = :1 AND is_active = 1
    """
    product = query_db(sql, (product_id,), one=True)
    if not product:
        return render_template("404.html", message="Product not found"), 404

    # 2. Record user view interaction in Oracle if logged in
    user = session.get("user")
    if user:
        try:
            inter_sql = """
                INSERT INTO interactions (
                    interaction_id, user_id, product_id, event_type, event_timestamp, device_type
                ) VALUES (
                    seq_interaction_id.NEXTVAL, :1, :2, 'view', SYSTIMESTAMP, 'Web'
                )
            """
            execute_db(inter_sql, (user["id"], product_id))
        except Exception as e:
            print(f"Error logging interaction: {e}")

    # 3. Content-Based TF-IDF + Cosine Similarity Recommendations
    engine = RecommendationEngine.get_instance()
    recommendations = engine.get_similar_products(product_id, top_n=6)

    # 4. Fetch Verified Reviews for this product from Oracle
    rev_sql = """
        SELECT r.rating, r.review_title, r.review_text, r.review_date, r.helpful_votes,
               u.first_name, u.city
        FROM reviews r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.product_id = :1
        ORDER BY r.review_date DESC
        FETCH FIRST 5 ROWS ONLY
    """
    reviews = query_db(rev_sql, (product_id,))

    return render_template("product_detail.html",
                           product=product,
                           recommendations=recommendations,
                           reviews=reviews)
