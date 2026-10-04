"""
bill_extraction.py — turns a photo of a Pakistani electricity bill into
structured numbers the calculation engine can use.

This is the one place in the app that calls an AI model. It only extracts
data (units consumed, tariff info, DISCO name) — it never touches the
CapEx/OpEx/ROI math, which lives entirely in calc_engine.py.

Uses Groq's vision API (Qwen3.6-27B) — OpenAI-compatible SDK, fast
inference, cheap. Requires a GROQ_API_KEY environment variable / Streamlit
secret. If it's missing or the call fails, the app falls back to manual
entry — this feature is additive, never a hard requirement to use BESSopt.

Note: Groq's roster of vision-capable models has changed before (their
earlier Llama 4 Scout/Maverick vision models were deprecated). If this
model ID ever starts returning a "model_not_found" error, check Groq's
current model list at https://console.groq.com/docs/vision and update
GROQ_VISION_MODEL below.
"""

import base64
import json
import os

GROQ_VISION_MODEL = "qwen/qwen3.6-27b"

EXTRACTION_PROMPT = """You are reading a photo of a Pakistani electricity bill \
(K-Electric, LESCO, or another DISCO). Do not show your reasoning or use any \
<think> tags — respond with nothing but the JSON object below, no other text.

IMPORTANT for units_consumed_kwh: bills often show several different \
"units" numbers — a breakdown by off-peak/peak energy, MDI, reactive \
energy, or a 13-month usage chart. Ignore all of those. Use ONLY the total \
monthly consumption figure, usually shown prominently near the top as \
"Current Month" or "Units Consumed", often formatted like \
"39,741 units = Rs. X". That top-line total is the number to extract.

Extract exactly these fields:

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
    Sends the bill photo to Groq (Qwen3.6-27B) for structured extraction.
    Returns a dict matching EXTRACTION_PROMPT's schema, or an error dict
    the caller can use to fall back to manual entry.
    """
    try:
        from groq import Groq
    except ImportError:
        return {"error": "groq package not installed"}

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"error": "GROQ_API_KEY not set"}

    client = Groq(api_key=api_key)
    b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{media_type};base64,{b64_image}"

    try:
        response = client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return {"error": "model returned an empty response"}

        # This model "thinks out loud" in a <think>...</think> block before
        # its real answer. Strip that out — if the block never closed
        # (ran out of tokens mid-thought), there's no usable answer at all.
        if "<think>" in text:
            if "</think>" in text:
                text = text.split("</think>", 1)[1].strip()
            else:
                return {"error": "model ran out of tokens while still reasoning — try again"}

        # Model sometimes wraps JSON in code fences, or adds a sentence
        # before/after the object despite instructions — pull out just the
        # {...} block rather than assuming the whole string is clean JSON.
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return {"error": f"couldn't find a JSON object in the model's response: {text[:200]!r}"}
        json_slice = text[start : end + 1]

        try:
            return json.loads(json_slice)
        except json.JSONDecodeError as exc:
            return {"error": f"model's response wasn't valid JSON ({exc}): {json_slice[:200]!r}"}
    except Exception as exc:  # noqa: BLE001 — surfaced to the UI as a fallback
        return {"error": str(exc)}
