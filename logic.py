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
    Generates an auto-written suitability note documenting
    why this recommendation is appropriate for this client.
    This is what advisors need for compliance documentation.
    """
    risk_description = {
        "high":   "aggressive growth",
        "medium": "balanced growth and income",
        "low":    "capital preservation and income"
    }.get(risk.lower(), "balanced")

    largest = max(allocation, key=allocation.get)
    largest_pct = allocation[largest]

    note = f"""SUITABILITY ASSESSMENT NOTE

Client: {client_name}
Age: {age} | Life Stage: {life_stage}
Investment Amount: ${amount:,}
Risk Tolerance: {risk.title()}
Time Horizon: {horizon} years

RECOMMENDATION RATIONALE:
Based on the client profile above, this portfolio allocation 
has been designed to achieve {risk_description} objectives. 

The recommended allocation places the largest weighting 
({largest_pct}%) in {largest}, which is appropriate given 
the client's {risk.lower()} risk tolerance and {horizon}-year 
investment horizon.

{"Given the client's age of " + str(age) + ", the allocation has been adjusted toward more conservative instruments to prioritize capital preservation." if age > 55 else ""}
{"The short time horizon of " + str(horizon) + " years has been reflected in reduced equity exposure to ensure adequate liquidity." if horizon < 5 else ""}

This recommendation was generated using AdvisorNest as a 
decision support tool. The final recommendation has been 
reviewed and approved by the licensed financial advisor.

ADVISOR CONFIRMATION:
This allocation is suitable for the client based on their 
stated investment objectives, risk tolerance, time horizon, 
and financial situation as documented above.

Advisor: ___________________________
Date: ___________________________
Signature: ___________________________

⚖ This document was prepared using AdvisorNest decision 
support software. All recommendations require advisor review 
and client suitability assessment before implementation.
"""
    return note