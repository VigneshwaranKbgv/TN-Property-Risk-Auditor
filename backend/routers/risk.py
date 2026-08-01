"""
routers/risk.py
POST /api/risk — property risk evaluation endpoint.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator

from services.spatial_engine import evaluate_property_risk
from services.llm_service import generate_risk_report
from utils.geo_utils import get_state_for_coords, is_within_tamil_nadu

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Log file path ─────────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).resolve().parent.parent / "queries.log"


# ── Request / Response models ─────────────────────────────────────────────────
class RiskRequest(BaseModel):
    lat: float
    lon: float

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not (-90 <= v <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, v: float) -> float:
        if not (-180 <= v <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return v


class RiskResponse(BaseModel):
    risk_metrics: dict
    report: str
    overall_risk: str


# ── POST /api/risk ─────────────────────────────────────────────────────────────
@router.post("/risk", response_model=RiskResponse)
async def assess_risk(request: RiskRequest) -> RiskResponse:
    """
    Evaluates environmental and legal risk for a property at the given coordinates.

    Steps:
    1. Validates lat/lon is within Tamil Nadu bounding box.
    2. Runs geospatial risk checks (water body, CRZ, flood zone).
    3. Generates a plain-English LLM risk report.
    4. Logs the query (coordinates + risk level only, no personal data).
    5. Returns risk_metrics, report, and overall_risk.
    """
    lat, lon = request.lat, request.lon

    # ── 1. Tamil Nadu boundary check (bounding box — fast, no network) ────────
    if not is_within_tamil_nadu(lat, lon):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Coordinates ({lat}, {lon}) are outside Tamil Nadu. "
                "Valid range: lat 8.0–13.6, lon 76.2–80.4"
            ),
        )

    # ── 1b. Tamil Nadu state check (reverse geocode) ──────────────────────────
    # The bounding box above is rectangular and necessarily overlaps slivers of
    # Kerala/Karnataka/Andhra Pradesh. Fails permissively (state is None) if
    # the geocoder is unreachable, so a flaky third party can't block real
    # Tamil Nadu queries.
    state = get_state_for_coords(lat, lon)
    if state is not None and "tamil nadu" not in state.lower():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Coordinates ({lat}, {lon}) appear to be in {state}, not Tamil Nadu. "
                "This tool only supports Tamil Nadu properties."
            ),
        )

    # ── 2. Geospatial risk evaluation ─────────────────────────────────────────
    try:
        risk_metrics = evaluate_property_risk(lat, lon)
    except Exception as e:
        logger.error(f"[Risk] Spatial evaluation failed for ({lat}, {lon}): {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Spatial evaluation error: {str(e)}",
        )

    # ── 3. LLM risk report ────────────────────────────────────────────────────
    try:
        report = generate_risk_report(risk_metrics)
    except Exception as e:
        logger.error(f"[Risk] LLM report generation failed: {e}")
        report = (
            "Unable to generate AI report at this time. "
            "Please review the raw risk metrics above."
        )

    overall_risk = risk_metrics.get("overall_risk", "UNKNOWN")

    # ── 4. Audit log (no PII — only coordinates + risk level + timestamp) ─────
    _log_query(lat, lon, overall_risk)

    # ── 5. Return response ────────────────────────────────────────────────────
    return RiskResponse(
        risk_metrics=risk_metrics,
        report=report,
        overall_risk=overall_risk,
    )


def _log_query(lat: float, lon: float, risk_level: str) -> None:
    """Appends a single audit log line to queries.log."""
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        log_line = f"{timestamp} | lat={lat} lon={lon} | risk={risk_level}\n"
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        logger.warning(f"[Risk] Could not write to queries.log: {e}")
