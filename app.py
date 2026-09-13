"""
app.py — BESSopt Streamlit frontend.

Two ways in: manual form entry, or upload a bill photo and let the vision
model pre-fill the units-consumed field. Either path feeds the same
deterministic calc_engine — the app never lets the AI layer touch the math.
"""

import streamlit as st
from calc_engine import SiteInputs, full_report
from bill_extraction import extract_bill_data

st.set_page_config(page_title="BESSopt — BESS Techno-Economic Advisor", page_icon="🔋", layout="centered")

st.title("🔋 BESSopt")
st.caption("A BESS Techno-Economic Advisor for Pakistani SMEs")

st.markdown(
    "Find out whether switching from diesel to battery storage actually pays "
    "off for your business — with real numbers, not a sales pitch."
)

st.divider()

# ---------------------------------------------------------------------------
# Input section
# ---------------------------------------------------------------------------
st.subheader("1. Tell us about your setup")

input_mode = st.radio(
    "How would you like to provide your details?",
    ["Manual entry", "Upload a bill photo"],
    horizontal=True,
)

units_hint = None

if input_mode == "Upload a bill photo":
    uploaded = st.file_uploader("Upload a photo of your electricity bill", type=["jpg", "jpeg", "png"])
    if uploaded is not None:
        st.image(uploaded, caption="Uploaded bill", width=300)
        with st.spinner("Reading your bill..."):
            result = extract_bill_data(uploaded.getvalue(), media_type=uploaded.type or "image/jpeg")
        if "error" in result:
            st.warning(
                f"Couldn't auto-read the bill ({result['error']}). "
                "No problem — just fill in the details manually below."
            )
        else:
            st.success(f"Extracted from your bill (confidence: {result.get('confidence', 'unknown')})")
            st.json(result)
            units_hint = result.get("units_consumed_kwh")

with st.form("site_form"):
    col1, col2 = st.columns(2)
    with col1:
        loadshedding_hours = st.number_input(
            "Daily load-shedding hours", min_value=0.0, max_value=24.0, value=6.0, step=0.5
        )
        average_load_kw = st.number_input(
            "Average load during outage (kW)", min_value=1.0, value=25.0, step=1.0
        )
        genset_kva = st.number_input(
            "Current generator size (kVA)", min_value=0.0, value=40.0, step=5.0
        )
    with col2:
        diesel_price = st.number_input(
            "Diesel price (PKR/litre)", min_value=1.0, value=278.0, step=1.0
        )
        grid_tariff = st.number_input(
            "Grid tariff (PKR/kWh)", min_value=1.0, value=45.0, step=1.0
        )
        horizon_years = st.slider("Analysis horizon (years)", min_value=3, max_value=15, value=7)

    submitted = st.form_submit_button("Generate report", use_container_width=True)

# ---------------------------------------------------------------------------
# Report section
# ---------------------------------------------------------------------------
if submitted:
    inputs = SiteInputs(
        daily_loadshedding_hours=loadshedding_hours,
        average_load_kw=average_load_kw,
        genset_kva=genset_kva,
        diesel_price_pkr_per_litre=diesel_price,
        grid_tariff_pkr_per_kwh=grid_tariff,
        analysis_years=horizon_years,
    )
    report = full_report(inputs)
    sizing = report["sizing"]
    fin = report["financials"]
    sens = report["sensitivity"]

    st.divider()
    st.subheader("2. Recommended system")
    c1, c2 = st.columns(2)
    c1.metric("Recommended BESS size", f"{sizing.recommended_bess_kwh:,.0f} kWh")
    c2.metric("Recommended inverter/PCS", f"{sizing.recommended_inverter_kw:,.1f} kW")

    st.subheader("3. Financial summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Estimated CapEx", f"PKR {fin.capex_pkr:,.0f}")
    c2.metric("Payback period", f"{fin.payback_years:.2f} years" if fin.payback_years > 0 else "N/A")
    c3.metric("ROI over horizon", f"{fin.roi_pct_over_horizon:.1f}%")

    c1, c2, c3 = st.columns(3)
    c1.metric("Diesel baseline cost/yr", f"PKR {fin.annual_diesel_baseline_pkr:,.0f}")
    c2.metric("BESS OpEx/yr", f"PKR {fin.annual_bess_opex_pkr:,.0f}")
    c3.metric("Annual savings", f"PKR {fin.annual_savings_pkr:,.0f}")

    st.caption(f"Estimated useful battery life: {fin.battery_useful_life_years:.1f} years at one full cycle/day.")

    st.subheader("4. Sensitivity analysis")
    st.markdown("What happens if prices move against you:")

    sens_rows = []
    for label, key in [
        ("Base case", "base_case"),
        ("Diesel price +20%", "diesel_price_up_20pct"),
        ("Grid tariff +15%", "grid_tariff_up_15pct"),
    ]:
        r = sens[key]
        sens_rows.append(
            {
                "Scenario": label,
                "Payback (years)": f"{r.payback_years:.2f}" if r.payback_years > 0 else "N/A",
                "ROI (%)": f"{r.roi_pct_over_horizon:.1f}",
                "Annual savings (PKR)": f"{r.annual_savings_pkr:,.0f}",
            }
        )
    st.table(sens_rows)

    st.subheader("5. In plain terms")
    if fin.payback_years > 0 and fin.payback_years <= horizon_years:
        st.success(
            f"Based on what you've entered, switching to a {sizing.recommended_bess_kwh:,.0f} kWh "
            f"battery system pays for itself in about {fin.payback_years:.1f} years, and keeps "
            f"saving money for the rest of its {fin.battery_useful_life_years:.0f}-year working life. "
            f"Even if diesel prices jump 20%, payback only improves."
        )
    else:
        st.info(
            "Based on what you've entered, the payback period is longer than your chosen analysis "
            "horizon. This can still make sense for reliability reasons, but the pure financial "
            "case is weaker at these numbers — try adjusting your inputs to see what changes it."
        )

    st.caption(
        "This is a planning estimate, not a substitute for a formal engineering feasibility "
        "study before purchase."
    )

st.divider()
st.caption("BESSopt — built for the HEC–NCEAC & PEC Generative & Agentic AI Training, Cohort 11 Mid-Term Hackathon.")
