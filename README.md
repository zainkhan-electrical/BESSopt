# BESSopt v2: a Solar, Wind & BESS Techno-Economic Advisor

Built for the HEC-NCEAC & PEC Generative & Agentic AI Training, Cohort 11 hackathon (PakAngels).

A Pakistani SME enters its load, load-shedding hours and location. BESSopt compares five setups
against the grid-plus-diesel arrangement it runs today and recommends the one that pays off best:

| Option | What it is |
|---|---|
| Current setup | Grid plus diesel generator, nothing new |
| Battery only | LFP battery, recharged from the grid |
| Solar + battery | PV sized to daytime load and battery recharging, limited by roof area |
| Wind + battery | Small wind turbine plus battery, only where the wind resource is usable |
| Solar + wind + battery | Both, plus battery |

The result comes with a payback and ROI for each option, a price sensitivity check (diesel +20%,
grid tariff +15%), and a **PDF report** the user can download.

## Files

```
app.py              Streamlit app: inputs, results, PDF download
calc_engine.py      The maths. Plain Python, no AI. All prices and assumptions live at the top
resource_data.py    Planning-level solar yield and wind capacity factor per city
report_pdf.py       Builds the PDF report (reportlab)
bill_extraction.py  Reads a bill photo with a vision model (Groq). Optional
test_calc_engine.py Tests for the engine and the PDF builder
requirements.txt
```

## Where AI is used, and where it is not

Only `bill_extraction.py` calls a model, and only to read the monthly units off a bill photo. Every
CapEx, OpEx, payback and ROI figure, and every sentence of the recommendation, comes from
`calc_engine.py`. Same inputs, same answer, and each number can be checked by hand. If the bill
reader fails or has no API key, the app asks for the details instead.

## Honest limits

- The model is an annual energy balance, not an hour-by-hour simulation.
- Payback and ROI are simple and undiscounted, with no price escalation or panel degradation.
- The per-city solar and wind values are rough planning figures. Check solar yield in PVGIS or
  NASA POWER, and measure wind on site, before anyone buys equipment.
- Equipment prices are editable assumptions in `calc_engine.py`, not quotes.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

For bill-photo reading, set a Groq key first: `export GROQ_API_KEY=your_key_here`.

## Tests

```bash
python test_calc_engine.py
```

## Deploy

Push the files to the root of the GitHub repo, then on Streamlit Community Cloud set the main file
to `app.py` and add `GROQ_API_KEY` under Secrets. Streamlit redeploys on every push.

## Team

M. Zain Khan, Adnan Yousaf, Saqib Mehmood, Ahmad Nazir, Atta Muhammad Mazhar, Dr. Ayesha Sultan.
