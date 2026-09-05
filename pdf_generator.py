from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
from datetime import datetime
import json

NAVY     = HexColor("#2c4a6e")
GOLD     = HexColor("#d4a853")
LIGHT_BG = HexColor("#faf9f7")
BORDER   = HexColor("#e8e4dc")
TEXT     = HexColor("#1a1a2e")
MUTED    = HexColor("#8892a4")
WHITE    = white


def safe(value, default=""):
    """Return value if not None, otherwise return default."""
    if value is None:
        return default
    return str(value)


def generate_pdf_report(client, advisor):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=0.8*inch, leftMargin=0.8*inch,
        topMargin=0.5*inch, bottomMargin=0.8*inch
    )
    W = 6.9 * inch
    content = []

    s_body = ParagraphStyle("Body", fontSize=9, textColor=TEXT,
        fontName="Helvetica", leading=14, spaceAfter=2)
    s_bold = ParagraphStyle("Bold", fontSize=9, textColor=TEXT,
        fontName="Helvetica-Bold", leading=14)
    s_label = ParagraphStyle("Label", fontSize=8, textColor=MUTED,
        fontName="Helvetica", leading=12)
    s_section = ParagraphStyle("Section", fontSize=9, textColor=WHITE,
        fontName="Helvetica-Bold")
    s_disclaimer = ParagraphStyle("Disclaimer", fontSize=7, textColor=MUTED,
        fontName="Helvetica", leading=10, alignment=TA_CENTER)

    # ── 1. Header ─────────────────────────────────────────
    header = Table(
        [
            [
                Paragraph("AdvisorNest", ParagraphStyle(
                    "Logo", fontSize=18, textColor=WHITE,
                    fontName="Times-Bold", leading=24)),
                Paragraph(
                    datetime.now().strftime("%B %d, %Y"),
                    ParagraphStyle("Date", fontSize=8,
                        textColor=HexColor("#a0b4c8"),
                        fontName="Helvetica",
                        alignment=TA_RIGHT, leading=12))
            ],
            [
                Paragraph("Where great portfolios are built",
                    ParagraphStyle("Tag", fontSize=8,
                        textColor=HexColor("#a0b4c8"),
                        fontName="Times-Italic", leading=12)),
                Paragraph("Portfolio Recommendation Report",
                    ParagraphStyle("Rep", fontSize=8,
                        textColor=HexColor("#a0b4c8"),
                        fontName="Helvetica",
                        alignment=TA_RIGHT, leading=12))
            ]
        ],
        colWidths=[3.4*inch, 3.5*inch]
    )
    header.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), NAVY),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
        ("TOPPADDING",    (0,0), (-1,0),  8),
        ("BOTTOMPADDING", (0,0), (-1,0),  2),
        ("TOPPADDING",    (0,1), (-1,1),  2),
        ("BOTTOMPADDING", (0,1), (-1,1),  6),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    content.append(header)
    content.append(Spacer(1, 8))

    # ── 2. Title ───────────────────────────────────────────
    content.append(Spacer(1, 3))
    content.append(Paragraph(
        f"Prepared for <b>{safe(client.get('client_name'), 'Client')}</b>",
        ParagraphStyle("Sub1", fontSize=14, textColor=NAVY,
            fontName="Times-Bold", alignment=TA_CENTER, spaceAfter=4)))
    content.append(Paragraph(
        f"{safe(advisor.get('full_name'), 'Licensed Advisor')} "
        f"&nbsp;&middot;&nbsp; "
        f"{safe(advisor.get('firm_name'), 'Independent')}",
        ParagraphStyle("Sub2", fontSize=10, textColor=MUTED,
            fontName="Helvetica", alignment=TA_CENTER, spaceAfter=14)))
    content.append(HRFlowable(width="100%", thickness=1.5,
        color=GOLD, spaceAfter=8))

    # ── Helper ─────────────────────────────────────────────
    def section_bar(title):
        t = Table([[Paragraph(title, s_section)]], colWidths=[W])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), NAVY),
            ("TOPPADDING",    (0,0), (-1,-1), 7),
            ("BOTTOMPADDING", (0,0), (-1,-1), 7),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ("RIGHTPADDING",  (0,0), (-1,-1), 10),
        ]))
        return t

    # ── 3. Client Profile ──────────────────────────────────
    content.append(section_bar("CLIENT PROFILE"))
    content.append(Spacer(1, 6))

    profile = [
        [Paragraph("Client Name", s_label),
         Paragraph(safe(client.get("client_name"), "N/A"), s_bold),
         Paragraph("Life Stage", s_label),
         Paragraph(safe(client.get("life_stage"), "N/A"), s_body)],
        [Paragraph("Age", s_label),
         Paragraph(safe(client.get("age"), "N/A"), s_body),
         Paragraph("Risk Tolerance", s_label),
         Paragraph(safe(client.get("risk"), "N/A"), s_bold)],
        [Paragraph("Investment Amount", s_label),
         Paragraph(f"${client['amount']:,}" if client.get("amount") else "N/A", s_bold),
         Paragraph("Time Horizon", s_label),
         Paragraph(f"{client.get('horizon', 'N/A')} years", s_body)],
        [Paragraph("Portfolio Score", s_label),
         Paragraph(f"{client.get('score', 'N/A')}/100", s_bold),
         Paragraph("Report Date", s_label),
         Paragraph(datetime.now().strftime("%B %d, %Y"), s_body)],
    ]
    pt = Table(profile,
        colWidths=[1.4*inch, 2.1*inch, 1.4*inch, 2.0*inch])
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), LIGHT_BG),
        ("BACKGROUND", (2,0), (2,-1), LIGHT_BG),
        ("GRID",       (0,0), (-1,-1), 0.5, BORDER),
        ("PADDING",    (0,0), (-1,-1), 8),
        ("VALIGN",     (0,0), (-1,-1), "TOP"),
    ]))
    content.append(pt)
    content.append(Spacer(1, 14))

    # ── 4. Portfolio Allocation ────────────────────────────
    content.append(section_bar("PORTFOLIO ALLOCATION"))
    content.append(Spacer(1, 6))

    allocation = client.get("allocation", {})
    if isinstance(allocation, str):
        try:
            allocation = json.loads(allocation)
        except Exception:
            allocation = {}

    cat_labels = {
        "equity_etfs":   "Equity ETFs",
        "growth_stocks": "Growth Stocks",
        "bond_etfs":     "Bond ETFs",
        "mutual_funds":  "Mutual Funds",
        "cds":           "Certificates of Deposit",
        "stocks_lt":     "Long-Term Stocks",
        "stocks_st":     "Short-Term Stocks",
        "bonds":         "Bonds",
    }

    notes_map = {
        "equity_etfs":   "Diversified ETF exposure to equity markets",
        "growth_stocks": "Individual company stocks for capital appreciation",
        "bond_etfs":     "Fixed income ETFs for stability and income",
        "mutual_funds":  "Professionally managed diversified funds",
        "cds":           "FDIC-insured certificates of deposit",
        "stocks_lt":     "Growth equity for long-term appreciation",
        "stocks_st":     "Tactical equity for near-term opportunities",
        "bonds":         "Fixed income for stability and income",
    }

    alloc_data = [[
        Paragraph("Asset Class", ParagraphStyle("AH1", fontSize=9,
            textColor=WHITE, fontName="Helvetica-Bold")),
        Paragraph("Allocation", ParagraphStyle("AH2", fontSize=9,
            textColor=WHITE, fontName="Helvetica-Bold",
            alignment=TA_CENTER)),
        Paragraph("Amount", ParagraphStyle("AH3", fontSize=9,
            textColor=WHITE, fontName="Helvetica-Bold",
            alignment=TA_RIGHT)),
        Paragraph("Description", ParagraphStyle("AH4", fontSize=9,
            textColor=WHITE, fontName="Helvetica-Bold")),
    ]]

    for key, pct in allocation.items():
        if pct and pct > 0:
            dollar = round((pct / 100) * client["amount"])
            label = cat_labels.get(key, key.replace("_", " ").title())
            note  = notes_map.get(key, "")
            alloc_data.append([
                Paragraph(label, s_bold),
                Paragraph(f"{pct}%", ParagraphStyle("AP", fontSize=9,
                    textColor=NAVY, fontName="Helvetica-Bold",
                    alignment=TA_CENTER)),
                Paragraph(f"${dollar:,}", ParagraphStyle("AR", fontSize=9,
                    textColor=TEXT, fontName="Helvetica-Bold",
                    alignment=TA_RIGHT)),
                Paragraph(note, s_label),
            ])

    alloc_data.append([
        Paragraph("TOTAL", ParagraphStyle("AT1", fontSize=9,
            textColor=NAVY, fontName="Helvetica-Bold")),
        Paragraph("100%", ParagraphStyle("AT2", fontSize=9,
            textColor=NAVY, fontName="Helvetica-Bold",
            alignment=TA_CENTER)),
        Paragraph(f"${client['amount']:,}", ParagraphStyle("AT3",
            fontSize=9, textColor=NAVY, fontName="Helvetica-Bold",
            alignment=TA_RIGHT)),
        Paragraph("", s_body),
    ])

    at = Table(alloc_data,
        colWidths=[2.0*inch, 0.9*inch, 1.2*inch, 2.8*inch])
    at.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),  (-1,0),  NAVY),
        ("BACKGROUND",    (0,-1), (-1,-1), HexColor("#eef2f7")),
        ("ROWBACKGROUND", (0,1),  (-1,-2), [LIGHT_BG, WHITE]),
        ("GRID",          (0,0),  (-1,-1), 0.5, BORDER),
        ("PADDING",       (0,0),  (-1,-1), 8),
        ("LINEABOVE",     (0,-1), (-1,-1), 1.5, NAVY),
        ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
    ]))
    content.append(at)
    content.append(Spacer(1, 14))

    # ── 5. Recommended Instruments ─────────────────────────
    rec_data = client.get("recommendation_data", {}) or {}
    if isinstance(rec_data, str):
        try:
            rec_data = json.loads(rec_data)
        except Exception:
            rec_data = {}

    instruments = rec_data.get("instruments", {})

    if instruments:
        content.append(section_bar("RECOMMENDED INSTRUMENTS"))
        content.append(Spacer(1, 6))

        instr_cat_colors = {
            "equity_etfs":   HexColor("#2c4a6e"),
            "growth_stocks": HexColor("#b7791f"),
            "bond_etfs":     HexColor("#2d7d4f"),
            "mutual_funds":  HexColor("#553c9a"),
            "cds":           HexColor("#9b2c2c"),
        }

        instr_cat_labels = {
            "equity_etfs":   "EQUITY ETFs",
            "growth_stocks": "GROWTH STOCKS",
            "bond_etfs":     "BOND ETFs",
            "mutual_funds":  "MUTUAL FUNDS",
            "cds":           "CERTIFICATES OF DEPOSIT",
        }

        tab_order = [
            "equity_etfs", "growth_stocks",
            "bond_etfs", "mutual_funds", "cds"
        ]

        for cat_key in tab_order:
            cat_instr = instruments.get(cat_key, [])
            if not cat_instr:
                continue

            cat_color = instr_cat_colors.get(cat_key, NAVY)
            cat_name  = instr_cat_labels.get(cat_key, cat_key.upper())

            sub_hdr = Table(
                [[Paragraph(cat_name, ParagraphStyle(
                    "CatHdr", fontSize=8, textColor=WHITE,
                    fontName="Helvetica-Bold", leading=11))]],
                colWidths=[W]
            )
            sub_hdr.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), cat_color),
                ("TOPPADDING",    (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                ("LEFTPADDING",   (0,0), (-1,-1), 10),
                ("RIGHTPADDING",  (0,0), (-1,-1), 10),
            ]))
            content.append(sub_hdr)

            instr_rows = [[
                Paragraph("Ticker", ParagraphStyle("IH1", fontSize=8,
                    textColor=WHITE, fontName="Helvetica-Bold")),
                Paragraph("Instrument Name", ParagraphStyle("IH2", fontSize=8,
                    textColor=WHITE, fontName="Helvetica-Bold")),
                Paragraph("Alloc %", ParagraphStyle("IH3", fontSize=8,
                    textColor=WHITE, fontName="Helvetica-Bold",
                    alignment=TA_CENTER)),
                Paragraph("Amount", ParagraphStyle("IH4", fontSize=8,
                    textColor=WHITE, fontName="Helvetica-Bold",
                    alignment=TA_RIGHT)),
                Paragraph("Hold Period", ParagraphStyle("IH5", fontSize=8,
                    textColor=WHITE, fontName="Helvetica-Bold")),
            ]]

            for inst in cat_instr:
                pct    = inst.get("allocation_pct", 0) or 0
                dollar = inst.get("dollar_amount", 0) or (pct/100)*client["amount"]
                instr_rows.append([
                    Paragraph(safe(inst.get("ticker"), ""), s_bold),
                    Paragraph(safe(inst.get("name"), ""), s_body),
                    Paragraph(f"{pct}%", ParagraphStyle("IP", fontSize=9,
                        textColor=NAVY, fontName="Helvetica-Bold",
                        alignment=TA_CENTER)),
                    Paragraph(f"${dollar:,.0f}", ParagraphStyle("IA", fontSize=9,
                        textColor=TEXT, fontName="Helvetica-Bold",
                        alignment=TA_RIGHT)),
                    Paragraph(safe(inst.get("hold_period"), ""), s_label),
                ])

            it = Table(instr_rows,
                colWidths=[0.7*inch, 2.2*inch, 0.65*inch, 0.95*inch, 2.4*inch])
            it.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),  (-1,0),  cat_color),
                ("ROWBACKGROUND", (0,1),  (-1,-1), [LIGHT_BG, WHITE]),
                ("GRID",          (0,0),  (-1,-1), 0.5, BORDER),
                ("PADDING",       (0,0),  (-1,-1), 6),
                ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
                ("FONTNAME",      (0,1),  (0,-1),  "Helvetica-Bold"),
                ("TEXTCOLOR",     (0,1),  (0,-1),  NAVY),
            ]))
            content.append(it)

            for inst in cat_instr:
                if inst.get("reasoning"):
                    content.append(Paragraph(
                        f"<b>{safe(inst.get('ticker'))}</b>: {safe(inst.get('reasoning'))}",
                        ParagraphStyle("Reason", fontSize=7.5, textColor=MUTED,
                            fontName="Helvetica", leading=11,
                            spaceAfter=2, leftIndent=6)
                    ))

            content.append(Spacer(1, 8))

        content.append(Spacer(1, 6))

    # ── 6. Suitability Note ────────────────────────────────
    content.append(section_bar("SUITABILITY ASSESSMENT"))
    content.append(Spacer(1, 6))

    suitability = safe(client.get("suitability_note"), "")
    if suitability:
        for line in suitability.split("\n"):
            line = line.strip()
            if not line:
                content.append(Spacer(1, 3))
            elif line.isupper() and len(line) < 60:
                content.append(Paragraph(line, ParagraphStyle(
                    "SH", fontSize=9, textColor=NAVY,
                    fontName="Helvetica-Bold",
                    spaceBefore=6, spaceAfter=2)))
            else:
                content.append(Paragraph(line, s_body))

    content.append(Spacer(1, 14))

    # ── 7. Advisor Signature ───────────────────────────────
    sig = [
        [Paragraph("Advisor Name:", s_label),
         Paragraph(safe(advisor.get("full_name"), ""), s_bold),
         Paragraph("Firm:", s_label),
         Paragraph(safe(advisor.get("firm_name"), "Independent"), s_body)],
        [Paragraph("CRD #:", s_label),
         Paragraph(safe(advisor.get("license_number"), "_______________________"), s_body),
         Paragraph("Date:", s_label),
         Paragraph("_______________________", s_body)],
        [Paragraph("Signature:", s_label),
         Paragraph("_______________________", s_body),
         Paragraph("", s_label),
         Paragraph("", s_body)],
    ]
    st = Table(sig,
        colWidths=[1.2*inch, 2.3*inch, 1.0*inch, 2.4*inch])
    st.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), LIGHT_BG),
        ("BACKGROUND", (2,0), (2,-1), LIGHT_BG),
        ("GRID",       (0,0), (-1,-1), 0.5, BORDER),
        ("PADDING",    (0,0), (-1,-1), 8),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ]))

    content.append(KeepTogether([
        section_bar("ADVISOR CONFIRMATION"),
        Spacer(1, 6),
        st,
        Spacer(1, 18),
    ]))

    # ── 8. Footer ──────────────────────────────────────────
    content.append(HRFlowable(width="100%", thickness=1,
        color=GOLD, spaceAfter=6))
    content.append(Paragraph(
        "IMPORTANT DISCLOSURE: This report was prepared using AdvisorNest "
        "decision support software for licensed financial advisors only. "
        "All recommendations require advisor review and client suitability "
        "assessment before implementation. This document does not constitute "
        "financial advice. AdvisorNest 2026",
        s_disclaimer))

    doc.build(content)
    buffer.seek(0)
    return buffer