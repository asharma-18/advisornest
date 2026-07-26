from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from io import BytesIO
from datetime import datetime

NAVY     = HexColor("#2c4a6e")
GOLD     = HexColor("#d4a853")
LIGHT_BG = HexColor("#faf9f7")
BORDER   = HexColor("#e8e4dc")
TEXT     = HexColor("#1a1a2e")
MUTED    = HexColor("#8892a4")
WHITE    = white


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
        ("LEFTPADDING",   (0,0), (-1,-1), 16),
        ("RIGHTPADDING",  (0,0), (-1,-1), 16),
        ("TOPPADDING",    (0,0), (-1,0),  14),
        ("BOTTOMPADDING", (0,0), (-1,0),  2),
        ("TOPPADDING",    (0,1), (-1,1),  2),
        ("BOTTOMPADDING", (0,1), (-1,1),  12),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    content.append(header)
    content.append(Spacer(1, 14))

    # ── 2. Title ──────────────────────────────────────────
    content.append(Spacer(1, 6))
    content.append(Paragraph(
        f"Prepared for <b>{client['client_name']}</b>",
        ParagraphStyle("Sub1", fontSize=14, textColor=NAVY,
            fontName="Times-Bold", alignment=TA_CENTER, spaceAfter=4)))
    content.append(Paragraph(
        f"{advisor.get('full_name', 'Licensed Advisor')} "
        f"&nbsp;·&nbsp; "
        f"{advisor.get('firm_name', 'Independent')}",
        ParagraphStyle("Sub2", fontSize=10, textColor=MUTED,
            fontName="Helvetica", alignment=TA_CENTER, spaceAfter=14)))
    content.append(HRFlowable(width="100%", thickness=1.5,
        color=GOLD, spaceAfter=14))

    # ── Helper ────────────────────────────────────────────
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

    # ── 3. Client Profile ─────────────────────────────────
    content.append(section_bar("CLIENT PROFILE"))
    content.append(Spacer(1, 6))

    profile = [
        [Paragraph("Client Name", s_label),
         Paragraph(client["client_name"], s_bold),
         Paragraph("Life Stage", s_label),
         Paragraph(client.get("life_stage", "N/A"), s_body)],
        [Paragraph("Age", s_label),
         Paragraph(str(client["age"]), s_body),
         Paragraph("Risk Tolerance", s_label),
         Paragraph(client["risk"], s_bold)],
        [Paragraph("Investment Amount", s_label),
         Paragraph(f"${client['amount']:,}", s_bold),
         Paragraph("Time Horizon", s_label),
         Paragraph(f"{client['horizon']} years", s_body)],
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

    # ── 4. Portfolio Allocation ───────────────────────────
    content.append(section_bar("PORTFOLIO ALLOCATION"))
    content.append(Spacer(1, 6))

    allocation = client.get("allocation", {})
    notes_map = {
        "Stocks (Long Term)":  "Growth equity for long-term appreciation",
        "Stocks (Short Term)": "Tactical equity for near-term opportunities",
        "Bonds":               "Fixed income for stability and income",
        "Mutual Funds":        "Diversified professionally managed funds",
        "CDs":                 "FDIC-insured certificates of deposit",
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

    for instrument, pct in allocation.items():
        dollar = round((pct / 100) * client["amount"])
        alloc_data.append([
            Paragraph(instrument, s_bold),
            Paragraph(f"{pct}%", ParagraphStyle("AP", fontSize=9,
                textColor=NAVY, fontName="Helvetica-Bold",
                alignment=TA_CENTER)),
            Paragraph(f"${dollar:,}", ParagraphStyle("AR", fontSize=9,
                textColor=TEXT, fontName="Helvetica-Bold",
                alignment=TA_RIGHT)),
            Paragraph(notes_map.get(instrument, ""), s_label),
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

    # ── 5. Suitability Note ───────────────────────────────
    content.append(section_bar("SUITABILITY ASSESSMENT"))
    content.append(Spacer(1, 6))

    suitability = client.get("suitability_note", "")
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

    # ── 6. Advisor Signature ──────────────────────────────
    content.append(section_bar("ADVISOR CONFIRMATION"))
    content.append(Spacer(1, 6))

    sig = [
        [Paragraph("Advisor Name:", s_label),
         Paragraph(advisor.get("full_name", ""), s_bold),
         Paragraph("Firm:", s_label),
         Paragraph(advisor.get("firm_name", "Independent"), s_body)],
        [Paragraph("Date:", s_label),
         Paragraph("_______________________", s_body),
         Paragraph("License #:", s_label),
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
    content.append(st)
    content.append(Spacer(1, 18))

    # ── 7. Footer ─────────────────────────────────────────
    content.append(HRFlowable(width="100%", thickness=1,
        color=GOLD, spaceAfter=6))
    content.append(Paragraph(
        "IMPORTANT DISCLOSURE: This report was prepared using AdvisorNest "
        "decision support software for licensed financial advisors only. "
        "All recommendations require advisor review and client suitability "
        "assessment before implementation. This document does not constitute "
        "financial advice. AdvisorNest 2025",
        s_disclaimer))

    doc.build(content)
    buffer.seek(0)
    return buffer