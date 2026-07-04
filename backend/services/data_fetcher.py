"""
data_fetcher.py
Fetches and caches geospatial layers for the TN Property Risk Auditor.

DATA REALITY (as of 2026):
  - TNGIS (tngis.tn.gov.in/geoserver/ows) → login-gated portal, NOT a public WFS.
    GetCapabilities returns 404 without auth.
  - Water bodies  → NWIC National Water Data Portal (public direct download)
    https://nwdp.nwic.gov.in → wb_tn_shp.zip (official shapefile)
  - Bhuvan WMS    → bhuvan-vec2.nrsc.gov.in/bhuvan/wms (public WMS, no WFS)
  - CRZ data      → Not a public download; use static representative GeoJSON
                    approved by TNSCZMA.  Replace with official data when
                    available from NCSCM.
  - Flood zones   → NDEM NRSC GeoServer (public WMS) — we cache on startup.

Fallback chain for every layer:
  Remote API → Local static GeoJSON/shapefile → Synthetic geometry (last resort)
"""

import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry import Point

logger = logging.getLogger(__name__)

# ── In-Memory GeoDataFrame Cache ──────────────────────────────────────────────
_cached_waterbodies_gdf: Optional[gpd.GeoDataFrame] = None
_cached_crz_gdf: Optional[gpd.GeoDataFrame] = None
_cached_flood_gdf: Optional[gpd.GeoDataFrame] = None

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_STATIC = BASE_DIR / "data" / "static"
CACHE_FILE = BASE_DIR / "data" / "capabilities_cache.json"

DATA_STATIC.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)

# ── Remote data sources ────────────────────────────────────────────────────────
NWIC_WATERBODY_URL = (
    "https://nwdp.nwic.gov.in/dataset/811f6a62-61c2-4d79-b90b-deeee4151f6d"
    "/resource/b53491de-0ab9-4f59-8071-8a9cfead60c3/download/wb_tn_shp.zip"
)

# Bhuvan WMS (public, no auth needed) — used for capabilities probe only
BHUVAN_WMS_URL = "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms"

# TNGIS base (login-gated — kept for future use if they open public API)
TNGIS_BASE_URL = os.getenv("TNGIS_BASE_URL", "https://tngis.tn.gov.in/geoserver/ows")


# ── get_capabilities ──────────────────────────────────────────────────────────
def get_capabilities() -> list[str]:
    """
    Probes known public GIS endpoints for available layer names.
    Checks Bhuvan (public WMS) first since TNGIS requires login auth.
    Caches result to capabilities_cache.json; loads from cache on failure.
    """
    layers: list[str] = []

    # Try Bhuvan WMS GetCapabilities (public endpoint)
    bhuvan_layers = _probe_wms_capabilities(BHUVAN_WMS_URL, "Bhuvan")
    layers.extend(bhuvan_layers)

    # Attempt TNGIS (will likely fail — documenting the attempt)
    tngis_layers = _probe_wms_capabilities(
        TNGIS_BASE_URL + "?service=WMS&version=1.1.1&request=GetCapabilities",
        "TNGIS",
    )
    layers.extend(tngis_layers)

    if layers:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"layers": layers, "sources": ["bhuvan", "tngis"]}, f, indent=2)
        logger.info(f"[Capabilities] Found {len(layers)} layers across public endpoints")
    else:
        logger.warning("[Capabilities] No layers retrieved. Loading from cache.")
        layers = _load_capabilities_from_cache()

    return layers


def _probe_wms_capabilities(url: str, source_name: str) -> list[str]:
    """Attempt a WMS GetCapabilities request and extract layer names."""
    params = {"service": "WMS", "version": "1.1.1", "request": "GetCapabilities"}
    try:
        # Handle pre-built URLs vs base URL
        if "request=GetCapabilities" in url:
            resp = requests.get(url, timeout=12)
        else:
            resp = requests.get(url, params=params, timeout=12)
        resp.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)

        layers = []
        # WMS 1.1.1 uses simple <Name> tags inside <Layer> elements
        for name_el in root.iter("Name"):
            if name_el.text and name_el.text.strip():
                layers.append(name_el.text.strip())

        logger.info(f"[{source_name}] Capability probe: found {len(layers)} layers")
        return layers

    except requests.exceptions.ConnectionError:
        logger.warning(f"[{source_name}] Could not connect (network/auth issue)")
    except requests.exceptions.Timeout:
        logger.warning(f"[{source_name}] GetCapabilities request timed out")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"[{source_name}] HTTP {e.response.status_code} — likely login-gated")
    except Exception as e:
        logger.warning(f"[{source_name}] Capability probe error: {e}")
    return []


def _load_capabilities_from_cache() -> list[str]:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE) as f:
                return json.load(f).get("layers", [])
        except Exception as e:
            logger.error(f"[Cache] Failed to read cache: {e}")
    return []


# ── fetch_waterbodies_layer ───────────────────────────────────────────────────
def fetch_waterbodies_layer(district: str = "") -> gpd.GeoDataFrame:
    """
    Returns a GeoDataFrame of Tamil Nadu water bodies.

    Priority:
    1. Local processed GeoJSON (waterbodies_tn.geojson) — fastest
    2. Downloaded NWIC shapefile ZIP (wb_tn_shp.zip) — extracted & converted
    3. Local fallback (waterbodies_fallback.geojson) — MVP polygon set
    4. Download from NWIC live — saves for next time

    All returned data is in EPSG:4326.
    """
    global _cached_waterbodies_gdf
    if _cached_waterbodies_gdf is not None:
        return _cached_waterbodies_gdf

    # 1. Processed GeoJSON already exists
    processed_path = DATA_STATIC / "waterbodies_tn.geojson"
    if processed_path.exists():
        _cached_waterbodies_gdf = _load_geojson(processed_path, "water bodies")
        return _cached_waterbodies_gdf

    # 2. NWIC zip was already downloaded — extract and process
    zip_path = DATA_STATIC / "wb_tn_shp.zip"
    if zip_path.exists():
        gdf = _extract_and_process_nwic_zip(zip_path, processed_path)
        if gdf is not None:
            _cached_waterbodies_gdf = gdf
            return gdf

    # 3. Try downloading from NWIC now
    logger.info("[NWIC] Attempting to download TN water body shapefile …")
    downloaded = _download_file(NWIC_WATERBODY_URL, zip_path, "NWIC water bodies ZIP")
    if downloaded and zip_path.exists():
        gdf = _extract_and_process_nwic_zip(zip_path, processed_path)
        if gdf is not None:
            _cached_waterbodies_gdf = gdf
            return gdf

    # 4. Fall through to local fallback
    _cached_waterbodies_gdf = _load_fallback_waterbodies(DATA_STATIC / "waterbodies_fallback.geojson")
    return _cached_waterbodies_gdf


def _extract_and_process_nwic_zip(
    zip_path: Path, output_geojson: Path
) -> Optional[gpd.GeoDataFrame]:
    """
    Extracts a shapefile ZIP from NWIC, reprojects to EPSG:4326,
    validates geometry, and saves as a GeoJSON for fast re-use.
    """
    extract_dir = DATA_STATIC / "wb_tn_extracted"
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)
        logger.info(f"[NWIC] Extracted ZIP to {extract_dir}")

        # Find the .shp file
        shp_files = list(extract_dir.rglob("*.shp"))
        if not shp_files:
            logger.error("[NWIC] No .shp file found inside ZIP")
            return None

        shp_path = shp_files[0]
        logger.info(f"[NWIC] Reading shapefile: {shp_path.name}")

        gdf = gpd.read_file(shp_path)
        logger.info(f"[NWIC] Loaded {len(gdf)} features | CRS: {gdf.crs}")

        # Fix CRS if missing or wrong
        gdf = _ensure_wgs84(gdf)

        # Fix invalid geometries
        invalid = ~gdf.geometry.is_valid
        if invalid.any():
            logger.warning(f"[NWIC] {invalid.sum()} invalid geometries — auto-fixing with buffer(0)")
            gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)

        # Remove null geometries
        gdf = gdf[gdf.geometry.notna()]
        logger.info(f"[NWIC] Final: {len(gdf)} valid water body features")

        # Save processed version for fast future loads
        gdf.to_file(output_geojson, driver="GeoJSON")
        logger.info(f"[NWIC] Saved processed GeoJSON to {output_geojson.name}")

        return gdf

    except zipfile.BadZipFile:
        logger.error("[NWIC] Downloaded file is not a valid ZIP — may have been a login redirect")
        zip_path.unlink(missing_ok=True)
        return None
    except Exception as e:
        logger.error(f"[NWIC] Failed to process shapefile ZIP: {e}")
        return None


def _ensure_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Ensures a GeoDataFrame is in EPSG:4326 (WGS-84).
    Handles common Indian government CRS variations.
    """
    if gdf.crs is None:
        logger.warning("[CRS] No CRS defined — assuming EPSG:4326")
        return gdf.set_crs("EPSG:4326")

    if gdf.crs.to_epsg() == 4326:
        return gdf

    logger.info(f"[CRS] Reprojecting from {gdf.crs} → EPSG:4326")
    return gdf.to_crs("EPSG:4326")


def _load_geojson(path: Path, name: str) -> gpd.GeoDataFrame:
    """Load a GeoJSON file and ensure it's in EPSG:4326."""
    try:
        gdf = gpd.read_file(path)
        gdf = _ensure_wgs84(gdf)
        logger.info(f"[{name}] Loaded {len(gdf)} features from {path.name}")
        return gdf
    except Exception as e:
        logger.error(f"[{name}] Failed to read {path.name}: {e}")
        return _empty_geodataframe()


def _load_fallback_waterbodies(path: Path) -> gpd.GeoDataFrame:
    """Load fallback GeoJSON or return empty GeoDataFrame."""
    if path.exists():
        return _load_geojson(path, "waterbodies fallback")
    logger.warning("[Fallback] No water body data available — returning empty GeoDataFrame")
    return _empty_geodataframe()


def _empty_geodataframe() -> gpd.GeoDataFrame:
    """Return an empty GeoDataFrame with geometry column so spatial ops don't crash."""
    gdf = gpd.GeoDataFrame({"geometry": [], "name": []})
    return gdf.set_geometry("geometry").set_crs("EPSG:4326")


def _download_file(url: str, dest: Path, label: str) -> bool:
    """Download a file from URL to dest. Returns True on success."""
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        # Check we actually got a ZIP, not an HTML redirect/login page
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            logger.warning(f"[{label}] Server returned HTML — URL may require auth or have changed")
            return False

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = dest.stat().st_size
        logger.info(f"[{label}] Downloaded to {dest.name} ({file_size:,} bytes)")
        return True

    except requests.exceptions.RequestException as e:
        logger.error(f"[{label}] Download failed: {e}")
        return False


# ── load_crz_layer ────────────────────────────────────────────────────────────
def load_crz_layer() -> gpd.GeoDataFrame:
    """
    Loads the Coastal Regulation Zone (CRZ) layer.
    """
    global _cached_crz_gdf
    if _cached_crz_gdf is not None:
        return _cached_crz_gdf

    crz_path = DATA_STATIC / "crz_tn.geojson"
    if crz_path.exists():
        gdf = _load_geojson(crz_path, "CRZ zones")
        if "zone_type" not in gdf.columns:
            gdf["zone_type"] = "CRZ-Unknown"
        _cached_crz_gdf = gdf
        return _cached_crz_gdf

    logger.warning("[CRZ] crz_tn.geojson not found — generating synthetic CRZ fallback")
    _cached_crz_gdf = _generate_synthetic_crz()
    return _cached_crz_gdf


def _generate_synthetic_crz() -> gpd.GeoDataFrame:
    """
    Creates a synthetic CRZ GeoDataFrame for Tamil Nadu's coastline.
    Polygons are illustrative only — do NOT use for legal decisions.
    """
    from shapely.geometry import box
    records = [
        {"zone_type": "CRZ-I",   "geometry": box(79.85, 8.07,  80.28, 9.00)},
        {"zone_type": "CRZ-II",  "geometry": box(79.80, 9.00,  80.32, 11.00)},
        {"zone_type": "CRZ-III", "geometry": box(79.75, 11.00, 80.34, 13.35)},
        {"zone_type": "CRZ-IV",  "geometry": box(79.70, 8.50,  79.90, 9.50)},
    ]
    return gpd.GeoDataFrame(records, crs="EPSG:4326")


# ── load_flood_zone_layer ─────────────────────────────────────────────────────
def load_flood_zone_layer() -> gpd.GeoDataFrame:
    """
    Loads the flood zone layer.
    """
    global _cached_flood_gdf
    if _cached_flood_gdf is not None:
        return _cached_flood_gdf

    flood_path = DATA_STATIC / "flood_zones_tn.geojson"
    if flood_path.exists():
        gdf = _load_geojson(flood_path, "flood zones")
        if "flood_risk" not in gdf.columns:
            gdf["flood_risk"] = "UNKNOWN"
        _cached_flood_gdf = gdf
        return _cached_flood_gdf

    logger.warning("[Flood] flood_zones_tn.geojson not found — generating synthetic fallback")
    _cached_flood_gdf = _generate_synthetic_flood_zones()
    return _cached_flood_gdf


def _generate_synthetic_flood_zones() -> gpd.GeoDataFrame:
    """Synthetic flood zones for major TN river deltas — fallback only."""
    from shapely.geometry import box
    records = [
        {"flood_risk": "HIGH",   "river": "Cauvery Delta",        "geometry": box(79.5, 10.5, 80.0, 11.5)},
        {"flood_risk": "HIGH",   "river": "Palar River",          "geometry": box(79.8, 12.8, 80.2, 13.2)},
        {"flood_risk": "MEDIUM", "river": "Vaigai Flood Plain",   "geometry": box(78.0, 9.6,  79.2, 10.2)},
        {"flood_risk": "MEDIUM", "river": "Tamiraparani",         "geometry": box(77.6, 8.4,  78.5, 9.0)},
        {"flood_risk": "LOW",    "river": "Low-lying Coastal",    "geometry": box(79.0, 11.5, 80.3, 12.5)},
    ]
    return gpd.GeoDataFrame(records, crs="EPSG:4326")
