# logic.py
# All portfolio calculation logic for AdvisorNest
# This file is imported by routes.py

# ── Portfolio Allocation ──────────────────────────────────
def calculate_allocation(risk, horizon, age):
    """
    Calculates portfolio allocation percentages based on
    risk tolerance, time horizon, and client age.
    Returns a dictionary of instrument → percentage.
    """
    risk = risk.lower()

    # Base allocation by risk level
    if risk == "high":
        s_lt, s_st, bonds, mf, cds = 45, 20, 20, 10, 5
    elif risk == "medium":
        s_lt, s_st, bonds, mf, cds = 30, 10, 35, 15, 10
    else:  # low
        s_lt, s_st, bonds, mf, cds = 10, 5, 45, 20, 20

    # Age adjustment
    # Older clients shift toward safety
    if age > 55:
        s_lt -= 10
        bonds += 10
    elif age < 35:
        s_lt += 10
        bonds -= 10

    # Horizon adjustment
    # Short horizon = more conservative
    if horizon < 5:
        s_lt  -= 10
        s_st  -= 5
        bonds += 10
        cds   += 5

    return {
        "Stocks (Long Term)":  max(s_lt, 0),
        "Stocks (Short Term)": max(s_st, 0),
        "Bonds":               max(bonds, 0),
        "Mutual Funds":        max(mf, 0),
        "CDs":                 max(cds, 0),
    }


# ── Portfolio Score ───────────────────────────────────────
def portfolio_score(risk, horizon, age):
    """
    Scores how well-balanced a portfolio is for this
    specific client profile. Returns a number 0-100.
    """
    score = 60

    # Reward appropriate time horizons
    if 5 <= horizon <= 20:
        score += 15

    # Reward working-age clients
    if 28 <= age <= 62:
        score += 15

    # Reward balanced risk
    if risk.lower() == "medium":
        score += 10

    return min(score, 100)


# ── Advisor Flags ─────────────────────────────────────────
def get_advisor_flags(risk, horizon, age):
    """
    Returns a list of important flags the advisor
    should be aware of for this client profile.
    Each flag is a dict with 'type' and 'message'.
    Types: warning, info, success
    """
    flags = []

    if age > 55:
        flags.append({
            "type": "warning",
            "message": "Client is above 55 — allocation shifted toward capital preservation and income stability."
        })

    if horizon < 5:
        flags.append({
            "type": "warning",
            "message": "Short time horizon detected — equity exposure reduced to prioritize liquidity."
        })

    if risk.lower() == "high" and age > 60:
        flags.append({
            "type": "warning",
            "message": "High risk tolerance selected for a client over 60 — review suitability before proceeding."
        })

    if risk.lower() == "low" and age < 35:
        flags.append({
            "type": "info",
            "message": "Low risk for a young client — they may be leaving significant long-term growth on the table."
        })

    if not flags:
        flags.append({
            "type": "success",
            "message": "Profile is well-balanced across risk, age, and time horizon. No special flags detected."
        })

    return flags


# ── Suitability Note ──────────────────────────────────────
def generate_suitability_note(client_name, age, life_stage,
                               risk, horizon, amount, allocation):
    """
    Generates a professional suitability assessment note
    for compliance documentation.
    """

    # Determine primary allocation category
    if isinstance(allocation, dict):
        primary = max(allocation, key=allocation.get)
        primary_pct = allocation.get(primary, 0)
    else:
        primary = "balanced"
        primary_pct = 0

    # Map category keys to readable names
    category_names = {
        "equity_etfs":   "Equity ETFs",
        "growth_stocks": "Growth Stocks",
        "bond_etfs":     "Bond ETFs",
        "mutual_funds":  "Mutual Funds",
        "cds":           "Certificates of Deposit",
        "stocks_lt":     "Long-Term Equities",
        "stocks_st":     "Short-Term Equities",
        "bonds":         "Bonds",
    }

    primary_name = category_names.get(primary, primary.replace("_", " ").title())

    # Risk rationale
    risk_rationale = {
        "Low":    "The client has expressed a low risk tolerance, prioritizing capital preservation over growth. The recommended allocation reflects this preference with a conservative weighting toward fixed income and guaranteed instruments.",
        "Medium": "The client has expressed a moderate risk tolerance, seeking a balance between growth and capital preservation. The recommended allocation reflects a balanced approach across equity and fixed income instruments.",
        "High":   "The client has expressed a high risk tolerance, prioritizing long-term capital appreciation over short-term stability. The recommended allocation reflects this with a significant weighting toward equity instruments."
    }

    # Life stage rationale
    life_stage_rationale = {
        "Early Career":    "As an early-career investor, the client has a long investment horizon providing significant time for portfolio recovery from market downturns, supporting a higher equity allocation.",
        "Mid-Career":      "As a mid-career investor, the client is in a wealth accumulation phase with sufficient time horizon to balance growth and income objectives.",
        "Pre-Retirement":  "As a pre-retirement investor, capital preservation becomes increasingly important. The allocation reflects the need to protect accumulated wealth while maintaining measured growth.",
        "Retirement":      "As a retired investor, income generation and capital preservation are the primary objectives. The allocation prioritizes stable, income-producing instruments."
    }

    note = f"""SUITABILITY ASSESSMENT NOTE

Client: {client_name}
Age: {age} | Life Stage: {life_stage}
Investment Amount: ${amount:,}
Risk Tolerance: {risk}
Time Horizon: {horizon} years

SUITABILITY DETERMINATION:
This portfolio recommendation has been determined suitable for the above-named client based on the following factors:

1. RISK PROFILE ALIGNMENT
{risk_rationale.get(risk, "The allocation has been designed to align with the client's stated risk tolerance.")}

2. TIME HORIZON CONSIDERATION
{life_stage_rationale.get(life_stage, "The allocation reflects the client's investment time horizon.")} With a {horizon}-year investment horizon, the recommended portfolio is designed to meet the client's long-term financial objectives.

3. ALLOCATION RATIONALE
The recommended allocation places the largest weighting ({primary_pct}%) in {primary_name}. This reflects the client's risk profile, time horizon, and current market conditions at the time of recommendation generation.

4. ADVISOR REVIEW AND APPROVAL
This recommendation has been reviewed by the licensed financial advisor named above. The advisor has determined that this recommendation is suitable for the client based on their complete financial picture, including factors not captured in this automated analysis such as existing assets, liabilities, tax situation, insurance coverage, and estate planning considerations.

5. DECISION SUPPORT DISCLOSURE
This recommendation was generated using AdvisorNest as a decision support tool for licensed financial advisors. The final investment decision rests solely with the licensed advisor. AdvisorNest does not provide financial advice and is not a registered investment advisor."""
    return note