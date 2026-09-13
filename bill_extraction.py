"""
bill_extraction.py — turns a photo of a Pakistani electricity bill into
structured numbers the calculation engine can use.

This is the one place in the app that calls an AI model. It only extracts
data (units consumed, tariff info, DISCO name) — it never touches the
CapEx/OpEx/ROI math, which lives entirely in calc_engine.py.

Requires an ANTHROPIC_API_KEY environment variable / Streamlit secret.
If it's missing or the call fails, the app falls back to manual entry —
this feature is additive, never a hard requirement to use BESSopt.
"""

import base64
import json
import os

EXTRACTION_PROMPT = """You are reading a photo of a Pakistani electricity bill \
(K-Electric, LESCO, or another DISCO). Extract exactly these fields and return \
ONLY a JSON object, no other text:

{
  "units_consumed_kwh": <number or null>,
  "tariff_category": <string or null>,
  "billed_amount_pkr": <number or null>,
  "disco_name": <string or null>,
  "billing_month": <string or null>,
  "confidence": <"high" | "medium" | "low">
}

If a field isn't visible or you're unsure, use null for that field and lower \
the confidence accordingly. Do not guess numbers you cannot actually read."""


def extract_bill_data(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """
    Sends the bill photo to Claude for structured extraction.
    Returns a dict matching EXTRACTION_PROMPT's schema, or an error dict
    the caller can use to fall back to manual entry.
    """
    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic package not installed"}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    client = anthropic.Anthropic(api_key=api_key)
    b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }
            ],
        )
        text = response.content[0].text.strip()
        # Model sometimes wraps JSON in code fences despite instructions.
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as exc:  # noqa: BLE001 — surfaced to the UI as a fallback
        return {"error": str(exc)}
