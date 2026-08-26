import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_ai_recommendation(
    client_name, age, life_stage, risk,
    horizon, amount, market_data
):
    rates = market_data.get("rates", {})
    treasury_10y = rates.get("10_year_treasury", "N/A")
    treasury_1y  = rates.get("1_year_treasury", "N/A")
    cd_1y        = rates.get("cd_1_year", "N/A")

    prompt = f"""You are a senior compliance officer and portfolio analyst at a registered investment advisory firm providing DECISION SUPPORT to licensed financial advisors. The advisor makes all final decisions.

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

APPROVED INSTRUMENT UNIVERSE — only use these:

EQUITY ETFs (equity_etfs):
hold_period must be "Core — Long Term Hold" or "Tactical — 12 to 18 Months"
VOO, VTI, ITOT, SCHB, IVV, SCHD, VYM, DGRO, NOBL, DVY, QQQ, VUG, SCHG, IWF, VXUS, VEA, VWO, EFA, XLK, XLF, XLV, XLE, XLU, XLP, XLI, AOM, AOA, AOK

GROWTH STOCKS (growth_stocks):
hold_period must be "Strategic — 5 to 10 Years", "Strategic — 10+ Years", "Tactical — 6 to 12 Months", or "Tactical — 12 to 18 Months"
MSFT, AAPL, GOOGL, AMZN, NVDA, META, JNJ, UNH, PFE, ABBV, JPM, BAC, WFC, GS, HD, MCD, COST, CAT, HON, UNP, BRK-B, PG, KO

BOND ETFs (bond_etfs):
hold_period must be "Income — Long Term Hold" or "Duration Play — 12 to 24 Months"
BND, AGG, BNDX, TLT, IEF, SHY, LQD, HYG, TIP, MUB

MUTUAL FUNDS (mutual_funds):
VFIAX, VBTLX, VWELX, FXAIX, FZROX, PIMIX, DODGX

CDs (cds):
CD-3M, CD-6M, CD-1Y, CD-2Y, TBILL

RULES:
- Only use instruments from the approved universe
- Amounts under $50K: prefer ETFs over individual stocks
- Amounts over $200K high risk: individual stocks appropriate
- Client over 60 with high risk: flag it
- Client under 35 with low risk: flag it
- Each option allocation sums to exactly 100
- equity_etfs + growth_stocks + bond_etfs + mutual_funds + cds = 100

SUITABILITY NOTE REQUIREMENTS — this is critical:
Each suitability_note must be exactly 4 paragraphs using formal SEC and FINRA compliance language:

Paragraph 1 — CLIENT PROFILE AND OBJECTIVES:
State the client name, age, life stage, investment amount, risk tolerance and time horizon. Describe the investment objective this option is designed to meet.

Paragraph 2 — EQUITY SUITABILITY:
Explain why each specific equity instrument selected is appropriate for this client. Reference the client age, risk tolerance and time horizon. For each ticker mentioned explain its role in the portfolio.

Paragraph 3 — FIXED INCOME AND GUARANTEED INSTRUMENTS:
Explain why the bond ETFs, mutual funds and CDs selected are appropriate. Reference current market conditions specifically mentioning the 10-Year Treasury yield of {treasury_10y}% and CD rate of {cd_1y}%. Explain how these provide stability relative to the client profile.

Paragraph 4 — SUITABILITY DETERMINATION:
State that based on the above analysis this recommendation is suitable for the named client. Reference that the licensed advisor has reviewed this recommendation and determined it meets the client suitability requirements under applicable regulations. State that this document was prepared using AdvisorNest as a decision support tool and that the final investment decision rests with the licensed advisor.

Generate exactly 4 options A B C D from most conservative to most aggressive. Mark one recommended=true.

Return ONLY valid JSON:
{{
  "options": [
    {{
      "id": "A",
      "name": "Capital Preservation",
      "tagline": "Safety and income above all else",
      "recommended": false,
      "allocation": {{
        "equity_etfs": 10,
        "growth_stocks": 0,
        "bond_etfs": 45,
        "mutual_funds": 25,
        "cds": 20
      }},
      "instruments": {{
        "equity_etfs": [
          {{
            "ticker": "SCHD",
            "name": "Schwab US Dividend Equity ETF",
            "allocation_pct": 10,
            "dollar_amount": 0,
            "reasoning": "Defensive dividend ETF for conservative income",
            "conviction": "High",
            "hold_period": "Core — Long Term Hold"
          }}
        ],
        "growth_stocks": [],
        "bond_etfs": [
          {{
            "ticker": "BND",
            "name": "Vanguard Total Bond Market ETF",
            "allocation_pct": 25,
            "dollar_amount": 0,
            "reasoning": "Core bond exposure for stability",
            "conviction": "High",
            "hold_period": "Income — Long Term Hold"
          }},
          {{
            "ticker": "MUB",
            "name": "iShares National Muni Bond ETF",
            "allocation_pct": 20,
            "dollar_amount": 0,
            "reasoning": "Tax-free municipal bond income",
            "conviction": "High",
            "hold_period": "Income — Long Term Hold"
          }}
        ],
        "mutual_funds": [
          {{
            "ticker": "VWELX",
            "name": "Vanguard Wellington Fund",
            "allocation_pct": 25,
            "dollar_amount": 0,
            "reasoning": "90-year track record balanced fund",
            "conviction": "High",
            "hold_period": "Core — Long Term Hold"
          }}
        ],
        "cds": [
          {{
            "ticker": "CD-1Y",
            "name": "1-Year Certificate of Deposit",
            "allocation_pct": 20,
            "dollar_amount": 0,
            "reasoning": "FDIC insured guaranteed return at current attractive rates",
            "conviction": "High",
            "hold_period": "1 Year"
          }}
        ]
      }},
      "reasoning": "Write 2-3 specific paragraphs explaining why this Capital Preservation allocation suits {client_name} aged {age} with {risk} risk tolerance and {horizon} year horizon given current market conditions.",
      "key_considerations": [
        "Specific consideration 1 for this client",
        "Specific consideration 2",
        "Specific consideration 3"
      ],
      "flags": [],
      "suitability_note": "Write exactly 4 formal compliance paragraphs for Option A Capital Preservation as described in the SUITABILITY NOTE REQUIREMENTS above. Reference SCHD, BND, MUB, VWELX, CD-1Y specifically. Use formal SEC FINRA language. Client is {client_name} age {age} {life_stage} ${amount:,} {risk} risk {horizon} years. Current 10Y Treasury {treasury_10y}% CD rate {cd_1y}%."
    }},
    {{
      "id": "B",
      "name": "Conservative Growth",
      "tagline": "Stability with modest appreciation",
      "recommended": false,
      "allocation": {{
        "equity_etfs": 25,
        "growth_stocks": 5,
        "bond_etfs": 35,
        "mutual_funds": 20,
        "cds": 15
      }},
      "instruments": {{
        "equity_etfs": [
          {{"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Core broad market exposure", "conviction": "High", "hold_period": "Core — Long Term Hold"}},
          {{"ticker": "SCHD", "name": "Schwab Dividend ETF", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Dividend income component", "conviction": "High", "hold_period": "Core — Long Term Hold"}}
        ],
        "growth_stocks": [
          {{"ticker": "JNJ", "name": "Johnson & Johnson", "allocation_pct": 5, "dollar_amount": 0, "reasoning": "Defensive quality dividend stock", "conviction": "Medium", "hold_period": "Strategic — 5 to 10 Years"}}
        ],
        "bond_etfs": [
          {{"ticker": "BND", "name": "Vanguard Total Bond Market ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "Core bond exposure for stability", "conviction": "High", "hold_period": "Income — Long Term Hold"}},
          {{"ticker": "TIP", "name": "iShares TIPS Bond ETF", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Inflation protection for purchasing power", "conviction": "High", "hold_period": "Income — Long Term Hold"}}
        ],
        "mutual_funds": [
          {{"ticker": "VWELX", "name": "Vanguard Wellington Fund", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "Proven balanced fund allocation", "conviction": "High", "hold_period": "Core — Long Term Hold"}}
        ],
        "cds": [
          {{"ticker": "CD-1Y", "name": "1-Year Certificate of Deposit", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "FDIC guaranteed return at current rates", "conviction": "High", "hold_period": "1 Year"}}
        ]
      }},
      "reasoning": "Write 2-3 specific paragraphs for Option B Conservative Growth for {client_name}.",
      "key_considerations": ["Consideration 1", "Consideration 2", "Consideration 3"],
      "flags": [],
      "suitability_note": "Write exactly 4 formal compliance paragraphs for Option B Conservative Growth. Reference VOO, SCHD, JNJ, BND, TIP, VWELX, CD-1Y specifically. Client is {client_name} age {age} {life_stage} ${amount:,} {risk} risk {horizon} years. Current 10Y Treasury {treasury_10y}% CD rate {cd_1y}%. Use formal SEC FINRA compliance language."
    }},
    {{
      "id": "C",
      "name": "Balanced Growth",
      "tagline": "Optimal risk-adjusted returns",
      "recommended": true,
      "allocation": {{
        "equity_etfs": 35,
        "growth_stocks": 15,
        "bond_etfs": 25,
        "mutual_funds": 15,
        "cds": 10
      }},
      "instruments": {{
        "equity_etfs": [
          {{"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "Core broad market ETF exposure", "conviction": "High", "hold_period": "Core — Long Term Hold"}},
          {{"ticker": "QQQ", "name": "Invesco Nasdaq 100 ETF", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Technology and growth sector tilt", "conviction": "Medium", "hold_period": "Core — Long Term Hold"}}
        ],
        "growth_stocks": [
          {{"ticker": "MSFT", "name": "Microsoft Corporation", "allocation_pct": 8, "dollar_amount": 0, "reasoning": "AI cloud leadership with consistent revenue growth", "conviction": "High", "hold_period": "Strategic — 5 to 10 Years"}},
          {{"ticker": "GOOGL", "name": "Alphabet Inc", "allocation_pct": 7, "dollar_amount": 0, "reasoning": "Diversified technology with AI integration", "conviction": "High", "hold_period": "Strategic — 5 to 10 Years"}}
        ],
        "bond_etfs": [
          {{"ticker": "BND", "name": "Vanguard Total Bond Market ETF", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Broad investment grade bond exposure", "conviction": "High", "hold_period": "Income — Long Term Hold"}},
          {{"ticker": "LQD", "name": "iShares Investment Grade Corp ETF", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Investment grade corporate bond yield premium", "conviction": "Medium", "hold_period": "Income — Long Term Hold"}}
        ],
        "mutual_funds": [
          {{"ticker": "FXAIX", "name": "Fidelity 500 Index Fund", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Ultra low cost S&P 500 index exposure", "conviction": "High", "hold_period": "Core — Long Term Hold"}}
        ],
        "cds": [
          {{"ticker": "CD-1Y", "name": "1-Year Certificate of Deposit", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "FDIC insured liquidity buffer at attractive rate", "conviction": "High", "hold_period": "1 Year"}}
        ]
      }},
      "reasoning": "Write 2-3 specific paragraphs for Option C Balanced Growth for {client_name}.",
      "key_considerations": ["Consideration 1", "Consideration 2", "Consideration 3"],
      "flags": [],
      "suitability_note": "Write exactly 4 formal compliance paragraphs for Option C Balanced Growth. Reference VOO, QQQ, MSFT, GOOGL, BND, LQD, FXAIX, CD-1Y specifically. Client is {client_name} age {age} {life_stage} ${amount:,} {risk} risk {horizon} years. Current 10Y Treasury {treasury_10y}% CD rate {cd_1y}%. Use formal SEC FINRA compliance language."
    }},
    {{
      "id": "D",
      "name": "Aggressive Growth",
      "tagline": "Maximum long-term growth potential",
      "recommended": false,
      "allocation": {{
        "equity_etfs": 40,
        "growth_stocks": 35,
        "bond_etfs": 10,
        "mutual_funds": 10,
        "cds": 5
      }},
      "instruments": {{
        "equity_etfs": [
          {{"ticker": "QQQ", "name": "Invesco Nasdaq 100 ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "High growth technology sector concentration", "conviction": "High", "hold_period": "Core — Long Term Hold"}},
          {{"ticker": "VUG", "name": "Vanguard Growth ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "Large cap growth factor exposure", "conviction": "High", "hold_period": "Core — Long Term Hold"}}
        ],
        "growth_stocks": [
          {{"ticker": "NVDA", "name": "NVIDIA Corporation", "allocation_pct": 12, "dollar_amount": 0, "reasoning": "AI semiconductor market leadership and revenue growth", "conviction": "High", "hold_period": "Strategic — 5 to 10 Years"}},
          {{"ticker": "MSFT", "name": "Microsoft Corporation", "allocation_pct": 12, "dollar_amount": 0, "reasoning": "Cloud and AI platform dominance", "conviction": "High", "hold_period": "Strategic — 10+ Years"}},
          {{"ticker": "GOOGL", "name": "Alphabet Inc", "allocation_pct": 11, "dollar_amount": 0, "reasoning": "Search advertising and AI revenue diversification", "conviction": "High", "hold_period": "Strategic — 5 to 10 Years"}}
        ],
        "bond_etfs": [
          {{"ticker": "HYG", "name": "iShares High Yield Corporate ETF", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Higher yield fixed income for aggressive risk profile", "conviction": "Medium", "hold_period": "Duration Play — 12 to 24 Months"}}
        ],
        "mutual_funds": [
          {{"ticker": "DODGX", "name": "Dodge & Cox Stock Fund", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Active value management with long term track record", "conviction": "Medium", "hold_period": "Core — Long Term Hold"}}
        ],
        "cds": [
          {{"ticker": "CD-3M", "name": "3-Month Certificate of Deposit", "allocation_pct": 5, "dollar_amount": 0, "reasoning": "Minimal liquidity reserve for aggressive portfolio", "conviction": "High", "hold_period": "3 Months"}}
        ]
      }},
      "reasoning": "Write 2-3 specific paragraphs for Option D Aggressive Growth for {client_name}. Note any suitability concerns.",
      "key_considerations": ["Consideration 1", "Consideration 2", "Consideration 3"],
      "flags": ["Review aggressive allocation suitability carefully for this specific client profile"],
      "suitability_note": "Write exactly 4 formal compliance paragraphs for Option D Aggressive Growth. Reference QQQ, VUG, NVDA, MSFT, GOOGL, HYG, DODGX, CD-3M specifically. Client is {client_name} age {age} {life_stage} ${amount:,} {risk} risk {horizon} years. Current 10Y Treasury {treasury_10y}% CD rate {cd_1y}%. Note any risk considerations for this aggressive allocation. Use formal SEC FINRA compliance language."
    }}
  ],
  "market_context": "Write 1-2 sentences on how current market conditions specifically the 10-Year Treasury at {treasury_10y}% and CD rates at {cd_1y}% influenced these recommendations.",
  "advisor_note": "The licensed financial advisor makes the final investment decision on all recommendations. These recommendations were generated by AdvisorNest as a decision support tool and must be reviewed against the client complete financial picture including existing assets liabilities tax situation and estate planning considerations before implementation."
}}

Calculate dollar_amount for each instrument as (allocation_pct / 100) * {amount}
Replace all placeholder text with real specific analysis for {client_name}.
Return ONLY valid JSON. No markdown. No text outside the JSON."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior compliance officer and portfolio analyst at a registered investment advisory firm. Always return valid JSON only. Never recommend instruments outside the approved universe. Write all suitability notes in formal SEC and FINRA compliance language — professional, specific, instrument-referenced, and defensible in a regulatory audit. Always write exactly 4 paragraphs per suitability note."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=5000,
            temperature=0.2
        )

        content = response.choices[0].message.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        if content.endswith("```"):
            content = content[:-3]

        result = json.loads(content.strip())
        return {"success": True, "fallback": False, "data": result}

    except json.JSONDecodeError as e:
        print(f"JSON parse error: {str(e)}")
        print(f"Raw content: {content[:300]}")

        try:
            partial = content.strip()
            for closing in [']}]}', ']}', '}]}']:
                try:
                    fixed = partial + closing
                    result = json.loads(fixed)
                    if result.get("options"):
                        print(f"Salvaged {len(result['options'])} options")
                        return {"success": True, "fallback": False, "data": result}
                except:
                    continue
        except:
            pass

        return {"success": False, "error": "Could not parse AI response"}

    except Exception as e:
        print(f"OpenAI error: {str(e)}")
        return {"success": False, "error": str(e)}


def get_fallback_recommendation(risk, age, horizon, amount):
    from logic import calculate_allocation
    allocation = calculate_allocation(risk, horizon, age)

    return {
        "success": True,
        "fallback": True,
        "data": {
            "options": [
                {
                    "id": "A",
                    "name": "Standard Recommendation",
                    "tagline": "Based on your client profile",
                    "recommended": True,
                    "allocation": {
                        "equity_etfs":   allocation.get("stocks_lt", 30),
                        "growth_stocks": allocation.get("stocks_st", 10),
                        "bond_etfs":     allocation.get("bonds", 35),
                        "mutual_funds":  allocation.get("mutual_funds", 15),
                        "cds":           allocation.get("cds", 10)
                    },
                    "instruments": {
                        "equity_etfs":   [],
                        "growth_stocks": [],
                        "bond_etfs":     [],
                        "mutual_funds":  [],
                        "cds":           []
                    },
                    "reasoning": "AI temporarily unavailable. Standard rule-based allocation applied.",
                    "key_considerations": [
                        "Review allocation with client",
                        "Verify risk tolerance is current",
                        "Consider current market conditions"
                    ],
                    "flags": [],
                    "suitability_note": "AI temporarily unavailable. Please regenerate recommendation for a full suitability assessment."
                }
            ],
            "market_context": "AI analysis temporarily unavailable.",
            "advisor_note": "The advisor makes the final decision on all recommendations."
        }
    }
def generate_suitability_note_ai(
    client_name, age, life_stage, risk,
    horizon, amount, option_name, option_id,
    instruments, market_data
):
    """
    Generates a specific compliance-grade suitability note
    for the selected portfolio option.
    Called when advisor selects an option card.
    """
    rates = market_data.get("rates", {})
    treasury_10y = rates.get("10_year_treasury", "N/A")
    cd_1y = rates.get("cd_1_year", "N/A")

    # Build instrument list for the prompt
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
Explain specifically why each equity instrument selected (ETFs and growth stocks) is appropriate for this client. Reference each ticker by name. Explain how each instrument aligns with the client age, risk tolerance and investment horizon. If no equity instruments, explain why a conservative fixed income focus is appropriate.

PARAGRAPH 3 — FIXED INCOME AND GUARANTEED INSTRUMENT SUITABILITY:
Explain why the bond ETFs, mutual funds and CDs selected are appropriate for this client. Reference the current 10-Year Treasury yield of {treasury_10y}% and CD rate of {cd_1y}% and explain how these market conditions make the fixed income allocation particularly relevant. Reference each ticker by name.

PARAGRAPH 4 — SUITABILITY DETERMINATION:
State that based on the above analysis this {option_name} recommendation is suitable for {client_name}. Reference FINRA Rule 2111 and SEC Regulation Best Interest. State that the licensed advisor has reviewed and approved this recommendation. State this was prepared using AdvisorNest as a decision support tool and the final investment decision rests with the licensed advisor.

Write in formal compliance language. Be specific. Reference actual tickers. Do not use placeholder text.
Return ONLY the 4 paragraphs of text. No JSON. No headers. Just the paragraphs separated by blank lines."""

    try:
        response = client.chat.completions.create(
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