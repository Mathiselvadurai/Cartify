import os
from flask import Flask, session
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "smart_recommendation_college_project_2026")
    
    # Initialize routes
    from app.routes.main_routes import main_bp
    from app.routes.auth_routes import auth_bp
    from app.routes.cart_routes import cart_bp
    from app.routes.eval_routes import eval_bp
    from app.routes.owner_routes import owner_bp
    from app.security import is_store_owner
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(eval_bp)
    app.register_blueprint(owner_bp)
    
    # Custom Jinja filters
    @app.template_filter("datetime")
    def format_datetime(value, format="%d %b %Y, %I:%M %p"):
        if value is None:
            return "N/A"
        if hasattr(value, "strftime"):
            return value.strftime(format)
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(value).split(".")[0].replace(" ", "T"))
            return dt.strftime(format)
        except Exception:
            return str(value).split(".")[0]

    # Context processor to inject cart count, wishlist, & logged in user into all templates
    @app.context_processor
    def inject_global_data():
        import secrets
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)

        class CSRFTokenStr(str):
            def __call__(self):
                return str(self)

        cart = session.get("cart", {})
        total_items = sum(item["quantity"] for item in cart.values())
        user = session.get("user")
        wishlist = session.get("wishlist", [])
        return {
            "cart_count": total_items,
            "current_user": user,
            "csrf_token": CSRFTokenStr(session.get("csrf_token", "")),
            "wishlist_count": len(wishlist),
            "wishlist_ids": set(wishlist),
            "is_owner": is_store_owner(user)
        }
        
    from flask import render_template

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("404.html", message="The requested page or item could not be found."), 404

    return app
