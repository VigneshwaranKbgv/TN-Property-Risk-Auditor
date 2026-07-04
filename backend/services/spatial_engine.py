"""
spatial_engine.py
All geospatial risk evaluation logic for the TN Property Risk Auditor.
All distance calculations use EPSG:32644 (UTM Zone 44N) for metric accuracy.
"""

import logging
import math
from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry import Point

from services.data_fetcher import (
    fetch_waterbodies_layer,
    load_crz_layer,
    load_flood_zone_layer,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
CRS_WGS84 = "EPSG:4326"
CRS_UTM44N = "EPSG:32644"          # UTM Zone 44N — accurate for Tamil Nadu
BUFFER_METERS = 50                  # 50 m buffer around the property point
WATERBODY_MEDIUM_THRESHOLD_M = 100  # Within 100 m → MEDIUM risk

# Bhuvan LULC layer — Land Use Land Cover 1:50k (2015-16 survey)
BHUVAN_WMS_URL = "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms"
BHUVAN_LULC_LAYER = "lulc:TN_LULC50K_1516"

# LULC class codes that indicate elevated environmental risk
# Source: NRSC LULC classification legend
HIGH_RISK_LULC_CODES = {6, 7, 4}    # Water body, Wetland, Forest
MEDIUM_RISK_LULC_CODES = {2, 3}     # Agricultural, Plantation

LULC_CLASS_LABELS = {
    1: "Built-up",
    2: "Agricultural Land",
    3: "Plantation / Orchards",
    4: "Forest",
    5: "Scrub / Degraded Land",
    6: "Water Bodies",
    7: "Wetlands",
    8: "Barren / Rocky",
    9: "Snow / Glaciers",
}


# ── evaluate_property_risk ────────────────────────────────────────────────────
def evaluate_property_risk(lat: float, lon: float) -> dict:
    """
    Evaluates the environmental / legal risk for a property at (lat, lon).

    Args:
        lat: Latitude in WGS-84 decimal degrees.
        lon: Longitude in WGS-84 decimal degrees.

    Returns:
        A structured risk dict with water_body, crz, flood_zone, and
        overall_risk fields.
    """
    # ── 1. Create property point in WGS-84 ───────────────────────────────────
    property_point_wgs84 = Point(lon, lat)
    property_gdf_wgs84 = gpd.GeoDataFrame(
        {"geometry": [property_point_wgs84]},
        crs=CRS_WGS84,
    )

    # ── 2. Reproject property to UTM 44N for metric calculations ─────────────
    property_gdf_utm = property_gdf_wgs84.to_crs(CRS_UTM44N)
    property_point_utm = property_gdf_utm.geometry.iloc[0]
    property_buffer_utm = property_point_utm.buffer(BUFFER_METERS)

    # ── 3. Load all layers ────────────────────────────────────────────────────
    logger.info(f"[SpatialEngine] Evaluating risk for lat={lat}, lon={lon}")

    water_gdf = _safe_load_layer("waterbodies", fetch_waterbodies_layer)
    crz_gdf = _safe_load_layer("CRZ", load_crz_layer)
    flood_gdf = _safe_load_layer("flood zones", load_flood_zone_layer)

    # ── 4. Run checks ─────────────────────────────────────────────────────────
    water_result = _check_water_body(
        property_point_wgs84, property_point_utm, property_buffer_utm, water_gdf
    )
    crz_result = _check_crz(
        property_point_wgs84, property_point_utm, crz_gdf
    )
    flood_result = _check_flood_zone(property_point_wgs84, flood_gdf)
    land_use_result = _check_land_use_bhuvan(lat, lon)

    # ── 5. Determine overall risk ─────────────────────────────────────────────
    overall_risk = _compute_overall_risk(water_result, crz_result, flood_result, land_use_result)

    # ── 6. Reverse geocode location ───────────────────────────────────────────
    location_address = _reverse_geocode_osm(lat, lon)

    return {
        "coordinates": {"lat": lat, "lon": lon},
        "location_address": location_address,
        "water_body": water_result,
        "crz": crz_result,
        "flood_zone": flood_result,
        "land_use": land_use_result,
        "overall_risk": overall_risk,
    }



# ── Water body check ──────────────────────────────────────────────────────────
def _check_water_body(
    point_wgs84: Point,
    point_utm: Point,
    buffer_utm,
    water_gdf: gpd.GeoDataFrame,
) -> dict:
    """
    Checks whether the property buffer intersects any water body polygon and
    calculates distance to the nearest water body edge.
    """
    default = {
        "infringement": False,
        "distance_meters": None,
        "nearest_body_name": None,
    }

    if water_gdf is None or water_gdf.empty:
        logger.warning("[SpatialEngine] Water body layer is empty — skipping check.")
        return default

    try:
        # Reproject water layer to UTM 44N
        water_utm = water_gdf.to_crs(CRS_UTM44N)

        # Check buffer intersection (50 m buffer)
        intersects_mask = water_utm.geometry.intersects(buffer_utm)
        infringement = bool(intersects_mask.any())

        # Distance to nearest water body edge from property point
        # Guard against null/empty geometries that can appear in government shapefiles
        distances = water_utm.geometry.apply(
            lambda geom: (
                point_utm.distance(geom)
                if (geom is not None and not geom.is_empty)
                else float("inf")
            )
        )
        nearest_idx = distances.idxmin()
        min_distance_m = float(distances[nearest_idx])

        # Get nearest water body name
        nearest_name = _get_feature_name(water_gdf, nearest_idx)

        return {
            "infringement": infringement,
            "distance_meters": round(min_distance_m, 2),
            "nearest_body_name": nearest_name,
        }

    except Exception as e:
        logger.error(f"[SpatialEngine] Water body check failed: {e}")
        return default


# ── CRZ check ─────────────────────────────────────────────────────────────────
def _check_crz(
    point_wgs84: Point,
    point_utm: Point,
    crz_gdf: gpd.GeoDataFrame,
) -> dict:
    """
    Checks whether the property point falls inside any CRZ polygon and
    calculates distance to the nearest CRZ boundary.
    """
    default = {
        "inside_zone": False,
        "zone_type": None,
        "distance_to_boundary_meters": None,
    }

    if crz_gdf is None or crz_gdf.empty:
        logger.warning("[SpatialEngine] CRZ layer is empty — skipping check.")
        return default

    try:
        crz_utm = crz_gdf.to_crs(CRS_UTM44N)
        point_geom_utm = gpd.GeoDataFrame(
            {"geometry": [point_utm]}, crs=CRS_UTM44N
        )

        # Check containment — point inside any CRZ polygon
        inside_mask = crz_utm.geometry.contains(point_utm)
        inside_zone = bool(inside_mask.any())

        zone_type: Optional[str] = None
        if inside_zone:
            # Get zone_type of the first containing polygon
            containing = crz_utm[inside_mask]
            if "zone_type" in containing.columns:
                zone_type = str(containing["zone_type"].iloc[0])

        # Distance from property point to nearest CRZ polygon boundary
        distances = crz_utm.geometry.apply(
            lambda geom: point_utm.distance(geom.boundary) if geom is not None else float("inf")
        )
        min_distance_m = float(distances.min())

        return {
            "inside_zone": inside_zone,
            "zone_type": zone_type,
            "distance_to_boundary_meters": round(min_distance_m, 2),
        }

    except Exception as e:
        logger.error(f"[SpatialEngine] CRZ check failed: {e}")
        return default


# ── Flood zone check ──────────────────────────────────────────────────────────
def _check_flood_zone(
    point_wgs84: Point,
    flood_gdf: gpd.GeoDataFrame,
) -> dict:
    """
    Checks whether the property point falls inside any flood zone polygon.
    """
    default = {
        "inside_zone": False,
        "risk_level": None,
    }

    if flood_gdf is None or flood_gdf.empty:
        logger.warning("[SpatialEngine] Flood zone layer is empty — skipping check.")
        return default

    try:
        # Flood zone check uses WGS-84 (containment only, no distance calc needed)
        inside_mask = flood_gdf.geometry.contains(point_wgs84)
        inside_zone = bool(inside_mask.any())

        risk_level: Optional[str] = None
        if inside_zone:
            containing = flood_gdf[inside_mask]
            if "flood_risk" in containing.columns:
                risk_level = str(containing["flood_risk"].iloc[0])

        return {
            "inside_zone": inside_zone,
            "risk_level": risk_level,
        }

    except Exception as e:
        logger.error(f"[SpatialEngine] Flood zone check failed: {e}")
        return default


# ── Land use check via Bhuvan WMS GetFeatureInfo ──────────────────────────────
def _check_land_use_bhuvan(lat: float, lon: float) -> dict:
    """
    Queries the Bhuvan LULC 1:50k WMS via GetFeatureInfo to get the satellite-
    derived land-use classification at the property coordinates.

    This is the 5th risk dimension: "What does ISRO satellite data say this land
    is classified as?" — surfaced without any shapefile download.

    Returns:
        lulc_code:  int or None
        lulc_class: human-readable land type string
        risk_flag:  "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN"
        source:     "bhuvan" | "unavailable"
    """
    default = {
        "lulc_code": None,
        "lulc_class": "Unknown",
        "risk_flag": "UNKNOWN",
        "source": "unavailable",
    }

    # Build a tiny BBOX (0.02° x 0.02°) centred on the property point
    half = 0.01
    bbox = f"{lon - half},{lat - half},{lon + half},{lat + half}"

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": BHUVAN_LULC_LAYER,
        "QUERY_LAYERS": BHUVAN_LULC_LAYER,
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": "1",
        "X": "128",
        "Y": "128",
        "WIDTH": "256",
        "HEIGHT": "256",
        "BBOX": bbox,
        "SRS": "EPSG:4326",
    }

    try:
        resp = requests.get(BHUVAN_WMS_URL, params=params, timeout=10)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        lulc_code: Optional[int] = None
        lulc_class = "Unknown"
        risk_flag = "UNKNOWN"

        if "json" in content_type:
            data = resp.json()
            features = data.get("features", [])
            if features:
                props = features[0].get("properties", {})
                
                # Check for Bhuvan thematic LULC text descriptions
                for field in ["DESCR_2", "DESCR_1", "Class", "descr_2", "descr_1", "class"]:
                    if field in props and props[field] is not None:
                        lulc_class = str(props[field]).strip()
                        break
                
                # Check for numeric code
                for field in ["LU_Webcode", "lu_webcode", "DN", "GRIDCODE", "code", "VALUE"]:
                    if field in props and props[field] is not None:
                        try:
                            lulc_code = int(props[field])
                        except (ValueError, TypeError):
                            pass
                        break

        elif "text" in content_type or "html" in content_type:
            # Some GeoServer versions return GML/text — parse with regex
            import re
            match = re.search(r'(?:DN|GRIDCODE|Class|VALUE)\s*=\s*(\d+)', resp.text)
            if match:
                lulc_code = int(match.group(1))

        # Determine risk flag based on parsed description text or code
        desc_lower = lulc_class.lower()
        if any(x in desc_lower for x in ["water", "wetland", "forest", "lake", "pond", "river", "marsh"]):
            risk_flag = "HIGH"
        elif any(x in desc_lower for x in ["agri", "plant", "crop", "orchard", "culti"]):
            risk_flag = "MEDIUM"
        elif lulc_class != "Unknown":
            risk_flag = "LOW"
        elif lulc_code is not None:
            # Fallback to LULC code mapping
            if lulc_code in HIGH_RISK_LULC_CODES:
                risk_flag = "HIGH"
            elif lulc_code in MEDIUM_RISK_LULC_CODES:
                risk_flag = "MEDIUM"
            else:
                risk_flag = "LOW"

        if lulc_class != "Unknown" or lulc_code is not None:
            if lulc_class == "Unknown" and lulc_code is not None:
                lulc_class = LULC_CLASS_LABELS.get(lulc_code, f"Code {lulc_code}")

            logger.info(
                f"[Bhuvan] LULC at ({lat},{lon}): class={lulc_class} "
                f"(code={lulc_code}) → {risk_flag}"
            )
            return {
                "lulc_code": lulc_code,
                "lulc_class": lulc_class,
                "risk_flag": risk_flag,
                "source": "bhuvan",
            }

        logger.info(f"[Bhuvan] No LULC feature returned for ({lat},{lon})")
        return default


    except requests.exceptions.Timeout:
        logger.warning("[Bhuvan] GetFeatureInfo timed out")
        return default
    except requests.exceptions.RequestException as e:
        logger.warning(f"[Bhuvan] GetFeatureInfo failed: {e}")
        return default
    except Exception as e:
        logger.error(f"[Bhuvan] Unexpected error in land use check: {e}")
        return default


# ── Overall risk computation ───────────────────────────────────────────────────
def _compute_overall_risk(
    water: dict,
    crz: dict,
    flood: dict,
    land_use: Optional[dict] = None,
) -> str:
    """
    Determines the overall risk level across all 5 dimensions.

    HIGH  : Water buffer infringement, CRZ-I, HIGH flood zone,
            or LULC classified as water body / wetland / forest
    MEDIUM: Within 100m water body, CRZ-II/III, MEDIUM flood zone,
            or LULC classified as agricultural / plantation
    LOW   : All clear
    """
    # HIGH conditions
    if water.get("infringement"):
        return "HIGH"
    if crz.get("inside_zone") and crz.get("zone_type") in ("CRZ-I", "CRZ-Unknown"):
        return "HIGH"
    if flood.get("inside_zone") and flood.get("risk_level") == "HIGH":
        return "HIGH"
    if land_use and land_use.get("risk_flag") == "HIGH":
        return "HIGH"

    # MEDIUM conditions
    water_dist = water.get("distance_meters")
    if water_dist is not None and water_dist <= WATERBODY_MEDIUM_THRESHOLD_M:
        return "MEDIUM"
    if crz.get("inside_zone") and crz.get("zone_type") in ("CRZ-II", "CRZ-III"):
        return "MEDIUM"
    if flood.get("inside_zone") and flood.get("risk_level") == "MEDIUM":
        return "MEDIUM"
    if land_use and land_use.get("risk_flag") == "MEDIUM":
        return "MEDIUM"

    return "LOW"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _safe_load_layer(layer_name: str, loader_fn) -> Optional[gpd.GeoDataFrame]:
    """Wraps a layer loader in try/except and returns None on failure."""
    try:
        return loader_fn()
    except Exception as e:
        logger.error(f"[SpatialEngine] Failed to load {layer_name} layer: {e}")
        return None


def _get_feature_name(gdf: gpd.GeoDataFrame, idx) -> Optional[str]:
    """
    Tries to extract a human-readable name from a GeoDataFrame row.
    Checks NWIC column names first (OBJNAM, WB_NAME), then common variants.
    """
    # NWIC shapefile uses OBJNAM or WB_NAME; government files often use OBJNAM
    name_columns = [
        "wetname", "WETNAME",          # NWIC wb_sac_tn.shp primary name column
        "OBJNAM", "WB_NAME", "wb_name", "NAME", "name", "Name",
        "WBNAME", "body_name", "layer_name", "feature_name", "DISTRICT",
    ]
    for col in name_columns:
        if col in gdf.columns:
            val = gdf.at[idx, col]
            str_val = str(val).strip()
            if str_val.lower() not in ("nan", "none", "", "null"):
                return str_val
    return "Unnamed water body"


def _reverse_geocode_osm(lat: float, lon: float) -> str:
    """
    Reverse geocodes coordinates using OpenStreetMap Nominatim API.
    Always includes a try/except guard and returns 'Unknown Location' on failure.
    """
    url = "https://nominatim.openstreetmap.org/reverse"
    headers = {
        "User-Agent": "TN-Property-Risk-Auditor/1.0 (contact: support@tn-risk-auditor.gov)"
    }
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": 14,  # City/town/village level description
        "addressdetails": 1
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            address = data.get("address", {})
            parts = []
            
            # Select key address fields for a clean name description
            for key in ["village", "suburb", "town", "city", "county", "state"]:
                if key in address:
                    parts.append(address[key])
                    
            if parts:
                return ", ".join(parts)
            return data.get("display_name", "Unknown Location")
    except Exception as e:
        logger.warning(f"[ReverseGeocode] Failed to reverse geocode coordinate ({lat}, {lon}): {e}")
        
    return "Unknown Location"
