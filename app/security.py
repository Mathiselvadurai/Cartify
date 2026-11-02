"""
Security Utilities for Cartify E-Commerce System.
Provides CSRF validation, ownership authorization guards, and input sanitization.
"""

import os
from functools import wraps
from flask import request, session, current_app, abort, redirect, url_for, flash, jsonify, render_template, has_request_context
from app.db import query_db

ADMIN_EMAILS = {
    "admin@cartify.com",
    "owner@cartify.com",
    "admin@example.com",
    "arjun.shetty53@example.com",   # Verified active Store Owner (User 53, is_active=1)
    "bharath.patel51@example.com",  # Deactivated Store Manager for audit testing (User 51, is_active=0)
}

def get_admin_emails():
    env_emails = os.getenv("CARTIFY_ADMIN_EMAILS", "")
    emails = set(ADMIN_EMAILS)
    if env_emails:
        emails.update(e.strip().lower() for e in env_emails.split(",") if e.strip())
    return emails

def is_store_owner(user=None):
    """
    Server-side verification of Store Owner authorization.
    Enforces the mandatory 6-step verification sequence:
    1. Obtain the authenticated user ID.
    2. Retrieve the corresponding user from Oracle Database 26ai.
    3. Verify that the account exists.
    4. Verify IS_ACTIVE = 1.
    5. Verify the database email matches the trusted administrator whitelist.
    6. Grant owner access only after all checks succeed.

    Arbitrary session flags, customer membership tiers, and browser-supplied
    identity information are strictly untrusted.
    """
    if not user and has_request_context():
        user = session.get("user")
    if not user or not isinstance(user, dict):
        return False

    user_id = user.get("id") or user.get("user_id")
    if not user_id:
        return False

    # 1 & 2. Retrieve user record directly from Oracle Database 26ai
    try:
        db_user = query_db(
            "SELECT user_id, email, is_active FROM users WHERE user_id = :1",
            (user_id,),
            one=True
        )
    except Exception as e:
        print(f"Database error during store owner verification: {e}")
        return False

    # 3. Verify account exists in database
    if not db_user:
        return False

    # 4. Verify account is active in database (IS_ACTIVE = 1)
    if db_user.get("is_active") != 1:
        return False

    # 5. Verify the DATABASE email (never trust browser/session email) matches admin whitelist
    db_email = (db_user.get("email") or "").strip().lower()
    admin_emails = get_admin_emails()
    if db_email not in admin_emails:
        return False

    # 6. All security verification steps succeeded
    return True

def owner_required(f):
    """
    Decorator to enforce server-side Store Owner authorization on protected routes.
    Rejects unauthenticated visitors (302 redirect to /login) and ordinary customers (403 Forbidden).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get("user")
        if not user or not user.get("id"):
            flash("Store Owner sign-in required to access the management portal.", "warning")
            return redirect(url_for("auth.login", next=request.url))

        if not is_store_owner(user):
            # Ordinary customer attempting to access owner portal -> 403 Forbidden
            if request.is_json:
                return jsonify({"error": "Forbidden: Store Owner access required", "code": "FORBIDDEN"}), 403
            return render_template("403.html", message="Forbidden: You do not have Store Owner or Administrative permissions to access this management dashboard."), 403

        return f(*args, **kwargs)
    return decorated_function

def validate_csrf():
    """
    Validates CSRF token for state-mutating POST/PUT/DELETE requests.
    In testing mode, validation is enforced only when ENFORCE_CSRF=True.
    """
    if current_app.config.get("TESTING") and not current_app.config.get("ENFORCE_CSRF"):
        return True

    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    session_token = session.get("csrf_token")
    if not session_token or not token or token != session_token:
        return False
    return True

def csrf_protected(f):
    """Decorator to enforce CSRF validation on route functions."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if not validate_csrf():
                if request.is_json or request.headers.get("Accept") == "application/json":
                    return jsonify({"error": "CSRF token missing or invalid", "code": "CSRF_ERROR"}), 403
                flash("Your session security token has expired or is invalid. Please try again.", "danger")
                return redirect(request.referrer or url_for("main.index"))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    """Decorator to enforce customer authentication on protected routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get("user")
        if not user or not user.get("id"):
            if request.is_json:
                return jsonify({"error": "Authentication required", "code": "AUTH_REQUIRED"}), 401
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function
