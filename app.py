"""
app.py - BESSopt v2 Streamlit front end.

Flow: describe the site (by hand, or let a vision model read a bill photo),
pick a location, and get solar, wind and battery options compared against the
current grid-plus-diesel setup, with a PDF report to download.

Every number comes from calc_engine.py. The vision model only reads the bill.
"""

import streamlit as st

from bill_extraction import extract_bill_data
from calc_engine import (
    ASSUMPTIONS, CONFIG_ORDER, SiteInputs, build_report, fmt_pkr, fmt_years,
    summary_text, system_description,
)
from report_pdf import build_pdf
from resource_data import CITY_NAMES, CITY_RESOURCES, OTHER_LABEL

st.set_page_config(page_title="BESSopt - Solar, Wind & BESS Advisor", page_icon="🔋", layout="centered")

st.title("🔋 BESSopt")
st.caption("A Solar, Wind & BESS Techno-Economic Advisor for Pakistani SMEs")
st.markdown(
    "Find out which mix of solar, wind and battery storage pays off for your business, "
    "compared with the grid-plus-diesel setup you run today."
)
st.divider()

# ---------------------------------------------------------------------------
# 1. Describe the site
# ---------------------------------------------------------------------------
st.subheader("1. Tell us about your site")

mode = st.radio("How would you like to enter your details?", ["Manual entry", "Upload a bill photo"], horizontal=True)

DEFAULT_OP_HOURS = 12.0
DEFAULT_OP_DAYS = 330
units_hint = None

if mode == "Upload a bill photo":
    uploaded = st.file_uploader("Upload a photo of your electricity bill", type=["jpg", "jpeg", "png"])
    if uploaded is not None:
        st.image(uploaded, caption="Uploaded bill", width=300)
        data = uploaded.getvalue()
        cache = st.session_state.setdefault("bill_cache", {})
        cache_key = (uploaded.name, len(data))
        if cache_key not in cache:  # one API call per file, not one per rerun
            with st.spinner("Reading your bill..."):
                cache[cache_key] = extract_bill_data(data, media_type=uploaded.type or "image/jpeg")
        result = cache[cache_key]
        if "error" in result:
            st.warning(f"Couldn't read the bill automatically ({result['error']}). Please enter the details below.")
        else:
            st.success(f"Read from your bill (confidence: {result.get('confidence', 'unknown')})")
            st.json(result)
            try:
                units_hint = float(str(result.get("units_consumed_kwh")).replace(",", ""))
            except (TypeError, ValueError):
                units_hint = None

suggested_load = None
if units_hint and units_hint > 0:
    # monthly kWh -> average kW while the site is running
    suggested_load = round(units_hint * 12 / (DEFAULT_OP_HOURS * DEFAULT_OP_DAYS), 1)
    st.info(
        f"Your bill shows about {units_hint:,.0f} units a month. Assuming {DEFAULT_OP_HOURS:g} operating hours a day "
        f"and {DEFAULT_OP_DAYS} days a year, that is an average load of about {suggested_load:,.1f} kW. "
        "It is filled in below, so change it if your schedule is different."
    )

city = st.selectbox("Where is the site?", CITY_NAMES + [OTHER_LABEL])
res = CITY_RESOURCES.get(city, {"solar_kwh_per_kwp": 1600, "wind_cf": 0.10})
rc1, rc2 = st.columns(2)
solar_yield = rc1.number_input(
    "Solar yield (kWh per kWp per year)", min_value=800.0, max_value=2200.0,
    value=float(res["solar_kwh_per_kwp"]), step=10.0, key=f"solar_yield_{city}",
)
wind_cf_pct = rc2.number_input(
    "Wind capacity factor (%)", min_value=0.0, max_value=60.0,
    value=float(res["wind_cf"] * 100), step=1.0, key=f"wind_cf_{city}",
)
st.caption(
    "City values are rough planning figures. Check solar yield in PVGIS or NASA POWER, and measure wind on site, "
    "before buying anything."
)

form_tag = int(units_hint) if units_hint else 0
with st.form("site_form"):
    c1, c2 = st.columns(2)
    with c1:
        avg_load = st.number_input(
            "Average load while running (kW)", min_value=1.0, max_value=5000.0,
            value=float(suggested_load or 25.0), step=1.0, key=f"avg_load_{form_tag}",
        )
        ls_hours = st.number_input("Load-shedding hours per day", min_value=0.0, max_value=24.0, value=6.0, step=0.5)
        op_hours = st.number_input("Operating hours per day", min_value=1.0, max_value=24.0, value=DEFAULT_OP_HOURS, step=1.0)
        op_days = st.number_input("Operating days per year", min_value=1, max_value=365, value=DEFAULT_OP_DAYS, step=1)
        roof_area = st.number_input("Roof area available (m2, 0 = no limit)", min_value=0.0, value=0.0, step=10.0)
    with c2:
        diesel_price = st.number_input("Diesel price (PKR per litre)", min_value=1.0, value=278.0, step=1.0)
        grid_tariff = st.number_input("Grid tariff (PKR per kWh)", min_value=1.0, value=45.0, step=1.0)
        daytime_share = st.slider("Share of load during daylight (%)", min_value=20, max_value=100, value=80)
        years = st.slider("Analysis period (years)", min_value=3, max_value=15, value=7)
        genset_kva = st.number_input("Current generator (kVA, optional)", min_value=0.0, value=0.0, step=5.0)
    submitted = st.form_submit_button("Compare options", use_container_width=True)

if submitted:
    inputs = SiteInputs(
        average_load_kw=avg_load,
        daily_loadshedding_hours=ls_hours,
        operating_hours_per_day=op_hours,
        operating_days_per_year=int(op_days),
        daytime_load_share=daytime_share / 100.0,
        diesel_price_pkr_per_litre=diesel_price,
        grid_tariff_pkr_per_kwh=grid_tariff,
        analysis_years=int(years),
        solar_yield_kwh_per_kwp=solar_yield,
        wind_capacity_factor=wind_cf_pct / 100.0,
        roof_area_m2=roof_area if roof_area > 0 else None,
        genset_kva=genset_kva if genset_kva > 0 else None,
        location_name="" if city == OTHER_LABEL else city,
    )
    report = build_report(inputs)
    st.session_state["report"] = report
    st.session_state["pdf_bytes"] = build_pdf(report)

# ---------------------------------------------------------------------------
# 2. Results (kept in session state so a download click doesn't wipe them)
# ---------------------------------------------------------------------------
report = st.session_state.get("report")
if report:
    inp = report.inputs
    rec = report.configs.get(report.recommended_key) if report.recommended_key else None

    st.divider()
    st.subheader("2. Recommendation")
    if rec:
        st.success(summary_text(report))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Up-front cost", fmt_pkr(rec.capex_total))
        m2.metric("Yearly saving", fmt_pkr(rec.annual_savings))
        m3.metric("Payback", fmt_years(rec.payback_years))
        m4.metric(f"Ahead after {inp.analysis_years} yrs", fmt_pkr(rec.net_benefit))
        st.caption(f"Recommended system: {system_description(rec)}.")
    else:
        st.info(summary_text(report))

    st.subheader("3. Options compared")
    rows = []
    for k in CONFIG_ORDER:
        c = report.configs[k]
        name = c.label + ("  (recommended)" if k == report.recommended_key else "")
        if k == "baseline":
            rows.append({"Option": name, "Equipment": "No new equipment", "CapEx (PKR M)": "-",
                         "Yearly cost (PKR M)": f"{c.annual_cost / 1e6:,.2f}", "Payback": "-", f"ROI ({inp.analysis_years} yrs)": "-"})
        elif not c.available:
            rows.append({"Option": name, "Equipment": "Not modelled here", "CapEx (PKR M)": "-",
                         "Yearly cost (PKR M)": "-", "Payback": "-", f"ROI ({inp.analysis_years} yrs)": "-"})
        else:
            rows.append({"Option": name, "Equipment": system_description(c), "CapEx (PKR M)": f"{c.capex_total / 1e6:,.2f}",
                         "Yearly cost (PKR M)": f"{c.annual_cost / 1e6:,.2f}", "Payback": fmt_years(c.payback_years),
                         f"ROI ({inp.analysis_years} yrs)": "n/a" if c.roi_pct is None else f"{c.roi_pct:,.0f}%"})
    st.table(rows)
    for k in ("wind_bess", "solar_wind_bess"):
        c = report.configs[k]
        if not c.available and c.note:
            st.caption(f"{c.label}: {c.note}")

    avail = [report.configs[k] for k in CONFIG_ORDER if report.configs[k].available]
    st.bar_chart({"Yearly running cost (PKR million)": {c.label: c.annual_cost / 1e6 for c in avail}}, horizontal=True)

    st.subheader("4. If prices move")
    srows = []
    for k in CONFIG_ORDER:
        s = report.sensitivity.get(k)
        if s:
            srows.append({"Option": report.configs[k].label, "Payback now": fmt_years(s["base"].payback_years),
                          "Diesel +20%": fmt_years(s["diesel_up_20"].payback_years),
                          "Grid tariff +15%": fmt_years(s["tariff_up_15"].payback_years)})
    if srows:
        st.table(srows)

    st.subheader("5. Take it with you")
    st.download_button(
        "Download PDF report", data=st.session_state["pdf_bytes"], file_name="BESSopt_report.pdf",
        mime="application/pdf", on_click="ignore", use_container_width=True,
    )

    with st.expander("How these numbers were built"):
        for line in ASSUMPTIONS:
            st.markdown(f"- {line}")

st.divider()
st.caption(
    "A planning estimate, not a replacement for a site survey. "
    "Built for the HEC-NCEAC & PEC Generative & Agentic AI Training, Cohort 11 hackathon."
)
