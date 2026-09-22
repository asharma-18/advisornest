from portfolio_snapshots_db import save_snapshot, get_client_snapshots
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from auth import login_advisor, register_advisor
from logic import calculate_allocation, portfolio_score, get_advisor_flags, generate_suitability_note
from market_data import get_all_market_data, fetch_instrument_prices, get_redis
from clients_db import save_client, get_all_clients, get_client, delete_client, get_client_count, update_client
from notes_db import get_all_notes, get_client_notes, add_note, delete_note, get_note_count, update_note
from recommendations_db import (
    save_recommendation, get_all_recommendations,
    get_client_recommendations, get_recommendation,
    delete_recommendation, get_recommendation_count
)
from ai_logic import generate_ai_recommendation, get_fallback_recommendation, generate_suitability_note_ai
from pdf_generator import generate_pdf_report
from flask import send_file
import json
import threading
import time
import feedparser
import requests as req

CACHE_TTL_SECONDS = 1800  # 30 minutes

_feed_cache = {}
_cache_lock = threading.Lock()

SEC_HEADERS = {
    "User-Agent": "AdvisorNest advisornest.app@gmail.com    b ",
    "Accept-Encoding": "gzip, deflate"
}

def _calculate_portfolio_drift(allocation, instruments, amount, original_prices):
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor

    cat_labels = {
        "equity_etfs":   "Equity ETFs",
        "growth_stocks": "Growth Stocks",
        "bond_etfs":     "Bond ETFs",
        "mutual_funds":  "Mutual Funds",
        "cds":           "CDs"
    }

    def fetch_price(ticker):
        try:
            if ticker.startswith("CD-") or ticker == "TBILL":
                return ticker, None
            info  = yf.Ticker(ticker).info
            price = info.get("regularMarketPrice") or \
                    info.get("currentPrice") or \
                    info.get("navPrice", 0)
            return ticker, float(price) if price else None
        except Exception:
            return ticker, None

    all_tickers = []
    for cat, items in instruments.items():
        for inst in items:
            ticker = inst.get("ticker", "")
            if ticker and ticker not in all_tickers:
                all_tickers.append(ticker)

    current_prices = {}
    if all_tickers:
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_price, all_tickers)
            for ticker, price in results:
                if price:
                    current_prices[ticker] = price

    results = []

    for cat, target_pct in allocation.items():
        if not target_pct or target_pct == 0:
            continue

        target_amt   = round((target_pct / 100) * amount)
        cat_instrs   = instruments.get(cat, [])
        inst_details = []
        current_value = 0
        has_real_data = False

        for inst in cat_instrs:
            ticker       = inst.get("ticker", "")
            inst_pct     = inst.get("allocation_pct", 0)
            original_amt = round((inst_pct / 100) * amount)

            if ticker.startswith("CD-") or ticker == "TBILL":
                current_value += original_amt
                continue

            orig_price    = original_prices.get(ticker)
            current_price = current_prices.get(ticker)

            if orig_price and current_price and orig_price > 0:
                shares         = original_amt / orig_price
                current_value += round(shares * current_price)
                has_real_data  = True
                pct_change     = round(((current_price - orig_price) / orig_price) * 100, 2)
                inst_details.append({
                    "ticker":        ticker,
                    "name":          inst.get("name", ""),
                    "orig_price":    round(orig_price, 2),
                    "current_price": round(current_price, 2),
                    "pct_change":    pct_change,
                    "direction":     "up" if pct_change > 0 else "down" if pct_change < 0 else "flat"
                })
            else:
                current_value += original_amt

        current_pct = round((current_value / amount) * 100, 1) if amount > 0 else target_pct
        drift_pct   = round(current_pct - target_pct, 1)
        drift_amt   = round(current_value - target_amt)

        if drift_pct > 5:
            action      = f"Consider trimming ${abs(drift_amt):,}"
            action_type = "sell"
        elif drift_pct < -5:
            action      = f"Consider adding ${abs(drift_amt):,}"
            action_type = "buy"
        else:
            action      = "On target — hold"
            action_type = "hold"

        results.append({
            "category":      cat_labels.get(cat, cat),
            "target_pct":    target_pct,
            "current_pct":   current_pct,
            "current_value": current_value,
            "drift_pct":     drift_pct,
            "drift_amt":     drift_amt,
            "action":        action,
            "action_type":   action_type,
            "has_real_data": has_real_data,
            "instruments":   inst_details
        })

    return results
def _build_action_plan(drift_results):
    """
    Turns drift results into two actionable lists:
    - rebalance_actions: categories that exceed the 2% threshold,
      naming the largest holding in that category as the likely trade
    - tax_loss_opportunities: individual instruments currently at a
      loss since purchase
    """
    rebalance_actions = []
    tax_loss_opportunities = []

    for cat in drift_results:
        if cat["action_type"] in ("buy", "sell"):
            largest_holding = None
            if cat["instruments"]:
                largest_holding = max(cat["instruments"], key=lambda i: abs(i["pct_change"]))

            rebalance_actions.append({
                "category":    cat["category"],
                "action_type": cat["action_type"],
                "amount":      abs(cat["drift_amt"]),
                "detail":      cat["action"],
                "largest_holding": largest_holding["ticker"] if largest_holding else None
            })

        for inst in cat["instruments"]:
            if inst["pct_change"] < 0:
                tax_loss_opportunities.append({
                    "ticker":     inst["ticker"],
                    "name":       inst["name"],
                    "category":   cat["category"],
                    "pct_change": inst["pct_change"]
                })

    tax_loss_opportunities.sort(key=lambda x: x["pct_change"])

    return rebalance_actions, tax_loss_opportunities

def _fetch_feed(url, headers=None, limit=8):
    resp = req.get(url, headers=headers, timeout=8)
    if resp.status_code == 429:
        print(f"SEC rate limit hit (429) for {url}")
    elif resp.status_code == 403:
        print(f"SEC blocked request (403) for {url} — check User-Agent or IP block")
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "").strip()
        link  = entry.get("link", "#")
        date  = entry.get("published", "")[:16] if entry.get("published") else ""
        if title and len(title) > 5:
            items.append({"title": title, "link": link, "date": date})
    return items


def _get_cached_feed(cache_key, fetch_fn):
    """
    Returns a list of items for the given feed, using a shared
    in-memory cache with a TTL. If a fresh fetch fails but a stale
    cached copy exists, the stale copy is served instead of nothing.
    """
    now = time.time()

    with _cache_lock:
        cached = _feed_cache.get(cache_key)

    if cached and (now - cached["timestamp"]) < CACHE_TTL_SECONDS:
        print(f"[CACHE HIT] {cache_key} ({int(now - cached['timestamp'])}s old)")
        return cached["items"], cached["timestamp"]
    print(f"[CACHE MISS] {cache_key} — fetching live")
    try:
        items = fetch_fn()
        with _cache_lock:
            _feed_cache[cache_key] = {"items": items, "timestamp": now}
        return items, now
    except Exception as e:
        print(f"{cache_key} fetch error: {str(e)}")
        if cached:
            print(f"Serving stale {cache_key} cache due to fetch failure")
            return cached["items"], cached["timestamp"]

        raise
main = Blueprint("main", __name__)


# ── Home ──────────────────────────────────────────────────
@main.route("/")
def home():
    if session.get("logged_in"):
        return redirect(url_for("main.dashboard"))
    return render_template("homepage.html")


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
                "user_id":        result["user_id"],
                "email":          result["email"],
                "full_name":      result["full_name"],
                "firm_name":      result["firm_name"],
                "license_number": result.get("license_number", "")
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

        license_number = request.form.get("license_number", "").strip()
        result = register_advisor(email, password, full_name, firm_name, license_number)

        if result["success"]:
            flash("Account created! Please log in.", "success")
            return redirect(url_for("main.login"))
        else:
            flash(result["message"], "error")
            return redirect(url_for("main.register"))

    return render_template("auth/register.html")


# ── Forgot Password ───────────────────────────────────────
@main.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        if not email:
            flash("Please enter your email address.", "error")
            return redirect(url_for("main.forgot_password"))

        try:
            from auth import get_supabase
            get_supabase().auth.reset_password_email(
                email,
                options={"redirect_to": "http://127.0.0.1:5000/reset-password"}
            )
        except Exception as e:
            pass

        flash("If an account exists for that email, a reset link has been sent.", "success")
        return redirect(url_for("main.login"))

    return render_template("auth/forgot_password.html")


# ── Reset Password ────────────────────────────────────────
@main.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        token    = request.form.get("token", "")
        refresh  = request.form.get("refresh_token", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/reset_password.html", token=token, refresh=refresh)

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html", token=token, refresh=refresh)

        try:
            from auth import get_supabase
            sb = get_supabase()

            if token and refresh:
                sb.auth.set_session(token, refresh)
            elif token:
                sb.auth.set_session(token, token)

            sb.auth.update_user({"password": password})
            flash("Password updated successfully. Please log in.", "success")
            return redirect(url_for("main.login"))

        except Exception as e:
            print(f"Password reset error: {str(e)}")
            flash("Could not reset password. Please request a new link.", "error")
            return redirect(url_for("main.forgot_password"))

    token   = request.args.get("token", "") or \
              request.args.get("access_token", "")
    refresh = request.args.get("refresh_token", "")

    return render_template("auth/reset_password.html", token=token, refresh=refresh)
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
        from auth import get_supabase

        code = request.args.get("code")
        if not code:
            flash("Google sign in failed. No authorization code received.", "error")
            return redirect(url_for("main.login"))

        auth_response = get_supabase().auth.exchange_code_for_session({
            "auth_code": code
        })

        if not auth_response or not auth_response.user:
            flash("Could not establish Google session. Please try again.", "error")
            return redirect(url_for("main.login"))

        user_id = auth_response.user.id
        email   = auth_response.user.email

        profile = get_supabase().table("advisors")\
            .select("*")\
            .eq("id", user_id)\
            .execute()

        if profile.data and len(profile.data) > 0:
            full_name      = profile.data[0].get("full_name", "")
            firm_name      = profile.data[0].get("firm_name", "")
            license_number = profile.data[0].get("license_number", "")

            session["logged_in"] = True
            session["advisor"] = {
                "user_id":        user_id,
                "email":          email,
                "full_name":      full_name,
                "firm_name":      firm_name,
                "license_number": license_number
            }
            flash(f"Welcome back, {full_name}!", "success")
            return redirect(url_for("main.dashboard"))
        else:
            full_name = auth_response.user.user_metadata.get("full_name", "") or \
                        auth_response.user.user_metadata.get("name", "Google User")
            firm_name = ""

            get_supabase().table("advisors").insert({
                "id":        user_id,
                "full_name": full_name,
                "firm_name": firm_name
            }).execute()

            session["logged_in"]  = True
            session["onboarding"] = True
            session["advisor"] = {
                "user_id":        user_id,
                "email":          email,
                "full_name":      full_name,
                "firm_name":      firm_name,
                "license_number": ""
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

    if not session.get("onboarding") and \
       session.get("advisor", {}).get("firm_name"):
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        firm_name  = request.form.get("firm_name", "").strip()
        advisor_id = session["advisor"]["user_id"]

        try:
            from auth import get_supabase
            get_supabase().table("advisors")\
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


# ── Profile Settings ──────────────────────────────────────
@main.route("/settings", methods=["GET", "POST"])
def settings():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]

    if request.method == "POST":
        full_name      = request.form.get("full_name", "").strip()
        firm_name      = request.form.get("firm_name", "").strip()
        license_number = request.form.get("license_number", "").strip()

        if not full_name:
            flash("Full name cannot be empty.", "error")
            return redirect(url_for("main.settings"))

        try:
            from auth import get_supabase
            get_supabase().table("advisors")\
                .update({
                    "full_name":      full_name,
                    "firm_name":      firm_name,
                    "license_number": license_number,
                })\
                .eq("id", advisor_id)\
                .execute()

            session["advisor"]["full_name"]      = full_name
            session["advisor"]["firm_name"]      = firm_name
            session["advisor"]["license_number"] = license_number
            session.modified = True

            flash("Profile updated successfully.", "success")
            return redirect(url_for("main.settings"))

        except Exception as e:
            flash("Could not update profile. Please try again.", "error")
            return redirect(url_for("main.settings"))

    try:
        from auth import get_supabase
        profile = get_supabase().table("advisors")\
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

        from concurrent.futures import ThreadPoolExecutor

        try:
            from market_data import get_rates
            rates_only = {"rates": get_rates()}
        except Exception:
            rates_only = {"rates": {}}

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

        if not ai_result["success"]:
            ai_result   = get_fallback_recommendation(risk, age, horizon, amount)
            ai_fallback = True
        else:
            ai_fallback = ai_result.get("fallback", False)

        ai_data    = ai_result["data"]
        ai_options = ai_data["options"]

        allocation = calculate_allocation(risk, horizon, age)
        score      = portfolio_score(risk, horizon, age)
        flags      = get_advisor_flags(risk, horizon, age)

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

        if score >= 80:
            score_color = "success"
            score_label = "Excellent"
        elif score >= 60:
            score_color = "warning"
            score_label = "Moderate"
        else:
            score_color = "error"
            score_label = "Needs Review"

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
        try:
            ai_data_raw = request.form.get("ai_data", "{}")
            ai_data = json.loads(ai_data_raw) if ai_data_raw else {}
        except Exception:
            ai_data = {}

        # Fetch original prices for drift tracking
        instrument_prices = {}
        try:
            if ai_data and ai_data.get("options"):
                selected_id = client_data.get("selected_option", "C")[0]
                selected_opt = next(
                    (o for o in ai_data["options"] if o.get("id") == selected_id),
                    ai_data["options"][0] if ai_data["options"] else None
                )
                if selected_opt:
                    from market_data import fetch_instrument_prices
                    instrument_prices = fetch_instrument_prices(
                        selected_opt.get("instruments", {})
                    )
        except Exception as e:
            print(f"Price fetch error: {str(e)}")

        save_recommendation(advisor_id, result.get("client_id"), {
            "client_name":       client_data["client_name"],
            "age":               client_data["age"],
            "life_stage":        client_data["life_stage"],
            "amount":            client_data["amount"],
            "risk":              client_data["risk"],
            "horizon":           client_data["horizon"],
            "selected_option":   client_data.get("selected_option", ""),
            "ai_data":           ai_data,
            "allocation":        client_data["allocation"],
            "suitability_note":  client_data["suitability_note"],
            "score":             client_data["score"],
            "instrument_prices": instrument_prices,
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

# ── Edit Client (load existing recommendation for editing) ─
@main.route("/edit-client/<client_id>")
def edit_client(client_id):
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    client     = get_client(client_id, advisor_id)

    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("main.clients"))

    recs = get_client_recommendations(advisor_id, client_id)
    latest_rec = recs[0] if recs else None

    if not latest_rec or not latest_rec.get("ai_data"):
        flash("No editable recommendation data found for this client.", "error")
        return redirect(url_for("main.view_client", client_id=client_id))

    ai_data = latest_rec.get("ai_data", {})
    selected_label = latest_rec.get("selected_option", "")
    selected_id = selected_label[0] if selected_label else None
    options = ai_data.get("options", [])
    selected_option = next((o for o in options if o.get("id") == selected_id), None)

    if not selected_option:
        flash("Could not find the selected option for this recommendation.", "error")
        return redirect(url_for("main.view_client", client_id=client_id))

    return render_template("portal/edit_client.html",
        advisor=session.get("advisor"),
        client=client,
        option=selected_option,
        market_data=latest_rec.get("ai_data", {}))

# ── Save Edited Client ──────────────────────────────────────
@main.route("/save-edited-client/<client_id>", methods=["POST"])
def save_edited_client(client_id):
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    client = get_client(client_id, advisor_id)

    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("main.clients"))

    try:
        allocation = json.loads(request.form.get("allocation", "{}"))
        instruments = json.loads(request.form.get("instruments", "{}"))
        suitability_note = request.form.get("suitability_note", "")

        score = portfolio_score(client["risk"], client["horizon"], client["age"])
        flags = get_advisor_flags(client["risk"], client["horizon"], client["age"])

        result = update_client(client_id, advisor_id, {
            "allocation": allocation,
            "score": score,
            "flags": flags,
            "suitability_note": suitability_note,
        })

        if result["success"]:
            instrument_prices = fetch_instrument_prices(instruments)

            save_recommendation(advisor_id, client_id, {
                "client_name":       client["client_name"],
                "age":               client["age"],
                "life_stage":        client["life_stage"],
                "amount":            client["amount"],
                "risk":              client["risk"],
                "horizon":           client["horizon"],
                "selected_option":   request.form.get("selected_option", ""),
                "ai_data":           {
                    "options": [{
                        "id": request.form.get("option_id", ""),
                        "name": request.form.get("option_name", ""),
                        "tagline": "",
                        "recommended": False,
                        "allocation": allocation,
                        "instruments": instruments,
                        "reasoning": "Edited by advisor after initial recommendation.",
                        "key_considerations": [],
                        "flags": []
                    }],
                    "market_context": "",
                    "advisor_note": ""
                },
                "allocation":        allocation,
                "suitability_note":  suitability_note,
                "score":             score,
                "instrument_prices": instrument_prices,
            })

            flash("Recommendation updated successfully.", "success")
        else:
            flash(result["message"], "error")

    except Exception as e:
        print(f"Save edited client error: {str(e)}")
        flash("Could not update recommendation. Please try again.", "error")

    return redirect(url_for("main.view_client", client_id=client_id))

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

# ── Generate Talking Points ───────────────────────────────
@main.route("/generate-talking-points", methods=["POST"])
def generate_talking_points():
    if not session.get("logged_in"):
        return json.dumps({"success": False})

    try:
        data        = request.get_json()
        client_name = data.get("client_name", "")
        age         = data.get("age", 0)
        life_stage  = data.get("life_stage", "")
        risk        = data.get("risk", "")
        horizon     = data.get("horizon", 0)
        amount      = data.get("amount", 0)
        score       = data.get("score", 0)
        last_note   = data.get("last_note", "")

        from openai import OpenAI
        import os
        ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""You are a senior financial advisor preparing for a client meeting.

CLIENT: {client_name}
Age: {age} | Life Stage: {life_stage} | Risk: {risk}
Investment: ${amount:,} | Horizon: {horizon} years | Score: {score}/100
Last meeting notes: {last_note if last_note else 'No previous notes'}

Generate exactly 4 specific conversation starters for this client meeting.
Each should be a question or talking point tailored to this specific client.
Focus on: portfolio performance, life changes, goals, market conditions.

Return ONLY a JSON array of 4 strings:
["talking point 1", "talking point 2", "talking point 3", "talking point 4"]"""

        response = ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.7
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        if content.endswith("```"):
            content = content[:-3]

        points = json.loads(content.strip())
        return json.dumps({"success": True, "points": points})

    except Exception as e:
        print(f"Talking points error: {str(e)}")
        return json.dumps({"success": False, "error": str(e)})

# ── Meeting Prep Market Data ──────────────────────────────
@main.route("/meeting-prep-market-data", methods=["POST"])
def meeting_prep_market_data():
    if not session.get("logged_in"):
        return json.dumps({"success": False})

    try:
        data       = request.get_json()
        allocation = data.get("allocation", {})
        risk       = data.get("risk", "Medium")
        amount     = data.get("amount", 0)

        from market_data import get_rates
        try:
            rates = get_rates()
        except Exception:
            rates = {}

        # Use fallback values if FRED API fails
        t10 = rates.get("10_year_treasury") or None
        t1  = rates.get("1_year_treasury") or None
        cd  = rates.get("cd_1_year") or None

        # If any rate is unavailable return error so frontend shows message
        if not t10 or not t1 or not cd:
            return json.dumps({
                "success": False,
                "message": "Market data temporarily unavailable. Please reload the page to try again."
            })

        items = []

        # 10-Year Treasury insight
        bond_pct    = allocation.get("bond_etfs", 0)
        bond_amt    = round((bond_pct / 100) * amount) if bond_pct else 0
        t10_insight = f"Client has {bond_pct}% (${bond_amt:,}) in Bond ETFs — rising yields affect bond prices." if bond_pct > 0 else "No bond exposure in this portfolio."

        items.append({
            "label":     "10-Year Treasury Yield",
            "value":     f"{t10}%",
            "direction": "neutral",
            "sub":       "Long-term benchmark rate",
            "insight":   t10_insight
        })

        # 1-Year Treasury insight
        cd_pct     = allocation.get("cds", 0)
        cd_amt     = round((cd_pct / 100) * amount) if cd_pct else 0
        t1_insight = f"Client's {cd_pct}% (${cd_amt:,}) in CDs earns close to this rate." if cd_pct > 0 else "Consider CDs as a stable income option."

        items.append({
            "label":     "1-Year Treasury Yield",
            "value":     f"{t1}%",
            "direction": "neutral",
            "sub":       "Short-term rate benchmark",
            "insight":   t1_insight
        })

        # CD Rate insight
        eq_pct     = allocation.get("equity_etfs", 0) + allocation.get("growth_stocks", 0)
        cd_insight = f"With {eq_pct}% in equities, current CD rates offer a {risk.lower()}-risk alternative worth discussing." if eq_pct > 50 else f"Current best CD rate aligns well with this {risk.lower()} risk portfolio."

        items.append({
            "label":     "Best 1-Year CD Rate",
            "value":     f"{cd}%",
            "direction": "neutral",
            "sub":       "FDIC-insured guaranteed return",
            "insight":   cd_insight
        })

        return json.dumps({"success": True, "items": items})

    except Exception as e:
        print(f"Meeting prep market data error: {str(e)}")
        return json.dumps({"success": False})

# ── Market Watch ──────────────────────────────────────────
@main.route("/market-watch")
def market_watch():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id  = session["advisor"]["user_id"]
    all_clients = get_all_clients(advisor_id)

    # Get all unique instruments across all client portfolios
    from recommendations_db import get_all_recommendations
    all_recs = get_all_recommendations(advisor_id)

    instrument_count = {}
    for rec in all_recs:
        ai_data = rec.get("ai_data", {})
        if not ai_data:
            continue
        options = ai_data.get("options", [])
        sel_id  = rec.get("selected_option", "C")
        sel_id  = sel_id[0] if sel_id else "C"
        sel_opt = next((o for o in options if o.get("id") == sel_id), None)
        if not sel_opt:
            continue
        instruments = sel_opt.get("instruments", {})
        for cat, items in instruments.items():
            for inst in items:
                ticker = inst.get("ticker", "")
                if ticker and not ticker.startswith("CD-") and ticker != "TBILL":
                    if ticker not in instrument_count:
                        instrument_count[ticker] = {
                            "ticker": ticker,
                            "name":   inst.get("name", ticker),
                            "count":  0
                        }
                    instrument_count[ticker]["count"] += 1

    # Sort by most held
    portfolio_instruments = sorted(
        instrument_count.values(),
        key=lambda x: x["count"],
        reverse=True
    )[:15]

    return render_template("portal/market_watch.html",
        advisor=session.get("advisor"),
        portfolio_instruments=portfolio_instruments,
        client_count=len(all_clients))

# ── Regulatory News ───────────────────────────────────────
@main.route("/regulatory-news")
def regulatory_news():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    return render_template("portal/regulatory_news.html",
        advisor=session.get("advisor"))

# ── Regulatory News Data ──────────────────────────────────
@main.route("/regulatory-news-data", methods=["POST"])
def regulatory_news_data():
    if not session.get("logged_in"):
        return json.dumps({"success": False})

    data      = request.get_json()
    data_type = data.get("type", "")

    try:
        if data_type == "sec":
            items, cached_at = _get_cached_feed(
                "sec",
                lambda: _fetch_feed("https://www.sec.gov/news/pressreleases.rss", headers=SEC_HEADERS)
            )
            return json.dumps({"success": True, "items": items, "cached_at": cached_at})

        elif data_type == "finra":
            items, cached_at = _get_cached_feed(
                "finra",
                lambda: _fetch_feed("https://www.finra.org/rules-guidance/notices/rss")
            )
            return json.dumps({"success": True, "items": items, "cached_at": cached_at})

        elif data_type == "enforcement":
            items, cached_at = _get_cached_feed(
                "enforcement",
                lambda: _fetch_feed("https://www.sec.gov/enforcement-litigation/litigation-releases/rss", headers=SEC_HEADERS)
            )
            return json.dumps({"success": True, "items": items, "cached_at": cached_at})

        return json.dumps({"success": False})

    except Exception as e:
        print(f"Regulatory news error: {str(e)}")
        return json.dumps({"success": False})

# ── Market Watch Data
@main.route("/market-watch-data", methods=["POST"])
def market_watch_data():
    if not session.get("logged_in"):
        return json.dumps({"success": False})

    try:
        data      = request.get_json()
        data_type = data.get("type", "")

        import yfinance as yf
        from concurrent.futures import ThreadPoolExecutor

        # ── Indices ──────────────────────────────────────
        if data_type == "indices":
            index_tickers = {
                "^GSPC": "S&P 500",
                "^IXIC": "Nasdaq",
                "^DJI":  "Dow Jones",
                "^RUT":  "Russell 2000"
            }

            def fetch_index(item):
                ticker, name = item
                try:
                    info  = yf.Ticker(ticker).info
                    price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                    prev  = info.get("regularMarketPreviousClose", price)
                    change     = round(price - prev, 2)
                    change_pct = round((change / prev) * 100, 2) if prev else 0
                    return {
                        "ticker":     ticker,
                        "name":       name,
                        "price":      f"{price:,.2f}",
                        "change":     f"{'+' if change >= 0 else ''}{change:,.2f}",
                        "change_pct": change_pct,
                        "direction":  "up" if change >= 0 else "down"
                    }
                except Exception:
                    return {"ticker": ticker, "name": name, "price": "N/A",
                            "change": "N/A", "change_pct": 0, "direction": "flat"}

            with ThreadPoolExecutor(max_workers=4) as executor:
                indices = list(executor.map(fetch_index, index_tickers.items()))

            return json.dumps({"success": True, "indices": indices})

        # ── Rates ────────────────────────────────────────
        elif data_type == "rates":
            from market_data import get_rates
            try:
                rates = get_rates()
            except Exception:
                rates = {}

            rate_items = [
                {"label": "3-Month Treasury", "value": rates.get("3_month_treasury", "N/A")},
                {"label": "1-Year Treasury",  "value": rates.get("1_year_treasury",  "N/A")},
                {"label": "2-Year Treasury",  "value": rates.get("5_year_treasury",  "N/A")},
                {"label": "10-Year Treasury", "value": rates.get("10_year_treasury", "N/A")},
                {"label": "30-Year Treasury", "value": rates.get("30_year_treasury", "N/A")},
                {"label": "Best 1-Year CD",   "value": rates.get("cd_1_year",        "N/A")},
            ]

            return json.dumps({"success": True, "rates": rate_items})

        # ── Holdings ─────────────────────────────────────
        elif data_type == "holdings":
            tickers = data.get("tickers", [])

            def fetch_price(ticker):
                try:
                    info  = yf.Ticker(ticker).info
                    price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                    prev  = info.get("regularMarketPreviousClose", price)
                    change_pct = round(((price - prev) / prev) * 100, 2) if prev else 0
                    return ticker, {
                        "price":      round(price, 2),
                        "change_pct": change_pct
                    }
                except Exception:
                    return ticker, {"price": "N/A", "change_pct": 0}

            with ThreadPoolExecutor(max_workers=10) as executor:
                results = dict(executor.map(fetch_price, tickers))

            return json.dumps({"success": True, "prices": results})

       
     # ── Search by ticker or name ──────────────────────
        elif data_type == "search":
            query = data.get("ticker", "").strip()
            try:
                import requests as req

                # Use Yahoo Finance search API to find matching tickers
                search_url = f"https://query1.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=5&newsCount=0"
                headers    = {"User-Agent": "Mozilla/5.0"}
                response   = req.get(search_url, headers=headers, timeout=5)
                results    = response.json().get("quotes", [])

                matches = []
                for r in results:
                    ticker_sym = r.get("symbol", "")
                    name       = r.get("longname") or r.get("shortname", ticker_sym)
                    if ticker_sym and r.get("quoteType") in ["EQUITY", "ETF", "MUTUALFUND"]:
                        matches.append({
                            "ticker": ticker_sym,
                            "name":   name,
                            "type":   r.get("quoteType", "")
                        })

                return json.dumps({"success": True, "matches": matches})

            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        # ── Get single ticker detail ──────────────────────
        elif data_type == "ticker_detail":
            ticker = data.get("ticker", "").upper()
            try:
                info       = yf.Ticker(ticker).info
                price      = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                prev       = info.get("regularMarketPreviousClose", price)
                change_pct = round(((price - prev) / prev) * 100, 2) if prev else 0
                name       = info.get("longName") or info.get("shortName", ticker)

                return json.dumps({
                    "success": True,
                    "info": {
                        "ticker":         ticker,
                        "name":           name,
                        "price":          round(price, 2),
                        "change_pct":     change_pct,
                        "week52_high":    round(info.get("fiftyTwoWeekHigh", 0), 2),
                        "week52_low":     round(info.get("fiftyTwoWeekLow", 0), 2),
                        "pe_ratio":       round(info.get("trailingPE", 0), 1) if info.get("trailingPE") else "N/A",
                        "dividend_yield": f"{round(info.get('dividendYield', 0) * 100, 2)}%" if info.get("dividendYield") else "N/A",
                        "market_cap":     info.get("marketCap", 0)
                    }
                })
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

         # ── Top Gainers ───────────────────────────────────
        elif data_type == "gainers":
            try:
                import requests as req

                headers = {"User-Agent": "Mozilla/5.0"}

                # Fetch top gainers from Yahoo Finance screener
                gainers_url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&lang=en-US&region=US&scrIds=day_gainers&count=10"
                losers_url  = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&lang=en-US&region=US&scrIds=day_losers&count=5"

                gainers_resp = req.get(gainers_url, headers=headers, timeout=8)
                losers_resp  = req.get(losers_url,  headers=headers, timeout=8)

                gainers_data = gainers_resp.json()
                losers_data  = losers_resp.json()

                results = []

                # Process gainers
                gainers_quotes = gainers_data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                for q in gainers_quotes[:7]:
                    results.append({
                        "ticker":     q.get("symbol", ""),
                        "name":       q.get("longName") or q.get("shortName", ""),
                        "price":      round(q.get("regularMarketPrice", 0), 2),
                        "change_pct": round(q.get("regularMarketChangePercent", 0), 2),
                        "direction":  "up"
                    })

                # Process losers
                losers_quotes = losers_data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                for q in losers_quotes[:3]:
                    results.append({
                        "ticker":     q.get("symbol", ""),
                        "name":       q.get("longName") or q.get("shortName", ""),
                        "price":      round(q.get("regularMarketPrice", 0), 2),
                        "change_pct": round(q.get("regularMarketChangePercent", 0), 2),
                        "direction":  "down"
                    })

                if results:
                    return json.dumps({"success": True, "gainers": results})

                # Fallback to yfinance if Yahoo API fails
                raise Exception("No data from Yahoo screener")

            except Exception:
                # Fallback
                fallback_tickers = [
                    "NVDA", "MSFT", "AAPL", "GOOGL", "AMZN",
                    "META", "TSLA", "AMD", "CRM", "NFLX"
                ]

                def fetch_gainer(ticker):
                    try:
                        info  = yf.Ticker(ticker).info
                        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
                        prev  = info.get("regularMarketPreviousClose", price)
                        change_pct = round(((price - prev) / prev) * 100, 2) if prev else 0
                        name       = info.get("longName") or info.get("shortName", ticker)
                        return {
                            "ticker":     ticker,
                            "name":       name,
                            "price":      round(price, 2),
                            "change_pct": change_pct,
                            "direction":  "up" if change_pct > 0 else "down"
                        }
                    except Exception:
                        return None

                with ThreadPoolExecutor(max_workers=10) as executor:
                    results = list(executor.map(fetch_gainer, fallback_tickers))

                results = [r for r in results if r]
                results.sort(key=lambda x: x["change_pct"], reverse=True)

                return json.dumps({"success": True, "gainers": results})
            
         # ── News ─────────────────────────────────────────
        elif data_type == "news":
            import feedparser
            feeds = [
                ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
                ("Seeking Alpha", "https://seekingalpha.com/feed.xml"),
                ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
                ("Investing.com", "https://www.investing.com/rss/news.rss"),
            ]

            news_items = []
            for source, url in feeds:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:4]:
                        title = entry.get("title", "").strip()
                        link  = entry.get("link", "#")
                        if title and len(title) > 10:
                            news_items.append({
                                "title":  title,
                                "link":   link,
                                "source": source,
                                "date":   entry.get("published", "")[:16] if entry.get("published") else ""
                            })
                    if len(news_items) >= 10:
                        break
                except Exception:
                    continue

            if news_items:
                return json.dumps({"success": True, "news": news_items[:10]})

            # Fallback — use Yahoo Finance news API
            try:
                import requests as req
                headers  = {"User-Agent": "Mozilla/5.0"}
                response = req.get(
                    "https://query1.finance.yahoo.com/v1/finance/trending/US",
                    headers=headers, timeout=5
                )
                trending = response.json().get("finance", {}).get("result", [{}])[0].get("quotes", [])
                news_items = [{
                    "title":  f"{q.get('symbol', '')} is trending today",
                    "link":   f"https://finance.yahoo.com/quote/{q.get('symbol', '')}",
                    "source": "Yahoo Finance",
                    "date":   ""
                } for q in trending[:10]]
                return json.dumps({"success": True, "news": news_items})
            except Exception:
                return json.dumps({"success": False})

        return json.dumps({"success": False, "error": "Unknown data type"})

    except Exception as e:
        print(f"Market watch data error: {str(e)}")
        return json.dumps({"success": False, "error": str(e)})

# ── Portfolio Drift Analysis ──────────────────────────────
@main.route("/portfolio-drift", methods=["POST"])
def portfolio_drift():
    if not session.get("logged_in"):
        return json.dumps({"success": False})

    try:
        data            = request.get_json()
        allocation      = data.get("allocation", {})
        instruments     = data.get("instruments", {})
        amount          = data.get("amount", 0)
        original_prices = data.get("original_prices", {})

        results = _calculate_portfolio_drift(allocation, instruments, amount, original_prices)
        return json.dumps({"success": True, "results": results})

    except Exception as e:
        print(f"Portfolio drift error: {str(e)}")
        return json.dumps({"success": False, "error": str(e)})

DRIFT_CACHE_TTL_SECONDS = 3600  # 1 hour

def _get_client_drift_summary(advisor_id, client_id):
    try:
        recs = get_client_recommendations(advisor_id, client_id)
        if not recs:
            return {"status": "no_data", "max_drift_pct": None, "total_value": None}

        latest = recs[0]
        ai_data = latest.get("ai_data", {})
        selected_label = latest.get("selected_option", "")
        selected_id = selected_label[0] if selected_label else None

        if not ai_data or not selected_id:
            return {"status": "no_data", "max_drift_pct": None, "total_value": None}

        options = ai_data.get("options", [])
        selected = next((o for o in options if o.get("id") == selected_id), None)
        if not selected:
            return {"status": "no_data", "max_drift_pct": None, "total_value": None}

        instruments = selected.get("instruments", {})
        allocation  = latest.get("allocation", {})
        amount      = latest.get("amount", 0)
        original_prices = latest.get("instrument_prices", {})

        if not instruments or not original_prices:
            return {"status": "no_data", "max_drift_pct": None, "total_value": None}

        results = _calculate_portfolio_drift(allocation, instruments, amount, original_prices)
        if not results:
            return {"status": "no_data", "max_drift_pct": None, "total_value": None}

        max_drift = max(abs(r["drift_pct"]) for r in results)
        total_value = sum(r["current_value"] for r in results)
        status = "needs_rebalancing" if max_drift > 5 else "on_target"

        save_snapshot(advisor_id, client_id, total_value)

        return {"status": status, "max_drift_pct": max_drift, "total_value": total_value}

    except Exception as e:
        print(f"Drift summary error for client {client_id}: {str(e)}")
        return {"status": "error", "max_drift_pct": None, "total_value": None}


def _get_cached_drift_summary(advisor_id, client_id):
    import json as _json

    r = get_redis()
    cache_key = f"drift:{advisor_id}:{client_id}"

    cached = r.get(cache_key)
    if cached:
        parsed = _json.loads(cached)
        return parsed["summary"], parsed["timestamp"]

    now = time.time()
    summary = _get_client_drift_summary(advisor_id, client_id)
    r.setex(cache_key, DRIFT_CACHE_TTL_SECONDS, _json.dumps({"summary": summary, "timestamp": now}))
    return summary, now

def refresh_all_drift_caches():
    """
    Background job: refreshes drift cache for every client of every
    advisor, so pages always read from cache instead of computing live.
    """
    from concurrent.futures import ThreadPoolExecutor
    try:
        from clients_db import get_supabase
        advisors = get_supabase().table("advisors").select("id").execute()
        advisor_ids = [a["id"] for a in advisors.data] if advisors.data else []

        def refresh_one(pair):
            advisor_id, client_id = pair
            import json as _json
            r = get_redis()
            now = time.time()
            summary = _get_client_drift_summary(advisor_id, client_id)
            cache_key = f"drift:{advisor_id}:{client_id}"
            r.setex(cache_key, DRIFT_CACHE_TTL_SECONDS, _json.dumps({"summary": summary, "timestamp": now}))

        all_pairs = []
        for advisor_id in advisor_ids:
            clients = get_all_clients(advisor_id)
            for client in clients:
                all_pairs.append((advisor_id, client.get("id")))

        with ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(refresh_one, all_pairs)

        print(f"[BACKGROUND] Refreshed drift cache for {len(all_pairs)} clients")

    except Exception as e:
        print(f"[BACKGROUND] Drift refresh error: {str(e)}")

    
# ── Portfolio Review (list) ────────────────────────────────
@main.route("/portfolio-review")
def portfolio_review():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id  = session["advisor"]["user_id"]
    all_clients = get_all_clients(advisor_id)

    return render_template("portal/portfolio_review.html",
        advisor=session.get("advisor"),
        clients=all_clients)


@main.route("/portfolio-review-data", methods=["POST"])
def portfolio_review_data():
    if not session.get("logged_in"):
        return json.dumps({"success": False})

    try:
        advisor_id  = session["advisor"]["user_id"]
        all_clients = get_all_clients(advisor_id)

        results = []
        for client in all_clients:
            client_id = client.get("id")
            summary, cached_at = _get_cached_drift_summary(advisor_id, client_id)
            results.append({
                "client_id":     client_id,
                "client_name":   client.get("client_name", "Unknown"),
                "status":        summary["status"],
                "max_drift_pct": summary["max_drift_pct"],
                "cached_at":     cached_at
            })

        order = {"needs_rebalancing": 0, "error": 1, "no_data": 2, "on_target": 3}
        results.sort(key=lambda r: (order.get(r["status"], 9), -(r["max_drift_pct"] or 0)))

        return json.dumps({"success": True, "clients": results})

    except Exception as e:
        print(f"Portfolio review error: {str(e)}")
        return json.dumps({"success": False})


# ── Portfolio Review (detail) ──────────────────────────────
@main.route("/portfolio-review/<client_id>")
def portfolio_review_detail(client_id):
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    client     = get_client(client_id, advisor_id)

    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("main.portfolio_review"))

    return render_template("portal/portfolio_review_detail.html",
        advisor=session.get("advisor"),
        client=client)


@main.route("/portfolio-review-detail-data/<client_id>", methods=["POST"])
def portfolio_review_detail_data(client_id):
    if not session.get("logged_in"):
        return json.dumps({"success": False})

    try:
        advisor_id = session["advisor"]["user_id"]
        recs = get_client_recommendations(advisor_id, client_id)

        if not recs:
            return json.dumps({"success": False, "message": "No saved recommendation for this client yet."})

        latest = recs[0]
        ai_data = latest.get("ai_data", {})
        selected_label = latest.get("selected_option", "")
        selected_id = selected_label[0] if selected_label else None
        options = ai_data.get("options", [])
        selected = next((o for o in options if o.get("id") == selected_id), None)

        if not selected:
            return json.dumps({"success": False, "message": "No saved recommendation for this client yet."})

        instruments = selected.get("instruments", {})
        allocation  = latest.get("allocation", {})
        amount      = latest.get("amount", 0)
        original_prices = latest.get("instrument_prices", {})

        drift_results = _calculate_portfolio_drift(allocation, instruments, amount, original_prices)
        rebalance_actions, tax_loss_opportunities = _build_action_plan(drift_results)
        snapshots = get_client_snapshots(advisor_id, client_id)

        return json.dumps({
            "success": True,
            "amount": amount,
            "drift": drift_results,
            "snapshots": snapshots,
            "rebalance_actions": rebalance_actions,
            "tax_loss_opportunities": tax_loss_opportunities
        })

    except Exception as e:
        print(f"Portfolio review detail error: {str(e)}")
        return json.dumps({"success": False})                
# ── Meeting Prep ──────────────────────────────────────────
@main.route("/clients/<client_id>/meeting-prep")
def meeting_prep(client_id):
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    client     = get_client(client_id, advisor_id)

    if not client:
        flash("Client not found.", "error")
        return redirect(url_for("main.clients"))

    try:
        recs = get_client_recommendations(advisor_id, client_id)
        latest_rec = recs[0] if recs else None
    except Exception:
        latest_rec = None

    try:
        from notes_db import get_client_notes
        notes = get_client_notes(advisor_id, client_id)
    except Exception:
        notes = []

    from datetime import datetime
    now = datetime.now()
    return render_template("clients/meeting_prep.html",
        advisor=session.get("advisor"),
        client=client,
        latest_rec=latest_rec,
        notes=notes,
        today=now.strftime("%B %d, %Y"),
        today_iso=now.strftime("%Y-%m-%d"))


# ── Meeting Prep Landing ──────────────────────────────────
@main.route("/meeting-prep")
def meeting_prep_landing():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id  = session["advisor"]["user_id"]
    all_clients = get_all_clients(advisor_id)

    return render_template("clients/meeting_prep_landing.html",
        advisor=session.get("advisor"),
        clients=all_clients)

# ── All Recommendations ───────────────────────────────────
@main.route("/recommendations")
def recommendations():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id  = session["advisor"]["user_id"]
    all_recs    = get_all_recommendations(advisor_id)
    all_clients = get_all_clients(advisor_id)

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
    rec        = get_recommendation(advisor_id, rec_id)

    if not rec:
        flash("Recommendation not found.", "error")
        return redirect(url_for("main.recommendations"))

    return render_template("recommendations/view.html",
        advisor=session.get("advisor"),
        rec=rec)


# ── Delete Recommendation ─────────────────────────────────
@main.route("/recommendations/delete/<rec_id>", methods=["POST"])
def delete_recommendation_route(rec_id):
    if not session.get("logged_in"):
        return redirect(url_for("main.login"))

    advisor_id = session["advisor"]["user_id"]
    delete_recommendation(advisor_id, rec_id)
    flash("Recommendation deleted.", "success")
    return redirect(url_for("main.recommendations"))


# ── Portfolio Notes ───────────────────────────────────────
@main.route("/notes")
def notes():
    if not session.get("logged_in"):
        flash("Please log in to continue.", "info")
        return redirect(url_for("main.login"))

    advisor_id  = session["advisor"]["user_id"]
    all_clients = get_all_clients(advisor_id)
    all_notes   = get_all_notes(advisor_id)

    return render_template("notes/list.html",
        advisor=session.get("advisor"),
        notes=all_notes,
        all_notes=all_notes,
        clients=all_clients,
        selected_client="",
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
    redirect_to  = request.form.get("redirect_to", "notes")

    if not client_id or not subject or not body:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("main.notes"))

    result = add_note(advisor_id, client_id, subject, body, meeting_date)

    if result["success"]:
        flash("Note saved successfully.", "success")
    else:
        flash("Could not save note. Please try again.", "error")

    if redirect_to == "meeting_prep":
        return redirect(url_for("main.meeting_prep", client_id=client_id))

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

    result = update_note(note_id, advisor_id, subject, body, meeting_date)

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

    try:
        recs = get_client_recommendations(advisor_id, client_id)
        if recs:
            latest_rec        = recs[0]
            ai_data           = latest_rec.get("ai_data", {})
            selected_option_label = latest_rec.get("selected_option", "")
            selected_option_id    = selected_option_label[0] if selected_option_label else None

            if ai_data and selected_option_id:
                options  = ai_data.get("options", [])
                selected = next(
                    (o for o in options if o.get("id") == selected_option_id),
                    options[0] if options else None
                )
                if selected:
                    client["recommendation_data"] = selected
    except Exception as e:
        print(f"Could not fetch recommendation data: {str(e)}")

    pdf_buffer = generate_pdf_report(client, session["advisor"])
    filename   = f"AdvisorNest_{client['client_name'].replace(' ', '_')}_Report.pdf"

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


# ── Validate Ticker ───────────────────────────────────────
@main.route("/validate-ticker/<ticker>")
def validate_ticker(ticker):
    if not session.get("logged_in"):
        return json.dumps({"valid": False})
    try:
        import yfinance as yf
        t     = yf.Ticker(ticker.upper())
        info  = t.info
        name  = info.get("longName") or info.get("shortName", "")
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        if name:
            return json.dumps({
                "valid":  True,
                "ticker": ticker.upper(),
                "name":   name,
                "price":  price
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
        data        = request.get_json()
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


# ── Logout ────────────────────────────────────────────────
@main.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("main.login"))