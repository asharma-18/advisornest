from ai_logic import generate_ai_recommendation, get_fallback_recommendation, generate_suitability_note_ai
from recommendations_db import (
    save_recommendation, get_all_recommendations,
    get_client_recommendations, get_recommendation,
    delete_recommendation, get_recommendation_count
)
from ai_logic import generate_ai_recommendation, get_fallback_recommendation
from notes_db import get_all_notes, get_client_notes, add_note, delete_note, get_note_count, update_note
from notes_db import get_all_notes, get_client_notes, add_note, delete_note, get_note_count
from pdf_generator import generate_pdf_report
from flask import send_file
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

# ── Forgot Password ───────────────────────────────────────
@main.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        if not email:
            flash("Please enter your email address.", "error")
            return redirect(url_for("main.forgot_password"))

        try:
            from auth import supabase
            supabase.auth.reset_password_email(
                email,
                options={"redirect_to": "http://127.0.0.1:5000/reset-password"}
            )
        except Exception as e:
            pass

        # Always show success — never reveal if email exists
        flash("If an account exists for that email, a reset link has been sent.", "success")
        return redirect(url_for("main.login"))

    return render_template("auth/forgot_password.html")

# ── Google OAuth ──────────────────────────────────────────
@main.route("/auth/google")
def google_login():
    from auth import get_google_auth_url
    url = get_google_auth_url()
    if url:
        return redirect(url)
    flash("Google sign in is unavailable. Please use email.", "error")
    return redirect(url_for("main.login"))


# ── Google OAuth Callback ─────────────────────────────────
@main.route("/auth/google/callback")
def google_callback():
    try:
        # Get the session from Supabase after Google auth
        from auth import supabase

        code = request.args.get("code")
        if not code:
            flash("Google sign in failed. Please try again.", "error")
            return redirect(url_for("main.login"))

        # Exchange code for session
        response = supabase.auth.exchange_code_for_session({
            "auth_code": code
        })

        if not response.user:
            flash("Could not sign in with Google.", "error")
            return redirect(url_for("main.login"))

        user = response.user
        user_id = user.id
        email = user.email
        full_name = user.user_metadata.get("full_name", "") or \
                    user.user_metadata.get("name", "")

        # Check if advisor profile exists
        profile = supabase.table("advisors")\
            .select("*")\
            .eq("id", user_id)\
            .execute()

        if profile.data and len(profile.data) > 0:
            # Existing advisor — go straight to dashboard
            firm_name = profile.data[0].get("firm_name", "")
            session["logged_in"] = True
            session["advisor"] = {
                "user_id":   user_id,
                "email":     email,
                "full_name": full_name,
                "firm_name": firm_name
            }
            flash(f"Welcome back, {full_name}!", "success")
            return redirect(url_for("main.dashboard"))
        else:
            # New advisor — save basic profile and go to onboarding
            supabase.table("advisors").insert({
                "id":        user_id,
                "full_name": full_name,
                "firm_name": ""
            }).execute()

            session["logged_in"]   = True
            session["onboarding"]  = True
            session["advisor"] = {
                "user_id":   user_id,
                "email":     email,
                "full_name": full_name,
                "firm_name": ""
            }
            return redirect(url_for("main.onboarding"))

    except Exception as e:
        print(f"Google callback error: {str(e)}")
        flash("Google sign in failed. Please try again.", "error")
        return redirect(url_for("main.login"))


# ── Onboarding ────────────────────────────────────────────
@main.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    # If already completed onboarding go to dashboard
    if not session.get("onboarding") and \
       session.get("advisor", {}).get("firm_name"):
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        firm_name = request.form.get("firm_name", "").strip()
        advisor_id = session["advisor"]["user_id"]

        try:
            from auth import supabase
            supabase.table("advisors")\
                .update({"firm_name": firm_name})\
                .eq("id", advisor_id)\
                .execute()

            session["advisor"]["firm_name"] = firm_name
            session.pop("onboarding", None)
            flash(f"Welcome to AdvisorNest, "
                  f"{session['advisor']['full_name']}!", "success")
            return redirect(url_for("main.dashboard"))

        except Exception as e:
            flash("Could not save your details. Please try again.", "error")
            return redirect(url_for("main.onboarding"))

    return render_template("auth/onboarding.html",
        advisor=session.get("advisor"))

# ── Profile Settings ──────────────────────────────────────
@main.route("/settings", methods=["GET", "POST"])
def settings():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        firm_name = request.form.get("firm_name", "").strip()

        if not full_name:
            flash("Full name cannot be empty.", "error")
            return redirect(url_for("main.settings"))

        license_number = request.form.get("license_number", "").strip()

        try:
            from auth import supabase
            supabase.table("advisors")\
                .update({
                    "full_name":      full_name,
                    "firm_name":      firm_name,
                    "license_number": license_number,
                })\
                .eq("id", advisor_id)\
                .execute()

            # Update session too
            session["advisor"]["full_name"] = full_name
            session["advisor"]["firm_name"] = firm_name
            session["advisor"]["license_number"] = license_number
            session.modified = True

            flash("Profile updated successfully.", "success")
            return redirect(url_for("main.settings"))

        except Exception as e:
            flash("Could not update profile. Please try again.", "error")
            return redirect(url_for("main.settings"))

    # Fetch latest profile from database
    try:
        from auth import supabase
        profile = supabase.table("advisors")\
            .select("*")\
            .eq("id", advisor_id)\
            .execute()

        advisor = profile.data[0] if profile.data else session["advisor"]
    except Exception:
        advisor = session["advisor"]

    client_count = get_client_count(advisor_id)
    return render_template("portal/settings.html",
        advisor=advisor,
        email=session["advisor"]["email"],
        client_count=client_count)
# ── All Recommendations ───────────────────────────────────
@main.route("/recommendations")
def recommendations():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id      = session["advisor"]["user_id"]
    all_recs        = get_all_recommendations(advisor_id)
    all_clients     = get_all_clients(advisor_id)

    return render_template("recommendations/list.html",
        advisor=session.get("advisor"),
        recommendations=all_recs,
        all_recs=all_recs,
        clients=all_clients,
        selected_client="")


# ── View Recommendation ───────────────────────────────────
@main.route("/recommendations/<rec_id>")
def view_recommendation(rec_id):
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    rec = get_recommendation(advisor_id, rec_id)

    if not rec:
        flash("Recommendation not found.", "error")
        return redirect(url_for("main.recommendations"))

    return render_template("recommendations/view.html",
        advisor=session.get("advisor"),
        rec=rec)


# ── Delete Recommendation ─────────────────────────────────
@main.route("/recommendations/delete/<rec_id>",
            methods=["POST"])
def delete_recommendation_route(rec_id):
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    delete_recommendation(advisor_id, rec_id)
    flash("Recommendation deleted.", "success")
    return redirect(url_for("main.recommendations"))

# ── Reset Password ────────────────────────────────────────
@main.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("main.reset_password"))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("main.reset_password"))

        try:
            from auth import supabase
            supabase.auth.update_user({"password": password})
            flash("Password updated successfully. Please log in.", "success")
            return redirect(url_for("main.login"))
        except Exception as e:
            flash("Could not reset password. Please try again.", "error")
            return redirect(url_for("main.reset_password"))

    return render_template("auth/reset_password.html")

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

        license_number = request.form.get("license_number", "").strip()
        result = register_advisor(email, password, full_name, firm_name, license_number)

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

        # Fetch live market data first
        from concurrent.futures import ThreadPoolExecutor

        # Fetch FRED rates first (fast - needed by GPT)
        try:
            from market_data import get_rates
            rates_only = {"rates": get_rates()}
        except Exception:
            rates_only = {"rates": {}}

        # Run market prices and AI simultaneously
        def fetch_market():
            try:
                return get_all_market_data(risk)
            except Exception:
                return rates_only

        def fetch_ai():
            return generate_ai_recommendation(
                client_name, age, life_stage,
                risk, horizon, amount, rates_only
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_market = executor.submit(fetch_market)
            future_ai     = executor.submit(fetch_ai)
            market_data   = future_market.result()
            ai_result     = future_ai.result()
     # Use fallback if AI fails
        if not ai_result["success"]:
            ai_result = get_fallback_recommendation(
                risk, age, horizon, amount)
            ai_fallback = True
        else:
            ai_fallback = ai_result.get("fallback", False)

        print("AI fallback:", ai_fallback)
        print("AI success:", ai_result["success"])

        ai_data    = ai_result["data"]
        ai_options = ai_data["options"]
        print("=== AI OPTIONS DEBUG ===")
        print("Type:", type(ai_options))
        print("First option type:", type(ai_options[0]) if ai_options else "empty")
        print("First option keys:", ai_options[0].keys() if ai_options else "empty")

        # Still run rule-based for score and legacy support
        allocation = calculate_allocation(risk, horizon, age)
        score      = portfolio_score(risk, horizon, age)
        flags      = get_advisor_flags(risk, horizon, age)

        # Use AI suitability note from recommended option
        # Fall back to generated note if AI note not available
        recommended_option = next(
            (o for o in ai_options if o.get("recommended")),
            ai_options[0] if ai_options else None
        )

        if recommended_option and recommended_option.get("suitability_note"):
            suitability_note = recommended_option["suitability_note"]
        else:
            suitability_note = generate_suitability_note(
                client_name, age, life_stage,
                risk, horizon, amount, allocation
            )

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

        # Default to recommended option for saving
        recommended = next(
            (o for o in ai_options if o.get("recommended")),
            ai_options[0]
        )
        allocation = {
            "equity_etfs":   recommended["allocation"].get("equity_etfs", 30),
            "growth_stocks": recommended["allocation"].get("growth_stocks", 10),
            "bond_etfs":     recommended["allocation"].get("bond_etfs", 35),
            "mutual_funds":  recommended["allocation"].get("mutual_funds", 15),
            "cds":           recommended["allocation"].get("cds", 10),
        }

        result = {
            "client_name":      client_name,
            "age":              age,
            "life_stage":       life_stage,
            "amount":           amount,
            "risk":             risk,
            "horizon":          horizon,
            "allocation":       allocation,
            "score":            score,
            "score_color":      score_color,
            "score_label":      score_label,
            "flags":            flags,
            "market_data":      market_data,
            "suitability_note": suitability_note,
            "ai_options":       ai_options,
            "ai_data":          ai_data,
            "ai_fallback":      ai_fallback,
        }

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

    age     = request.form.get("age")
    amount  = request.form.get("amount")
    horizon = request.form.get("horizon")
    score   = request.form.get("score")

    client_data = {
        "client_name":      request.form.get("client_name", ""),
        "age":              int(age) if age else 0,
        "life_stage":       request.form.get("life_stage", ""),
        "amount":           int(float(amount)) if amount else 0,
        "risk":             request.form.get("risk", ""),
        "horizon":          int(horizon) if horizon else 0,
        "allocation":       json.loads(request.form.get("allocation", "{}")),
        "score":            int(score) if score else 0,
        "flags":            json.loads(request.form.get("flags", "[]")),
        "suitability_note": request.form.get("suitability_note", ""),
        "selected_option":  request.form.get("selected_option", ""),
    }
    result = save_client(advisor_id, client_data)

    if result["success"]:
        # Also save the full AI recommendation
        try:
            ai_data_raw = request.form.get("ai_data", "{}")
            ai_data = json.loads(ai_data_raw) if ai_data_raw else {}
        except Exception:
            ai_data = {}
        print("=== SAVING RECOMMENDATION ===")
        print("ai_data_raw:", request.form.get("ai_data", "NOT FOUND")[:100])
        
        save_recommendation(advisor_id, result.get("client_id"), {
            "client_name":     client_data["client_name"],
            "age":             client_data["age"],
            "life_stage":      client_data["life_stage"],
            "amount":          client_data["amount"],
            "risk":            client_data["risk"],
            "horizon":         client_data["horizon"],
            "selected_option": client_data.get("selected_option", ""),
            "ai_data":         ai_data,
            "allocation":      client_data["allocation"],
            "suitability_note": client_data["suitability_note"],
            "score":           client_data["score"],
        })

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

# ── Portfolio Notes ───────────────────────────────────────
@main.route("/notes")
def notes():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id      = session["advisor"]["user_id"]
    all_clients     = get_all_clients(advisor_id)
    selected_client = request.args.get("client", "").strip()
    all_notes       = get_all_notes(advisor_id)

    return render_template("notes/list.html",
        advisor=session.get("advisor"),
        notes=all_notes,
        all_notes=all_notes,
        clients=all_clients,
        selected_client=selected_client,
        search_query="")
# ── Add Note ──────────────────────────────────────────────
@main.route("/notes/add", methods=["POST"])
def add_note_route():
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id   = session["advisor"]["user_id"]
    client_id    = request.form.get("client_id")
    subject      = request.form.get("subject", "").strip()
    body         = request.form.get("body", "").strip()
    meeting_date = request.form.get("meeting_date", "")

    if not client_id or not subject or not body:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("main.notes"))

    result = add_note(advisor_id, client_id,
                      subject, body, meeting_date)

    if result["success"]:
        flash("Note saved successfully.", "success")
    else:
        flash("Could not save note. Please try again.", "error")

    return redirect(url_for("main.notes"))


# ── Delete Note ───────────────────────────────────────────
@main.route("/notes/delete/<note_id>", methods=["POST"])
def delete_note_route(note_id):
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    result     = delete_note(note_id, advisor_id)

    if result["success"]:
        flash("Note deleted.", "success")
    else:
        flash("Could not delete note.", "error")

    return redirect(url_for("main.notes"))

# ── Update Note ───────────────────────────────────────────
@main.route("/notes/update/<note_id>", methods=["POST"])
def update_note_route(note_id):
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id   = session["advisor"]["user_id"]
    subject      = request.form.get("subject", "").strip()
    body         = request.form.get("body", "").strip()
    meeting_date = request.form.get("meeting_date", "")

    if not subject or not body:
        flash("Subject and notes cannot be empty.", "error")
        return redirect(url_for("main.notes"))

    result = update_note(note_id, advisor_id,
                         subject, body, meeting_date)

    if result["success"]:
        flash("Note updated successfully.", "success")
    else:
        flash("Could not update note.", "error")

    return redirect(url_for("main.notes"))

# ── Download PDF ──────────────────────────────────────────
@main.route("/download-pdf/<client_id>")
def download_pdf(client_id):
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    client     = get_client(client_id, advisor_id)

    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("main.clients"))

    # Get latest recommendation for this client
    # to include instrument picks in the PDF
    try:
        recs = get_client_recommendations(advisor_id, client_id)
        if recs:
            latest_rec = recs[0]
            ai_data    = latest_rec.get("ai_data", {})

            # Find the selected option from ai_data
            selected_option_label = latest_rec.get("selected_option", "")
            selected_option_id    = selected_option_label[0] if selected_option_label else None

            if ai_data and selected_option_id:
                options = ai_data.get("options", [])
                selected = next(
                    (o for o in options
                     if o.get("id") == selected_option_id),
                    options[0] if options else None
                )
                if selected:
                    client["recommendation_data"] = selected
    except Exception as e:
        print(f"Could not fetch recommendation data: {str(e)}")

    pdf_buffer = generate_pdf_report(client, session["advisor"])

    filename = f"AdvisorNest_{client['client_name'].replace(' ', '_')}_Report.pdf"

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )

    # Generate the PDF
    pdf_buffer = generate_pdf_report(client, session["advisor"])

    # Send as downloadable file
    filename = f"AdvisorNest_{client['client_name'].replace(' ', '_')}_Report.pdf"

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )

# ── Logout ────────────────────────────────────────────────
@main.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("main.login"))

# ── Validate Ticker ───────────────────────────────────────
@main.route("/validate-ticker/<ticker>")
def validate_ticker(ticker):
    if not session.get("logged_in"):
        return json.dumps({"valid": False})
    try:
        import yfinance as yf
        t = yf.Ticker(ticker.upper())
        info = t.info
        name = info.get("longName") or info.get("shortName", "")
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        if name:
            return json.dumps({
                "valid": True,
                "ticker": ticker.upper(),
                "name": name,
                "price": price
            })
        return json.dumps({"valid": False})
    except Exception:
        return json.dumps({"valid": False})

 # ── Generate Suitability Note ─────────────────────────────
@main.route("/generate-suitability-note", methods=["POST"])
def generate_suitability_note_route():
    if not session.get("logged_in"):
        return json.dumps({"success": False, "error": "Not logged in"})

    try:
        data = request.get_json()

        client_name = data.get("client_name", "")
        age         = data.get("age", 0)
        life_stage  = data.get("life_stage", "")
        risk        = data.get("risk", "")
        horizon     = data.get("horizon", 0)
        amount      = data.get("amount", 0)
        option_name = data.get("option_name", "")
        option_id   = data.get("option_id", "")
        instruments = data.get("instruments", {})
        market_data = data.get("market_data", {})

        result = generate_suitability_note_ai(
            client_name, age, life_stage, risk,
            horizon, amount, option_name, option_id,
            instruments, market_data
        )

        return json.dumps(result)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

# ── Terms of Service ──────────────────────────────────────
@main.route("/terms")
def terms():
    return render_template("legal/terms.html")


# ── Privacy Policy ────────────────────────────────────────
@main.route("/privacy")
def privacy():
    return render_template("legal/privacy.html")