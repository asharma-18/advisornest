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

        try:
            from auth import supabase
            supabase.table("advisors")\
                .update({
                    "full_name": full_name,
                    "firm_name": firm_name
                })\
                .eq("id", advisor_id)\
                .execute()

            # Update session too
            session["advisor"]["full_name"] = full_name
            session["advisor"]["firm_name"] = firm_name
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

# ── Portfolio Notes ───────────────────────────────────────
@main.route("/notes")
def notes():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id      = session["advisor"]["user_id"]
    all_clients     = get_all_clients(advisor_id)
    selected_client = request.args.get("client", "").strip()
    search_query    = request.args.get("q", "").strip()

    # Get notes — filtered by client if selected
    if selected_client:
        all_notes = get_client_notes(advisor_id, selected_client)
    else:
        all_notes = get_all_notes(advisor_id)

    # Get ALL notes for sidebar counts (unfiltered)
    all_notes_unfiltered = get_all_notes(advisor_id)

    # Filter by search query
    if search_query:
        all_notes = [n for n in all_notes if
            search_query.lower() in n.get("subject", "").lower() or
            search_query.lower() in n.get("body", "").lower() or
            search_query.lower() in (
                (n.get("clients") or {}).get("client_name", "")
            ).lower()
        ]

    return render_template("notes/list.html",
        advisor=session.get("advisor"),
        notes=all_notes,
        all_notes=all_notes_unfiltered,
        clients=all_clients,
        selected_client=selected_client,
        search_query=search_query)
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