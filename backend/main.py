"""
main.py
FastAPI application entry point for the TN Property Risk Auditor backend.
"""

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env before anything else so env vars are available everywhere
load_dotenv()

from routers.risk import router as risk_router
from routers.chat import router as chat_router
from services.data_fetcher import get_capabilities

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tn_risk_auditor")


# ── Application lifespan ───────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: print available TNGIS layers.
    Shutdown: (nothing needed for MVP).
    """
    logger.info("=" * 60)
    logger.info("  TN Property Risk Auditor — Backend Starting Up")
    logger.info("=" * 60)

    nvidia_key = os.getenv("NVIDIA_API_KEY", "")
    if not nvidia_key or nvidia_key == "nvapi-your-key-here":
        logger.warning(
            "NVIDIA_API_KEY is not set or is still the placeholder value. "
            "LLM features will not work until a valid key is provided."
        )
    else:
        logger.info(f"NVIDIA NIM API key loaded (ends with ...{nvidia_key[-6:]})")

    # Print available TNGIS layers
    logger.info("Fetching available TNGIS GIS layers …")
    try:
        layers = get_capabilities()
        if layers:
            logger.info(f"Available TNGIS layers ({len(layers)} total):")
            for layer in layers[:20]:   # Print first 20 to avoid log flood
                logger.info(f"  • {layer}")
            if len(layers) > 20:
                logger.info(f"  … and {len(layers) - 20} more (see capabilities_cache.json)")
        else:
            logger.warning("No TNGIS layers found — check network or capabilities_cache.json")
    except Exception as e:
        logger.error(f"Could not fetch TNGIS capabilities: {e}")

    # Pre-load spatial layers to cache in memory
    logger.info("Pre-loading geospatial risk layers into memory cache …")
    try:
        from services.data_fetcher import fetch_waterbodies_layer, load_crz_layer, load_flood_zone_layer
        fetch_waterbodies_layer()
        load_crz_layer()
        load_flood_zone_layer()
        logger.info("Geospatial layers cached successfully!")
    except Exception as e:
        logger.error(f"Failed to pre-load geospatial layers: {e}")

    logger.info("Backend is ready. API docs at http://localhost:8000/docs")
    logger.info("=" * 60)

    yield  # Application runs here

    logger.info("TN Property Risk Auditor — Shutting down.")


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TN Property Risk Auditor API",
    description=(
        "A civic tool that checks if a property in Tamil Nadu sits inside "
        "environmentally restricted zones (CRZ, flood zones, protected water bodies) "
        "using Tamil Nadu's public GIS infrastructure and NVIDIA NIM LLMs."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS middleware ────────────────────────────────────────────────────────────
cors_origin = os.getenv("CORS_ORIGIN", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[cors_origin, "http://localhost:3000"],  # Allow Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Router mounting ────────────────────────────────────────────────────────────
app.include_router(risk_router, prefix="/api", tags=["Risk Assessment"])
app.include_router(chat_router, prefix="/api", tags=["Follow-up Chat"])


# ── Health endpoint ────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    """Returns application health status."""
    return {"status": "ok", "service": "TN Property Risk Auditor"}


# ── Dev entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
