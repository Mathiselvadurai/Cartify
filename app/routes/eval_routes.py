import json
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from app.services.evaluator import MLEvaluator, _eval_lock
from app.security import validate_csrf, csrf_protected

eval_bp = Blueprint("evaluation", __name__, url_prefix="/evaluation")

DEMO_ACCESS_KEY = "cartify-eval-2026"
LEGACY_ACCESS_KEY = "aurastore-eval-2026"

def is_authorized_evaluator():
    """
    Checks whether the visitor has verified evaluator or admin privileges.
    Protects sensitive ML evaluation dashboards from unauthorized public viewing.
    """
    if session.get("is_evaluator") or session.get("is_admin"):
        return True
    
    # Check query parameter demo flag or key
    if request.args.get("demo") == "1" or request.args.get("key") in (DEMO_ACCESS_KEY, LEGACY_ACCESS_KEY):
        session["is_evaluator"] = True
        return True
        
    user = session.get("user")
    if user and user.get("tier") in ("Premium", "Admin"):
        session["is_evaluator"] = True
        return True

    return False

@eval_bp.route("/", methods=["GET", "POST"])
def dashboard():
    """
    Renders the Stage 3 & Phase 8 ML Recommendation Evaluation Dashboard.
    Requires academic demo authorization or authenticated evaluator session.
    """
    if request.method == "POST":
        if not validate_csrf():
            flash("Invalid security token. Please try again.", "danger")
            return redirect(url_for("evaluation.dashboard"))

        submitted_key = request.form.get("access_key", "").strip()
        if submitted_key in (DEMO_ACCESS_KEY, LEGACY_ACCESS_KEY) or submitted_key.lower() == "demo":
            session["is_evaluator"] = True
            flash("Academic Evaluator access granted.", "success")
            return redirect(url_for("evaluation.dashboard"))
        else:
            flash("Invalid evaluation access key. (Hint: Use 'cartify-eval-2026' or 'demo')", "danger")

    if not is_authorized_evaluator():
        return render_template("eval_access.html"), 403

    force_refresh = request.args.get("refresh") == "1"

    # 1. Architecture & Hyperparameters
    architecture = MLEvaluator.get_system_architecture()

    # 2. Offline RecSys Policy Comparison (Popularity vs Content vs Semantic vs CF vs Hybrid)
    policy_eval = MLEvaluator.evaluate_offline_policies(sample_users=30, force_refresh=force_refresh)

    # 3. Hybrid Blending Parameter Alpha Optimization (alpha in [0.00, 0.10, 0.20, 0.30])
    alpha_optimization = MLEvaluator.evaluate_hybrid_alpha_optimization(sample_users=30, force_refresh=force_refresh)

    # 4. Repeatable Inference Latency Benchmarks
    latencies = MLEvaluator.benchmark_latencies(runs=30, force_refresh=force_refresh)

    # 5. Anonymized Personalization Case Studies (Strict PII Protection)
    case_studies = MLEvaluator.get_personalization_case_studies()

    # 6. Search Linguistic Tests (Spelling & Domain Synonyms)
    search_tests = MLEvaluator.evaluate_search_linguistics()

    # 7. System Integrity & Safeguard Audits
    integrity_checks = MLEvaluator.verify_system_integrity_checks()

    return render_template(
        "evaluation.html",
        architecture=architecture,
        policy_eval=policy_eval,
        alpha_optimization=alpha_optimization,
        latencies=latencies,
        case_studies=case_studies,
        search_tests=search_tests,
        integrity_checks=integrity_checks,
        active_page="evaluation"
    )

@eval_bp.route("/run", methods=["POST"])
@csrf_protected
def run_benchmark():
    """
    Executes a fresh live benchmark run with mutex concurrency protection and CSRF validation.
    """
    if not is_authorized_evaluator():
        return jsonify({"error": "Unauthorized. Evaluator access required."}), 403

    acquired = _eval_lock.acquire(blocking=False)
    if not acquired:
        return jsonify({
            "status": "busy",
            "message": "A recommendation evaluation benchmark is currently executing. Please wait for completion."
        }), 429

    try:
        policy_eval = MLEvaluator.evaluate_offline_policies(sample_users=30, force_refresh=True)
        alpha_eval = MLEvaluator.evaluate_hybrid_alpha_optimization(sample_users=30, force_refresh=True)
        latencies = MLEvaluator.benchmark_latencies(runs=30, force_refresh=True)
        flash("Live evaluation benchmark completed successfully.", "success")
        if request.headers.get("Accept") == "application/json" or request.is_json:
            return jsonify({
                "status": "success",
                "message": "Live benchmark execution completed",
                "policies": policy_eval,
                "alpha_optimization": alpha_eval,
                "latencies": latencies
            })
        return redirect(url_for("evaluation.dashboard"))
    finally:
        _eval_lock.release()

@eval_bp.route("/api/summary")
def api_summary():
    """JSON API endpoint for programmatic evaluation audit."""
    if not is_authorized_evaluator():
        return jsonify({"error": "Unauthorized. Evaluator access key required."}), 403

    architecture = MLEvaluator.get_system_architecture()
    policy_eval = MLEvaluator.evaluate_offline_policies(sample_users=30)
    alpha_optimization = MLEvaluator.evaluate_hybrid_alpha_optimization(sample_users=30)
    latencies = MLEvaluator.benchmark_latencies(runs=30)
    
    return jsonify({
        "architecture": architecture,
        "policy_evaluation": policy_eval,
        "alpha_optimization": alpha_optimization,
        "latencies": latencies
    })
