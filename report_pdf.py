"""
report_pdf.py - turns a calc_engine Report into a downloadable PDF.

The PDF repeats what the app shows on screen: recommendation, options
compared, price sensitivity, and the assumptions behind the numbers. All text
comes from calc_engine, so the app and the PDF can never disagree.
"""

import datetime
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from calc_engine import (
    ASSUMPTIONS, CONFIG_ORDER, Report, fmt_years, summary_text, system_description,
)

NAVY = colors.HexColor("#0B1F3A")
AMBER = colors.HexColor("#F4A300")
PALE_AMBER = colors.HexColor("#FFF3D6")
GRID = colors.HexColor("#D8DCE3")
MUTED = colors.HexColor("#5B6472")
TEXT = colors.HexColor("#16202E")

PAGE_W, _ = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

S_TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY)
S_SUB = ParagraphStyle("sub", fontName="Helvetica", fontSize=10, leading=14, textColor=MUTED)
S_H = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=NAVY,
                     spaceBefore=14, spaceAfter=6)
S_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=14, textColor=TEXT)
S_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, textColor=TEXT)
S_CELL_B = ParagraphStyle("cellb", parent=S_CELL, fontName="Helvetica-Bold")
S_HEAD = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white)
S_BULLET = ParagraphStyle("bullet", parent=S_BODY, fontSize=8.5, leading=12, leftIndent=10, bulletIndent=0,
                          spaceAfter=2)
S_NOTE = ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=8, leading=11, textColor=MUTED)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _m(x: float) -> str:
    """PKR in millions, two decimals."""
    return f"{x / 1_000_000:,.2f}"


def _roi(x) -> str:
    return "n/a" if x is None else f"{x:,.0f}%"


def _table(rows, col_widths, highlight_row=None, header=True):
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if highlight_row is not None:
        style.append(("BACKGROUND", (0, highlight_row), (-1, highlight_row), PALE_AMBER))
    t.setStyle(TableStyle(style))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(GRID)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 9.5 * mm,
                      "BESSopt planning estimate. Not a substitute for a site survey or formal feasibility study.")
    canvas.drawRightString(PAGE_W - MARGIN, 9.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _inputs_rows(report: Report):
    i = report.inputs
    roof = f"{i.roof_area_m2:,.0f} m2" if i.roof_area_m2 else "No limit entered"
    rows = [
        ("Location", i.location_name or "Not specified"),
        ("Average load", f"{i.average_load_kw:,.1f} kW"),
        ("Load-shedding", f"{i.daily_loadshedding_hours:g} hours per day"),
        ("Operating schedule", f"{i.operating_hours_per_day:g} hours per day, {i.operating_days_per_year} days per year"),
        ("Daytime share of load", f"{i.daytime_load_share * 100:.0f}%"),
        ("Diesel price", f"PKR {i.diesel_price_pkr_per_litre:,.0f} per litre"),
        ("Grid tariff", f"PKR {i.grid_tariff_pkr_per_kwh:,.1f} per kWh"),
        ("Solar yield", f"{i.solar_yield_kwh_per_kwp:,.0f} kWh per kWp per year"),
        ("Wind capacity factor", f"{i.wind_capacity_factor * 100:.0f}%"),
        ("Roof area", roof),
        ("Analysis period", f"{i.analysis_years} years"),
    ]
    return [[Paragraph(f"<b>{_esc(a)}</b>", S_CELL), Paragraph(_esc(b), S_CELL)] for a, b in rows]


def build_pdf(report: Report) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16 * mm, bottomMargin=20 * mm,
        title="BESSopt Techno-Economic Report", author="BESSopt",
    )
    story = []

    # ---- Header -----------------------------------------------------------
    story.append(Paragraph("BESSopt Techno-Economic Report", S_TITLE))
    place = f" for {_esc(report.inputs.location_name)}" if report.inputs.location_name else ""
    today = datetime.date.today().strftime("%d %B %Y")
    story.append(Paragraph(f"Solar, wind and battery options compared against grid plus diesel{place}. {today}.", S_SUB))
    story.append(Spacer(1, 4))
    rule = Table([[""]], colWidths=[CONTENT_W], rowHeights=[2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AMBER)]))
    story.append(rule)

    # ---- Recommendation ---------------------------------------------------
    story.append(Paragraph("Recommendation", S_H))
    story.append(Paragraph(_esc(summary_text(report)), S_BODY))

    rec = report.configs.get(report.recommended_key) if report.recommended_key else None
    if rec:
        story.append(Spacer(1, 6))
        facts = [
            [Paragraph("System", S_HEAD), Paragraph("Up-front cost", S_HEAD), Paragraph("Yearly saving", S_HEAD),
             Paragraph("Payback", S_HEAD), Paragraph(f"Ahead after {report.inputs.analysis_years} yrs", S_HEAD)],
            [Paragraph(_esc(system_description(rec)), S_CELL_B), Paragraph(f"PKR {_m(rec.capex_total)} million", S_CELL_B),
             Paragraph(f"PKR {_m(rec.annual_savings)} million", S_CELL_B), Paragraph(fmt_years(rec.payback_years), S_CELL_B),
             Paragraph(f"PKR {_m(rec.net_benefit)} million", S_CELL_B)],
        ]
        story.append(_table(facts, [52 * mm, 30 * mm, 30 * mm, 22 * mm, CONTENT_W - 134 * mm]))

    # ---- Site -------------------------------------------------------------
    story.append(Paragraph("Site and inputs", S_H))
    story.append(_table(_inputs_rows(report), [48 * mm, CONTENT_W - 48 * mm], header=False))

    # ---- Options compared -------------------------------------------------
    story.append(Paragraph("Options compared", S_H))
    head = ["Option", "Equipment", "CapEx (PKR M)", "Yearly cost (PKR M)", "Yearly saving (PKR M)", "Payback",
            f"ROI ({report.inputs.analysis_years} yrs)"]
    rows = [[Paragraph(h, S_HEAD) for h in head]]
    highlight = None
    for k in CONFIG_ORDER:
        c = report.configs[k]
        label = c.label + (" (recommended)" if k == report.recommended_key else "")
        if k == report.recommended_key:
            highlight = len(rows)
        if k == "baseline":
            rows.append([Paragraph(_esc(label), S_CELL_B), Paragraph("No new equipment", S_CELL), Paragraph("-", S_CELL),
                         Paragraph(_m(c.annual_cost), S_CELL), Paragraph("-", S_CELL), Paragraph("-", S_CELL),
                         Paragraph("-", S_CELL)])
        elif not c.available:
            rows.append([Paragraph(_esc(label), S_CELL_B), Paragraph("Not modelled: " + _esc(c.note), S_CELL),
                         Paragraph("-", S_CELL), Paragraph("-", S_CELL), Paragraph("-", S_CELL), Paragraph("-", S_CELL),
                         Paragraph("-", S_CELL)])
        else:
            rows.append([Paragraph(_esc(label), S_CELL_B), Paragraph(_esc(system_description(c)), S_CELL),
                         Paragraph(_m(c.capex_total), S_CELL), Paragraph(_m(c.annual_cost), S_CELL),
                         Paragraph(_m(c.annual_savings), S_CELL), Paragraph(fmt_years(c.payback_years), S_CELL),
                         Paragraph(_roi(c.roi_pct), S_CELL)])
    widths = [31 * mm, 45 * mm, 20 * mm, 20 * mm, 20 * mm, 17 * mm, CONTENT_W - 153 * mm]
    story.append(_table(rows, widths, highlight_row=highlight))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Yearly cost is what the site would pay each year for grid power, diesel and upkeep under that option. "
        "Yearly saving is the drop against the current setup.", S_NOTE))

    # ---- Sensitivity ------------------------------------------------------
    sens_heading = Paragraph("If prices move", S_H)
    srows = [[Paragraph(h, S_HEAD) for h in ["Option", "Payback now", "Diesel 20% dearer", "Grid tariff 15% higher"]]]
    for k in CONFIG_ORDER:
        s = report.sensitivity.get(k)
        if not s:
            continue
        srows.append([Paragraph(_esc(report.configs[k].label), S_CELL_B),
                      Paragraph(fmt_years(s["base"].payback_years), S_CELL),
                      Paragraph(fmt_years(s["diesel_up_20"].payback_years), S_CELL),
                      Paragraph(fmt_years(s["tariff_up_15"].payback_years), S_CELL)])
    if len(srows) > 1:
        story.append(KeepTogether([sens_heading, _table(srows, [60 * mm, 38 * mm, 38 * mm, CONTENT_W - 136 * mm])]))
    else:
        story.append(KeepTogether([sens_heading, Paragraph(
            "No option pays back at these inputs, so there is nothing to stress-test.", S_BODY)]))

    # ---- Assumptions ------------------------------------------------------
    story.append(Paragraph("How the numbers were built", S_H))
    story.append(Paragraph(
        "The model is an annual energy balance, not an hour-by-hour simulation. The maths runs as plain code with "
        "no AI involved, so the same inputs always give the same answer. The prices below are planning "
        "assumptions, not quotes.", S_BODY))
    story.append(Spacer(1, 4))
    for line in ASSUMPTIONS:
        story.append(Paragraph(_esc(line), S_BULLET, bulletText="-"))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
