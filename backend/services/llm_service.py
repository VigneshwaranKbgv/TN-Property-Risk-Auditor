"""
llm_service.py
NVIDIA NIM LLM integration for risk report generation and follow-up Q&A.
Uses the OpenAI-compatible SDK with NVIDIA's base URL.
"""

import copy
import json
import logging
import os
from typing import Generator

from openai import OpenAI, APIError, APITimeoutError, APIConnectionError

from utils.geo_utils import format_distance

logger = logging.getLogger(__name__)

# ── NVIDIA NIM Client ─────────────────────────────────────────────────────────
def _get_client() -> OpenAI:
    """Create and return an OpenAI client pointed at NVIDIA NIM."""
    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.getenv("NVIDIA_API_KEY", ""),
    )


# ── Model routing ─────────────────────────────────────────────────────────────
MODEL_DEEP = "meta/llama-3.1-8b-instruct"
MODEL_FAST = "meta/llama-3.1-8b-instruct"



def _select_model(risk_metrics: dict) -> str:
    """
    Routes to DeepSeek R1 for HIGH risk scenarios (complex legal reasoning),
    Phi-4-mini for MEDIUM/LOW (fast and cheap).
    """
    overall = risk_metrics.get("overall_risk", "LOW")
    water = risk_metrics.get("water_body", {})
    crz = risk_metrics.get("crz", {})
    flood = risk_metrics.get("flood_zone", {})

    high_flags = [
        overall == "HIGH",
        water.get("infringement", False),
        crz.get("inside_zone", False) and crz.get("zone_type") == "CRZ-I",
        flood.get("inside_zone", False) and flood.get("risk_level") == "HIGH",
    ]

    if any(high_flags):
        logger.info(f"[LLM] HIGH risk detected — routing to {MODEL_DEEP}")
        return MODEL_DEEP

    logger.info(f"[LLM] MEDIUM/LOW risk — routing to {MODEL_FAST}")
    return MODEL_FAST


# ── System prompts ─────────────────────────────────────────────────────────────
RISK_REPORT_SYSTEM_PROMPT = """You are a plain-language property legal advisor in Tamil Nadu, India.
You receive structured geospatial risk data about a property.
Your job is to write a clear, honest, non-jargon risk assessment
that a first-time homebuyer with no legal background can understand.

Rules:
- Never use legal jargon without explaining it immediately after
- Be specific about distances and zone types from the data
- Any field ending in "_formatted" (e.g. distance_meters_formatted) is already
  formatted for display — copy that string exactly (e.g. "42.14 km"). Do not
  read the raw numeric field, recompute the distance, or convert units yourself.
- Always end with a clear recommended next step
- Write in simple English. Max 300 words.
- Do not give investment advice. Only flag legal/environmental risks.
- If low risk, say so clearly and reassuringly — don't manufacture fear
- Format your response as 2-3 short paragraphs. No bullet points."""


def _format_risk_metrics_for_prompt(risk_metrics: dict) -> dict:
    """
    Returns a deep copy of risk_metrics with raw meter distances accompanied by
    a pre-formatted "_formatted" string (e.g. "42.14 km").

    The 8B model reliably garbles large multi-digit decimals (e.g. reading
    42137.13 as "421") when asked to transcribe them into prose. Formatting
    distances server-side and instructing the model to copy them verbatim
    removes that failure mode instead of relying on the model to do math.
    """
    formatted = copy.deepcopy(risk_metrics)

    water = formatted.get("water_body") or {}
    if water.get("distance_meters") is not None:
        water["distance_meters_formatted"] = format_distance(water["distance_meters"])

    crz = formatted.get("crz") or {}
    if crz.get("distance_to_boundary_meters") is not None:
        crz["distance_to_boundary_meters_formatted"] = format_distance(
            crz["distance_to_boundary_meters"]
        )

    return formatted


def _build_followup_system_prompt(risk_metrics: dict) -> str:
    formatted_metrics = _format_risk_metrics_for_prompt(risk_metrics)
    return f"""You are a friendly property advisor. The user has already received
a risk report for their property. Answer their follow-up questions
using the risk data provided. Be concise and plain-spoken.
Never guess — if the data doesn't cover their question, say so.
Any field ending in "_formatted" is already formatted for display (e.g.
"42.14 km") — copy it exactly rather than reading the raw numeric field.
Risk data: {json.dumps(formatted_metrics, indent=2)}"""


# ── generate_risk_report ──────────────────────────────────────────────────────
def generate_risk_report(risk_metrics: dict) -> str:
    """
    Generates a plain-language risk report using the appropriate NVIDIA NIM model.

    Args:
        risk_metrics: Structured dict from spatial_engine.evaluate_property_risk()

    Returns:
        Plain-English risk assessment string (max ~300 words).
    """
    client = _get_client()
    model = _select_model(risk_metrics)
    formatted_metrics = _format_risk_metrics_for_prompt(risk_metrics)
    user_message = f"Here is the property risk data: {json.dumps(formatted_metrics, indent=2)}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": RISK_REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=600,
        )

        report_text = response.choices[0].message.content
        if not report_text:
            raise ValueError("Empty response received from LLM")

        # Strip any <think> reasoning blocks that DeepSeek R1 may include
        report_text = _strip_think_tags(report_text)

        logger.info(f"[LLM] Risk report generated successfully (model={model})")
        return report_text.strip()

    except APITimeoutError:
        logger.error("[LLM] NVIDIA NIM API request timed out.")
        return _fallback_report(risk_metrics)
    except APIConnectionError as e:
        logger.error(f"[LLM] Could not connect to NVIDIA NIM API: {e}")
        return _fallback_report(risk_metrics)
    except APIError as e:
        logger.error(f"[LLM] NVIDIA NIM API error: {e}")
        return _fallback_report(risk_metrics)
    except Exception as e:
        logger.error(f"[LLM] Unexpected error generating report: {e}")
        return _fallback_report(risk_metrics)


# ── answer_followup (streaming) ────────────────────────────────────────────────
def answer_followup(
    question: str,
    risk_metrics: dict,
    history: list,
) -> Generator[str, None, None]:
    """
    Answers a follow-up question about the property using Phi-4-mini with streaming.

    Args:
        question:     User's follow-up question string.
        risk_metrics: Risk dict from spatial_engine (used as context).
        history:      List of {"role": ..., "content": ...} dicts (max last 6).

    Yields:
        Streamed text chunks from the LLM response.
    """
    client = _get_client()
    system_prompt = _build_followup_system_prompt(risk_metrics)

    # Keep only the last 6 messages of history to stay within context limits
    trimmed_history = history[-6:] if len(history) > 6 else history

    messages = [
        {"role": "system", "content": system_prompt},
        *trimmed_history,
        {"role": "user", "content": question},
    ]

    try:
        stream = client.chat.completions.create(
            model=MODEL_FAST,
            messages=messages,
            temperature=0.4,
            max_tokens=400,
            stream=True,
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    except APITimeoutError:
        logger.error("[LLM] NVIDIA NIM streaming API timed out.")
        yield "Sorry, the AI service timed out. Please try your question again."
    except APIConnectionError as e:
        logger.error(f"[LLM] Could not connect to NVIDIA NIM API for streaming: {e}")
        yield "Sorry, I couldn't connect to the AI service. Please check your network and try again."
    except APIError as e:
        logger.error(f"[LLM] NVIDIA NIM API streaming error: {e}")
        yield f"The AI service returned an error: {str(e)}"
    except Exception as e:
        logger.error(f"[LLM] Unexpected streaming error: {e}")
        yield "An unexpected error occurred. Please try again."


# ── Helpers ───────────────────────────────────────────────────────────────────
def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks that DeepSeek R1 produces during reasoning."""
    import re
    # Remove <think>...</think> blocks (including multiline)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned.strip()


def _fallback_report(risk_metrics: dict) -> str:
    """
    Generates a basic rule-based report when the LLM API is unavailable.
    Ensures the application never crashes on API failure.
    """
    overall = risk_metrics.get("overall_risk", "UNKNOWN")
    water = risk_metrics.get("water_body", {})
    crz = risk_metrics.get("crz", {})
    flood = risk_metrics.get("flood_zone", {})
    coords = risk_metrics.get("coordinates", {})

    lines = [
        f"PROPERTY RISK SUMMARY (AI service temporarily unavailable)",
        f"Location: {coords.get('lat', 'N/A')}°N, {coords.get('lon', 'N/A')}°E",
        f"Overall Risk Level: {overall}",
        "",
    ]

    if water.get("infringement"):
        lines.append(
            f"⚠ Water Body: This property's 50-metre boundary overlaps a water body. "
            f"Nearest: {water.get('nearest_body_name', 'Unknown')}."
        )
    elif water.get("distance_meters") is not None:
        lines.append(
            f"Water Body: Nearest water body is {water['distance_meters']:.0f} m away "
            f"({water.get('nearest_body_name', 'Unknown')})."
        )

    if crz.get("inside_zone"):
        lines.append(
            f"⚠ Coastal Zone: Property is inside a {crz.get('zone_type', 'CRZ')} area. "
            f"Construction in this zone is heavily regulated or prohibited."
        )

    if flood.get("inside_zone"):
        lines.append(
            f"⚠ Flood Zone: Property is in a {flood.get('risk_level', 'UNKNOWN')} flood risk area."
        )

    lines.append("")
    lines.append(
        "Recommended next step: Consult a licensed property lawyer or "
        "CMDA/DTCP-registered surveyor to verify these findings before "
        "signing any agreement."
    )

    return "\n".join(lines)
