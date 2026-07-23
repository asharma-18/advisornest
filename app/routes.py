from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from auth import login_advisor, register_advisor
from logic import calculate_allocation, portfolio_score, get_advisor_flags, generate_suitability_note
from market_data import get_all_market_data
from clients_db import save_client, get_all_clients, get_client, delete_client, get_client_count
import json

main = Blueprint("main", __name__)


# ── Home ──────────────────────────────────────────────────
@main.route("/")
def home():
    if session.get("logged_in"):
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.login"))


# ── Login ─────────────────────────────────────────────────
@main.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return redirect(url_for("main.login"))

        result = login_advisor(email, password)

        if result["success"]:
            session["logged_in"] = True
            session["advisor"]   = {
                "user_id":   result["user_id"],
                "email":     result["email"],
                "full_name": result["full_name"],
                "firm_name": result["firm_name"]
            }
            flash(f"Welcome back, {result['full_name']}!", "success")
            return redirect(url_for("main.dashboard"))
        else:
            flash(result["message"], "error")
            return redirect(url_for("main.login"))

    return render_template("auth/login.html")


# ── Register ──────────────────────────────────────────────
@main.route("/register", methods=["GET", "POST"])
def register():
    if session.get("logged_in"):
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        firm_name = request.form.get("firm_name", "").strip()
        email     = request.form.get("email", "").strip()
        password  = request.form.get("password", "")
        confirm   = request.form.get("confirm_password", "")

        if not full_name or not email or not password:
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("main.register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("main.register"))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("main.register"))

        result = register_advisor(email, password, full_name, firm_name)

        if result["success"]:
            flash("Account created! Please log in.", "success")
            return redirect(url_for("main.login"))
        else:
            flash(result["message"], "error")
            return redirect(url_for("main.register"))

    return render_template("auth/register.html")


# ── Dashboard ─────────────────────────────────────────────
@main.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id   = session["advisor"]["user_id"]
    client_count = get_client_count(advisor_id)

    return render_template("portal/dashboard.html",
        advisor=session.get("advisor"),
        client_count=client_count)


# ── Portal ────────────────────────────────────────────────
@main.route("/portal", methods=["GET", "POST"])
def portal():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    result    = None
    form_data = {}

    if request.method == "POST":
        client_name = request.form.get("client_name", "").strip()
        age         = int(request.form.get("age", 45))
        life_stage  = request.form.get("life_stage", "Mid-Career")
        amount      = int(request.form.get("amount", 100000))
        risk        = request.form.get("risk", "Medium")
        horizon     = int(request.form.get("horizon", 10))

        form_data = {
            "client_name": client_name,
            "age":         age,
            "life_stage":  life_stage,
            "amount":      amount,
            "risk":        risk,
            "horizon":     horizon
        }

        if not client_name:
            flash("Please enter a client name.", "error")
            return render_template("portal/index.html",
                advisor=session.get("advisor"),
                form_data=form_data,
                result=None)

        # Run core logic
        allocation       = calculate_allocation(risk, horizon, age)
        score            = portfolio_score(risk, horizon, age)
        flags            = get_advisor_flags(risk, horizon, age)
        suitability_note = generate_suitability_note(
            client_name, age, life_stage,
            risk, horizon, amount, allocation
        )

        # Fetch live market data
        try:
            market_data = get_all_market_data(risk)
        except Exception:
            market_data = None

        # Calculate dollar amounts
        dollar_allocation = {
            instrument: {
                "percentage": pct,
                "amount":     round((pct / 100) * amount)
            }
            for instrument, pct in allocation.items()
        }

        # Score color and label
        if score >= 80:
            score_color = "success"
            score_label = "Excellent"
        elif score >= 60:
            score_color = "warning"
            score_label = "Moderate"
        else:
            score_color = "error"
            score_label = "Needs Review"

        result = {
            "client_name":       client_name,
            "age":               age,
            "life_stage":        life_stage,
            "amount":            amount,
            "risk":              risk,
            "horizon":           horizon,
            "allocation":        allocation,
            "dollar_allocation": dollar_allocation,
            "score":             score,
            "score_color":       score_color,
            "score_label":       score_label,
            "flags":             flags,
            "market_data":       market_data,
            "suitability_note":  suitability_note,
        }

        # Pre-convert to JSON for hidden form fields
        result["allocation_json"] = json.dumps(allocation)
        result["flags_json"]      = json.dumps(flags)

    return render_template("portal/index.html",
        advisor=session.get("advisor"),
        result=result,
        form_data=form_data)


# ── Save Client ───────────────────────────────────────────
@main.route("/save-client", methods=["POST"])
def save_client_route():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]

    client_data = {
        "client_name":      request.form.get("client_name"),
        "age":              int(request.form.get("age")),
        "life_stage":       request.form.get("life_stage"),
        "amount":           int(request.form.get("amount")),
        "risk":             request.form.get("risk"),
        "horizon":          int(request.form.get("horizon")),
        "allocation":       json.loads(request.form.get("allocation")),
        "score":            int(request.form.get("score")),
        "flags":            json.loads(request.form.get("flags")),
        "suitability_note": request.form.get("suitability_note"),
    }

    result = save_client(advisor_id, client_data)

    if result["success"]:
        flash(result["message"], "success")
    else:
        flash(result["message"], "error")

    return redirect(url_for("main.clients"))


# ── Clients ───────────────────────────────────────────────
@main.route("/clients")
def clients():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id   = session["advisor"]["user_id"]
    all_clients  = get_all_clients(advisor_id)
    client_count = get_client_count(advisor_id)

    return render_template("clients/list.html",
        advisor=session.get("advisor"),
        clients=all_clients,
        client_count=client_count)


# ── Delete Client ─────────────────────────────────────────
@main.route("/delete-client/<client_id>", methods=["POST"])
def delete_client_route(client_id):
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    result     = delete_client(client_id, advisor_id)

    if result["success"]:
        flash(result["message"], "success")
    else:
        flash(result["message"], "error")

    return redirect(url_for("main.clients"))


# ── View Client ───────────────────────────────────────────
@main.route("/clients/<client_id>")
def view_client(client_id):
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    client     = get_client(client_id, advisor_id)

    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("main.clients"))

    return render_template("clients/view.html",
        advisor=session.get("advisor"),
        client=client)


# ── Logout ────────────────────────────────────────────────
@main.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("main.login"))