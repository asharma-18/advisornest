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

    prompt = f"""You are a senior portfolio analyst at a wealth management firm.
A licensed financial advisor is using this tool to get portfolio recommendations
for their client. You are providing DECISION SUPPORT only — the advisor makes
the final decision and is solely responsible for all recommendations.

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

APPROVED INSTRUMENT UNIVERSE:
Only recommend instruments from this list.

EQUITY ETFs (equity_etfs category):
For each ETF, set hold_period to "Core — Long Term Hold" or "Tactical — 12 to 18 Months"
- Broad Market: VOO, VTI, ITOT, SCHB, IVV
- Dividend: SCHD, VYM, DGRO, NOBL, DVY
- Growth: QQQ, VUG, SCHG, IWF
- International: VXUS, VEA, VWO, EFA
- Sector: XLK, XLF, XLV, XLE, XLU, XLP, XLI
- Balanced: AOM, AOA, AOK

GROWTH STOCKS (growth_stocks category):
Individual company stocks only — no ETFs here.
For each growth stock pick, set hold_period to one of:
- "Strategic — 5 to 10 Years" for core long term holdings
- "Strategic — 10+ Years" for permanent core holdings
- "Tactical — 6 to 12 Months" for short term catalyst plays
- "Tactical — 12 to 18 Months" for medium term sector plays
Never use just "Long Term" or "Short Term" — always specify duration.

- Technology: MSFT, AAPL, GOOGL, AMZN, NVDA, META
- Healthcare: JNJ, UNH, PFE, ABBV
- Financial: JPM, BAC, WFC, GS
- Consumer: HD, MCD, COST
- Industrial: CAT, HON, UNP
- Defensive: BRK-B, PG, KO

For conservative profiles: use defensive stocks only
For aggressive profiles: use technology growth stocks
For tactical plays: JPM and XLE when rates are high

BOND ETFs (bond_etfs category):
For each bond ETF, set hold_period to "Income — Long Term Hold" or "Duration Play — 12 to 24 Months"
- Total Bond: BND, AGG, BNDX
- Treasury: TLT (long), IEF (medium), SHY (short)
- Corporate: LQD (investment grade), HYG (high yield - aggressive only)
- Inflation: TIP
- Municipal: MUB (tax advantaged)

MUTUAL FUNDS (mutual_funds category):
- VFIAX, VBTLX, VWELX, FXAIX, FZROX, PIMIX, DODGX

CDs (cds category):
- CD-3M, CD-6M, CD-1Y, CD-2Y, TBILL

RULES:
- Only use instruments from the approved universe above
- For clients over 60 with high risk: flag it
- For clients under 35 with very low risk: flag it
- For amounts under $50K: prefer ETFs over individual stocks
- For amounts over $200K with high risk: individual stocks appropriate
- Each option allocation must sum to exactly 100
- equity_etfs + growth_stocks + bond_etfs + mutual_funds + cds = 100

Generate exactly 4 portfolio options A, B, C, D from most conservative
to most aggressive. Mark one as recommended=true.

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
            "hold_period": "Long Term"
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
            "hold_period": "Long Term"
          }},
          {{
            "ticker": "MUB",
            "name": "iShares National Muni Bond ETF",
            "allocation_pct": 20,
            "dollar_amount": 0,
            "reasoning": "Tax-free income",
            "conviction": "High",
            "hold_period": "Long Term"
          }}
        ],
        "mutual_funds": [
          {{
            "ticker": "VWELX",
            "name": "Vanguard Wellington Fund",
            "allocation_pct": 25,
            "dollar_amount": 0,
            "reasoning": "Proven 90-year balanced fund",
            "conviction": "High",
            "hold_period": "Long Term"
          }}
        ],
        "cds": [
          {{
            "ticker": "CD-1Y",
            "name": "1-Year Certificate of Deposit",
            "allocation_pct": 20,
            "dollar_amount": 0,
            "reasoning": "FDIC insured guaranteed return",
            "conviction": "High",
            "hold_period": "1 Year"
          }}
        ]
      }},
      "reasoning": "Explain why this allocation suits this specific client.",
      "key_considerations": [
        "Point 1 for advisor",
        "Point 2",
        "Point 3"
      ],
      "flags": []
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
        "equity_etfs": [{{ "ticker": "VOO", "name": "Vanguard S&P 500 ETF", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Core broad market exposure", "conviction": "High", "hold_period": "Long Term" }}, {{ "ticker": "SCHD", "name": "Schwab Dividend ETF", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Dividend income component", "conviction": "High", "hold_period": "Long Term" }}],
        "growth_stocks": [{{ "ticker": "JNJ", "name": "Johnson & Johnson", "allocation_pct": 5, "dollar_amount": 0, "reasoning": "Defensive quality stock", "conviction": "Medium", "hold_period": "Long Term" }}],
        "bond_etfs": [{{ "ticker": "BND", "name": "Vanguard Total Bond ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "Core bond exposure", "conviction": "High", "hold_period": "Long Term" }}, {{ "ticker": "TIP", "name": "iShares TIPS Bond ETF", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Inflation protection", "conviction": "High", "hold_period": "Long Term" }}],
        "mutual_funds": [{{ "ticker": "VWELX", "name": "Vanguard Wellington Fund", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "Balanced exposure", "conviction": "High", "hold_period": "Long Term" }}],
        "cds": [{{ "ticker": "CD-1Y", "name": "1-Year CD", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Guaranteed return", "conviction": "High", "hold_period": "1 Year" }}]
      }},
      "reasoning": "Explain why this allocation suits this specific client.",
      "key_considerations": ["Point 1", "Point 2", "Point 3"],
      "flags": []
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
        "equity_etfs": [{{ "ticker": "VOO", "name": "Vanguard S&P 500 ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "Core market exposure", "conviction": "High", "hold_period": "Long Term" }}, {{ "ticker": "QQQ", "name": "Invesco Nasdaq ETF", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Growth tilt", "conviction": "Medium", "hold_period": "Long Term" }}],
        "growth_stocks": [{{ "ticker": "MSFT", "name": "Microsoft Corporation", "allocation_pct": 8, "dollar_amount": 0, "reasoning": "AI and cloud leader", "conviction": "High", "hold_period": "Long Term" }}, {{ "ticker": "GOOGL", "name": "Alphabet Inc", "allocation_pct": 7, "dollar_amount": 0, "reasoning": "Diversified tech exposure", "conviction": "High", "hold_period": "Long Term" }}],
        "bond_etfs": [{{ "ticker": "BND", "name": "Vanguard Total Bond ETF", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Core fixed income", "conviction": "High", "hold_period": "Long Term" }}, {{ "ticker": "LQD", "name": "iShares Investment Grade ETF", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Corporate bond yield", "conviction": "Medium", "hold_period": "Long Term" }}],
        "mutual_funds": [{{ "ticker": "FXAIX", "name": "Fidelity 500 Index Fund", "allocation_pct": 15, "dollar_amount": 0, "reasoning": "Low cost index exposure", "conviction": "High", "hold_period": "Long Term" }}],
        "cds": [{{ "ticker": "CD-1Y", "name": "1-Year CD", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Guaranteed liquidity buffer", "conviction": "High", "hold_period": "1 Year" }}]
      }},
      "reasoning": "Explain why this allocation suits this specific client.",
      "key_considerations": ["Point 1", "Point 2", "Point 3"],
      "flags": []
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
        "equity_etfs": [{{ "ticker": "QQQ", "name": "Invesco Nasdaq ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "High growth tech exposure", "conviction": "High", "hold_period": "Long Term" }}, {{ "ticker": "VUG", "name": "Vanguard Growth ETF", "allocation_pct": 20, "dollar_amount": 0, "reasoning": "Large cap growth", "conviction": "High", "hold_period": "Long Term" }}],
        "growth_stocks": [{{ "ticker": "NVDA", "name": "NVIDIA Corporation", "allocation_pct": 12, "dollar_amount": 0, "reasoning": "AI chip market leader", "conviction": "High", "hold_period": "Long Term" }}, {{ "ticker": "MSFT", "name": "Microsoft Corporation", "allocation_pct": 12, "dollar_amount": 0, "reasoning": "Cloud and AI dominance", "conviction": "High", "hold_period": "Long Term" }}, {{ "ticker": "GOOGL", "name": "Alphabet Inc", "allocation_pct": 11, "dollar_amount": 0, "reasoning": "Search and AI revenue", "conviction": "High", "hold_period": "Long Term" }}],
        "bond_etfs": [{{ "ticker": "HYG", "name": "iShares High Yield ETF", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Higher yield for aggressive profile", "conviction": "Medium", "hold_period": "Medium Term" }}],
        "mutual_funds": [{{ "ticker": "DODGX", "name": "Dodge & Cox Stock Fund", "allocation_pct": 10, "dollar_amount": 0, "reasoning": "Active value management", "conviction": "Medium", "hold_period": "Long Term" }}],
        "cds": [{{ "ticker": "CD-3M", "name": "3-Month CD", "allocation_pct": 5, "dollar_amount": 0, "reasoning": "Minimal liquidity buffer", "conviction": "High", "hold_period": "3 Months" }}]
      }},
      "reasoning": "Explain why this allocation suits this specific client.",
      "key_considerations": ["Point 1", "Point 2", "Point 3"],
      "flags": ["Review aggressive allocation suitability for this client profile"]
    }}
  ],
  "market_context": "Brief note on how current market conditions influenced these recommendations.",
  "advisor_note": "The licensed advisor makes the final decision on all recommendations and must review against the client complete financial picture."
}}

Calculate dollar_amount for each instrument as (allocation_pct / 100) * {amount}
Fill in reasoning, key_considerations with real analysis for this specific client.
Return ONLY valid JSON. No markdown."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior portfolio analyst providing decision support to licensed financial advisors. Always return valid JSON only. Never recommend instruments outside the approved universe."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=4000,
            temperature=0.3
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
        print(f"Raw content was: {content}")

        # Try to salvage partial response
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
        import traceback
        traceback.print_exc()
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
                    "flags": []
                }
            ],
            "market_context": "AI analysis temporarily unavailable.",
            "advisor_note": "The advisor makes the final decision on all recommendations."
        }
    }