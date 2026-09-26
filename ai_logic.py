import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

_client = None

def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

# ── Option Definitions ────────────────────────────────────
OPTION_DEFINITIONS = {
    "A": {
        "name": "Capital Preservation",
        "tagline": "Safety and income above all else",
        "recommended": False,
        "ranges": {
            "equity_etfs":   "5 to 15",
            "growth_stocks": "0",
            "bond_etfs":     "40 to 55",
            "mutual_funds":  "20 to 30",
            "cds":           "15 to 25"
        },
        "context": "This is the MOST CONSERVATIVE option. Focus on capital preservation, income, and safety. Minimal equity exposure. Heavy fixed income and CDs."
    },
    "B": {
        "name": "Conservative Growth",
        "tagline": "Stability with modest appreciation",
        "recommended": False,
        "ranges": {
            "equity_etfs":   "20 to 30",
            "growth_stocks": "0 to 8",
            "bond_etfs":     "30 to 40",
            "mutual_funds":  "15 to 25",
            "cds":           "10 to 20"
        },
        "context": "This is the SECOND most conservative option. Slightly more equity than Option A but still bond-heavy. Option A is more conservative than this. Option C is more aggressive than this."
    },
    "C": {
        "name": "Balanced Growth",
        "tagline": "Optimal risk-adjusted returns",
        "recommended": True,
        "ranges": {
            "equity_etfs":   "30 to 40",
            "growth_stocks": "10 to 20",
            "bond_etfs":     "20 to 30",
            "mutual_funds":  "10 to 20",
            "cds":           "5 to 15"
        },
        "context": "This is the BALANCED option and the AI recommended choice. Equal weight between growth and stability. Option B is more conservative than this. Option D is more aggressive than this."
    },
    "D": {
        "name": "Aggressive Growth",
        "tagline": "Maximum long-term growth potential",
        "recommended": False,
        "ranges": {
            "equity_etfs":   "35 to 50",
            "growth_stocks": "25 to 40",
            "bond_etfs":     "5 to 15",
            "mutual_funds":  "5 to 15",
            "cds":           "0 to 8"
        },
        "context": "This is the MOST AGGRESSIVE option. Maximum equity and growth stock exposure. Minimal fixed income. Option C is more conservative than this."
    }
}

def normalize_category_totals(option):
    """
    Forces the five category-level allocation percentages
    (equity_etfs, growth_stocks, bond_etfs, mutual_funds, cds)
    to sum exactly to 100 — regardless of what the AI actually
    returned. Fixes cases like 40+30+10+10+0 = 90.
    """
    categories = ["equity_etfs", "growth_stocks", "bond_etfs", "mutual_funds", "cds"]
    allocation = option.get("allocation", {})
    current_total = sum(allocation.get(cat, 0) for cat in categories)

    if current_total <= 0 or abs(current_total - 100) < 0.01:
        return option

    scale = 100 / current_total
    running_total = 0

    for i, cat in enumerate(categories):
        if i == len(categories) - 1:
            new_pct = round(100 - running_total, 2)
        else:
            new_pct = round(allocation.get(cat, 0) * scale, 2)
            running_total += new_pct
        allocation[cat] = max(new_pct, 0)

    option["allocation"] = allocation
    return option

def normalize_option_allocations(option, amount):
    """
    Forces each category's instrument allocation_pct values to sum
    exactly to that category's declared allocation percentage —
    regardless of what the AI actually returned. Fixes cases where
    the AI leaves a gap (e.g. category says 15% but only lists one
    instrument at 10%).
    """
    categories = ["equity_etfs", "growth_stocks", "bond_etfs", "mutual_funds", "cds"]

    for cat in categories:
        target_pct = option.get("allocation", {}).get(cat, 0)
        instruments = option.get("instruments", {}).get(cat, [])

        if not instruments or target_pct <= 0:
            continue

        current_sum = sum(inst.get("allocation_pct", 0) for inst in instruments)
        if current_sum <= 0:
            continue

        scale = target_pct / current_sum
        running_total = 0

        for i, inst in enumerate(instruments):
            if i == len(instruments) - 1:
                new_pct = round(target_pct - running_total, 2)
            else:
                new_pct = round(inst["allocation_pct"] * scale, 2)
                running_total += new_pct

            inst["allocation_pct"] = max(new_pct, 0)
            inst["dollar_amount"] = round((inst["allocation_pct"] / 100) * amount)

    return option

def generate_single_option(
    option_id, client_name, age, life_stage,
    risk, horizon, amount, market_data, max_retries=2
):
    """
    Generates one portfolio option via OpenAI.
    Retries up to `max_retries` times, and instead of crashing
    when the API returns no content (None), it logs the real reason
    (refusal text or finish_reason) and retries before giving up.
    """
    rates = market_data.get("rates", {})
    treasury_10y = rates.get("10_year_treasury", "N/A")
    treasury_1y  = rates.get("1_year_treasury", "N/A")
    cd_1y        = rates.get("cd_1_year", "N/A")

    opt = OPTION_DEFINITIONS[option_id]
    ranges = opt["ranges"]

    prompt = f"""You are a senior portfolio analyst providing DECISION SUPPORT to licensed financial advisors.

Generate ONE specific portfolio option for this client.

CLIENT PROFILE:
- Name: {client_name}
- Age: {age}
- Life Stage: {life_stage}
- Risk Tolerance: {risk}
- Investment Amount: ${amount:,}
- Time Horizon: {horizon} years

CURRENT MARKET CONDITIONS:
- 10-Year Treasury Yield: {treasury_10y}%
- 1-Year Treasury Yield: {treasury_1y}%
- Best 1-Year CD Rate: {cd_1y}%

YOU ARE GENERATING: Option {option_id} — {opt['name']}
{opt['context']}

STRICT ALLOCATION RANGES FOR THIS OPTION (must stay within these):
- equity_etfs:   {ranges['equity_etfs']}%
- growth_stocks: {ranges['growth_stocks']}%
- bond_etfs:     {ranges['bond_etfs']}%
- mutual_funds:  {ranges['mutual_funds']}%
- cds:           {ranges['cds']}%
- Total must equal exactly 100%

APPROVED INSTRUMENTS ONLY:

EQUITY ETFs: VOO, VTI, ITOT, SCHB, IVV, SCHD, VYM, DGRO, NOBL, DVY, QQQ, VUG, SCHG, IWF, VXUS, VEA, VWO, EFA, XLK, XLF, XLV, XLE, XLU, XLP, XLI, AOM, AOA, AOK
hold_period: "Core — Long Term Hold" or "Tactical — 12 to 18 Months"

GROWTH STOCKS: MSFT, AAPL, GOOGL, AMZN, NVDA, META, JNJ, UNH, PFE, ABBV, JPM, BAC, WFC, GS, HD, MCD, COST, CAT, HON, UNP, BRK-B, PG, KO
hold_period: "Strategic — 5 to 10 Years", "Strategic — 10+ Years", "Tactical — 6 to 12 Months", "Tactical — 12 to 18 Months"

BOND ETFs: BND, AGG, BNDX, TLT, IEF, SHY, LQD, HYG, TIP, MUB
hold_period: "Income — Long Term Hold" or "Duration Play — 12 to 24 Months"

MUTUAL FUNDS: VFIAX, VBTLX, VWELX, FXAIX, FZROX, PIMIX, DODGX

CDs: CD-3M, CD-6M, CD-1Y, CD-2Y, TBILL

RULES:
- Only use instruments from the approved lists above
- If growth_stocks range is 0% leave the array empty
- Amounts under $50K prefer ETFs over individual stocks
- Client over 60 with high risk: add a flag
- Client under 35 with low risk: add a flag
- CRITICAL: instrument allocation_pct values within each category MUST sum exactly to the category allocation percentage
- Example: if equity_etfs = 35%, then all equity_etf instruments must sum to exactly 35%
- Use multiple instruments per category to fill the full allocation
- Never leave allocation gaps — every percentage point must be assigned to an instrument

Return ONLY this exact JSON structure:
{{
  "id": "{option_id}",
  "name": "{opt['name']}",
  "tagline": "{opt['tagline']}",
  "recommended": {'true' if opt['recommended'] else 'false'},
  "allocation": {{
    "equity_etfs": <number within {ranges['equity_etfs']}>,
    "growth_stocks": <number within {ranges['growth_stocks']}>,
    "bond_etfs": <number within {ranges['bond_etfs']}>,
    "mutual_funds": <number within {ranges['mutual_funds']}>,
    "cds": <number within {ranges['cds']}>
  }},
  "instruments": {{
    "equity_etfs": [
      {{"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "specific reason for this client", "conviction": "High", "hold_period": "Core — Long Term Hold"}}
    ],
    "growth_stocks": [],
    "bond_etfs": [
      {{"ticker": "BND", "name": "Vanguard Total Bond ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "specific reason for this client", "conviction": "High", "hold_period": "Income — Long Term Hold"}}
    ],
    "mutual_funds": [
      {{"ticker": "VWELX", "name": "Vanguard Wellington Fund", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "specific reason for this client", "conviction": "High", "hold_period": "Core — Long Term Hold"}}
    ],
    "cds": [
      {{"ticker": "CD-1Y", "name": "1-Year Certificate of Deposit", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "specific reason for this client", "conviction": "High", "hold_period": "1 Year"}}
    ]
  }},
  "reasoning": "Write 2-3 specific paragraphs explaining why this exact allocation suits {client_name} aged {age} with {risk} risk tolerance and {horizon} year horizon. Reference current market conditions including 10Y Treasury at {treasury_10y}%.",
  "key_considerations": [
    "Specific consideration 1 tailored to this client and option",
    "Specific consideration 2",
    "Specific consideration 3"
  ],
  "flags": []
}}

Calculate dollar_amount as (allocation_pct / 100) * {amount}
Replace example instruments with your actual picks from the approved lists.
Return ONLY valid JSON. No markdown. No explanation."""

    last_error = "unknown error"

    for attempt in range(max_retries):
        try:
            response = get_client().chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"You are generating Option {option_id} — {opt['name']} for a portfolio recommendation tool. Return only valid JSON. Never use instruments outside the approved universe. Keep allocations strictly within the specified ranges."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=1200,
                temperature=0.2
            )

            message = response.choices[0].message

            if message.content is None:
                last_error = (
                    getattr(message, "refusal", None)
                    or f"empty content, finish_reason={response.choices[0].finish_reason}"
                )
                print(f"Option {option_id} attempt {attempt+1}: None content — {last_error}")
                continue

            content = message.content.strip()

            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            if content.endswith("```"):
                content = content[:-3]

            option = json.loads(content.strip())
            option = normalize_category_totals(option)
            option = normalize_option_allocations(option, amount)
            return {"success": True, "option": option}

        except json.JSONDecodeError as e:
            last_error = str(e)
            print(f"Option {option_id} attempt {attempt+1} JSON error: {last_error}")
            continue

        except Exception as e:
            last_error = str(e)
            print(f"Option {option_id} attempt {attempt+1} error: {last_error}")
            continue

    return {"success": False, "option_id": option_id, "error": last_error}


def generate_market_context(
    client_name, risk, treasury_10y, cd_1y
):
    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": f"""Write a market context statement (1-2 sentences) explaining how current market conditions with 10-Year Treasury at {treasury_10y}% and CD rates at {cd_1y}% influence portfolio recommendations for a {risk} risk client.
Return only a JSON object:
{{"market_context": "your 1-2 sentence market context here", "advisor_note": "The licensed financial advisor makes the final investment decision on all recommendations. These recommendations were generated by AdvisorNest as a decision support tool and must be reviewed against the client complete financial picture before implementation."}}"""
                }
            ],
            max_tokens=200,
            temperature=0.2
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        if content.endswith("```"):
            content = content[:-3]

        return json.loads(content.strip())

    except Exception as e:
        print(f"Market context error: {str(e)}")
        return {
            "market_context": f"Current market conditions with 10-Year Treasury at {treasury_10y}% and CD rates at {cd_1y}% have influenced these recommendations.",
            "advisor_note": "The licensed financial advisor makes the final investment decision on all recommendations."
        }


def build_rule_based_option(option_id, client_name, age, risk, horizon, amount):
    """
    Used when an individual AI-generated option keeps failing even after
    retries. Produces a rule-based allocation scaled to that option's
    defined range, so the advisor still sees 4 distinct, correctly-tiered
    options instead of one generic fallback.
    """
    opt = OPTION_DEFINITIONS[option_id]
    ranges = opt["ranges"]

    def midpoint(range_str):
        parts = [float(p.strip()) for p in range_str.replace("to", "-").split("-")]
        return sum(parts) / len(parts) if len(parts) > 1 else parts[0]

    allocation = {
        "equity_etfs":   midpoint(ranges["equity_etfs"]),
        "growth_stocks": midpoint(ranges["growth_stocks"]),
        "bond_etfs":     midpoint(ranges["bond_etfs"]),
        "mutual_funds":  midpoint(ranges["mutual_funds"]),
        "cds":           midpoint(ranges["cds"]),
    }

    return {
        "id": option_id,
        "name": opt["name"],
        "tagline": opt["tagline"],
        "recommended": opt["recommended"],
        "allocation": allocation,
        "instruments": {
            "equity_etfs": [], "growth_stocks": [],
            "bond_etfs": [], "mutual_funds": [], "cds": []
        },
        "reasoning": f"AI-generated detail unavailable for this option; a rule-based {opt['name'].lower()} allocation was applied instead. Review instrument selection manually before presenting to the client.",
        "key_considerations": [
            "This option used rule-based allocation, not AI-generated instrument selection",
            "Manually select specific instruments before finalizing",
            "Review allocation against client's full financial picture"
        ],
        "flags": ["Rule-based allocation — AI-generated detail was unavailable for this option"]
    }


def generate_ai_recommendation(
    client_name, age, life_stage, risk,
    horizon, amount, market_data
):
    rates = market_data.get("rates", {})
    treasury_10y = rates.get("10_year_treasury", "N/A")
    cd_1y        = rates.get("cd_1_year", "N/A")

    option_ids = ["A", "B", "C", "D"]
    results = {}

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:

            future_to_option = {
                executor.submit(
                    generate_single_option,
                    option_id,
                    client_name, age, life_stage,
                    risk, horizon, amount, market_data
                ): option_id
                for option_id in option_ids
            }

            future_context = executor.submit(
                generate_market_context,
                client_name, risk, treasury_10y, cd_1y
            )

            for future in as_completed(future_to_option):
                option_id = future_to_option[future]
                try:
                    result = future.result()
                    if result["success"]:
                        results[option_id] = result["option"]
                    else:
                        print(f"Option {option_id} failed: {result.get('error')}")
                except Exception as e:
                    print(f"Option {option_id} exception: {str(e)}")

            try:
                context_data = future_context.result()
            except Exception:
                context_data = {
                    "market_context": f"Current market conditions with 10-Year Treasury at {treasury_10y}% influenced these recommendations.",
                    "advisor_note": "The licensed financial advisor makes the final investment decision."
                }

        # Only fully fall back if EVERY option failed.
        # If some (but not all) options failed even after retries,
        # fill just those gaps with a rule-based option instead of
        # discarding the AI-generated ones that did succeed.
        if len(results) == 0:
            print("All 4 options failed, using full fallback")
            return {"success": False, "error": "No options generated"}

        partial_fallback_count = 0
        if len(results) < 4:
            print(f"Only got {len(results)}/4 options — filling gaps with rule-based options")
            missing = [oid for oid in option_ids if oid not in results]
            partial_fallback_count = len(missing)
            for oid in missing:
                results[oid] = build_rule_based_option(
                    oid, client_name, age, risk, horizon, amount
                )

        ordered_options = [results[oid] for oid in option_ids if oid in results]

        return {
            "success": True,
            "fallback": False,
            "partial_fallback_count": partial_fallback_count,
            "data": {
                "options": ordered_options,
                "market_context": context_data.get("market_context", ""),
                "advisor_note": context_data.get("advisor_note", "")
            }
        }

    except Exception as e:
        print(f"Parallel generation error: {str(e)}")
        return {"success": False, "error": str(e)}


def get_fallback_recommendation(risk, age, horizon, amount, client_name="the client"):
    """
    Instead of one generic "AI unavailable" card, this builds all 4
    rule-based options (same as build_rule_based_option), so even a
    total AI failure looks like a normal set of tiered recommendations
    to the advisor — not a visible outage.
    """
    options = [
        build_rule_based_option(oid, client_name, age, risk, horizon, amount)
        for oid in ["A", "B", "C", "D"]
    ]

    return {
        "success": True,
        "fallback": True,
        "data": {
            "options": options,
            "market_context": "Standard rule-based allocation applied for this recommendation.",
            "advisor_note": "The licensed advisor makes the final investment decision on all recommendations."
        }
    }


def generate_suitability_note_ai(
    client_name, age, life_stage, risk,
    horizon, amount, option_name, option_id,
    instruments, market_data
):
    rates = market_data.get("rates", {})
    treasury_10y = rates.get("10_year_treasury", "N/A")
    cd_1y = rates.get("cd_1_year", "N/A")

    instrument_summary = []
    for category, items in instruments.items():
        for inst in items:
            category_label = category.replace("_", " ").title()
            instrument_summary.append(
                f"{inst['ticker']} ({inst['name']}) — "
                f"{category_label} — "
                f"{inst['allocation_pct']}% — "
                f"{inst.get('hold_period', 'Long Term')}"
            )

    instrument_text = "\n".join(instrument_summary) if instrument_summary else "Standard allocation"

    prompt = f"""You are a senior compliance officer at a registered investment advisory firm.
Write a formal suitability assessment note for the following portfolio recommendation.

CLIENT PROFILE:
- Name: {client_name}
- Age: {age}
- Life Stage: {life_stage}
- Investment Amount: ${amount:,}
- Risk Tolerance: {risk}
- Time Horizon: {horizon} years

SELECTED PORTFOLIO OPTION: {option_id} — {option_name}

INSTRUMENTS SELECTED:
{instrument_text}

CURRENT MARKET CONDITIONS:
- 10-Year Treasury Yield: {treasury_10y}%
- Best 1-Year CD Rate: {cd_1y}%

Write exactly 4 formal paragraphs:

PARAGRAPH 1 — CLIENT PROFILE AND INVESTMENT OBJECTIVES:
State the client full name, age, life stage, investment amount, risk tolerance and time horizon. Describe what investment objective this specific option is designed to meet for this client.

PARAGRAPH 2 — EQUITY INSTRUMENT SUITABILITY:
Explain specifically why each equity instrument selected is appropriate for this client. Reference each ticker by name. Explain how each instrument aligns with the client age, risk tolerance and investment horizon. If no equity instruments, explain why a conservative fixed income focus is appropriate.

PARAGRAPH 3 — FIXED INCOME AND GUARANTEED INSTRUMENT SUITABILITY:
Explain why the bond ETFs, mutual funds and CDs selected are appropriate for this client. Reference the current 10-Year Treasury yield of {treasury_10y}% and CD rate of {cd_1y}%. Reference each ticker by name.

PARAGRAPH 4 — SUITABILITY DETERMINATION:
State that based on the above analysis this {option_name} recommendation is suitable for {client_name}. Reference FINRA Rule 2111 and SEC Regulation Best Interest. State that the licensed advisor has reviewed and approved this recommendation. State this was prepared using AdvisorNest as a decision support tool and the final investment decision rests with the licensed advisor.

Write in formal compliance language. Be specific. Reference actual tickers.
Return ONLY the 4 paragraphs of text. No JSON. No headers. Just the paragraphs separated by blank lines."""

    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior compliance officer writing formal SEC and FINRA compliant suitability documentation. Write in professional regulatory language. Be specific and reference actual instruments."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=800,
            temperature=0.2
        )

        note = response.choices[0].message.content.strip()
        return {"success": True, "note": note}

    except Exception as e:
        print(f"Suitability note error: {str(e)}")
        return {"success": False, "error": str(e)}