# BESSopt — A BESS Techno-Economic Advisor

Built for the HEC–NCEAC & PEC Generative & Agentic AI Training, Cohort 11 — Mid-Term Hackathon (PakAngels).

BESSopt tells a Pakistani SME whether switching from diesel generator backup to a Battery
Energy Storage System (BESS) actually pays off — using their own numbers instead of a
vendor's sales pitch.

## What's in this repo

```
bessopt/
├── app/
│   ├── app.py              # Streamlit frontend
│   ├── calc_engine.py       # Deterministic CapEx/OpEx/payback/ROI math (no AI here)
│   └── bill_extraction.py   # Vision-based bill photo parsing (Claude API)
├── tests/
│   └── test_calc_engine.py  # Unit tests for the calculation engine
├── requirements.txt
└── README.md
```

## Why the math and the AI are kept separate

`calc_engine.py` contains plain, auditable arithmetic — no model call touches these numbers.
`bill_extraction.py` is the only place an AI model is used, and only to read a bill photo into
structured fields. If that call fails or no API key is set, the app falls back to manual entry.
This split is intentional: it's what makes the financial output defensible to an SME owner or
a bank, not just "an AI said so."

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app/app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

The bill-photo feature needs an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=your_key_here
streamlit run app/app.py
```

Without a key, manual entry still works fully — the photo feature is additive, not required.

## Running tests

```bash
python -m pytest tests/
# or, without pytest installed:
python tests/test_calc_engine.py
```

## Deploying (for the hackathon submission link)

### Option A — Streamlit Community Cloud (fastest)

1. Push this repo to your own GitHub account (see below).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app**, pick this repo, set the main file path to `app/app.py`.
4. Under **Advanced settings → Secrets**, add:
   ```
   ANTHROPIC_API_KEY = "your_key_here"
   ```
5. Deploy. Streamlit gives you a public URL — that's your **Application Working Link**.

### Option B — Hugging Face Spaces

1. Create a new Space at [huggingface.co/new-space](https://huggingface.co/new-space), SDK: Streamlit.
2. Push this repo's contents to the Space's git remote (same push steps as GitHub, just a
   different remote URL — Hugging Face gives you one when you create the Space).
3. Add `ANTHROPIC_API_KEY` under the Space's **Settings → Repository secrets**.
4. The Space builds automatically and gives you a public URL.

## Pushing this repo to GitHub

From this project folder:

```bash
git init
git add .
git commit -m "Initial commit: BESSopt MVP"
git branch -M main
git remote add origin https://github.com/<your-username>/bessopt.git
git push -u origin main
```

Make sure the repo is **public** (or at least "anyone with the link can view") — the hackathon
submission form requires a viewable link.

## Tuning local assumptions

Diesel price, grid tariff default, battery cost per kWh, and cycle life all live as named
constants at the top of `app/calc_engine.py`. Update them there as prices change — nothing
else in the app hardcodes a number.

## Team

| Member | Role |
|---|---|
| M. Zain Khan | Calculation Engine + Team Lead |
| Adnan Yousaf | Frontend |
| Saqib Mehmood | Backend |
| Ahmad Nazir | Frontend Support + Deployment |
| Atta Muhammad Mazhar | Vision Extraction |
| Dr. Ayesha Sultan | Documentation & Presentation |
