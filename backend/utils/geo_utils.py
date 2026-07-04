"""
geo_utils.py
CRS conversion helpers, bounding box utilities, and coordinate validation
for the TN Property Risk Auditor.
"""

from typing import Tuple

import geopandas as gpd
from shapely.geometry import Point, box


# ── Tamil Nadu bounding box ───────────────────────────────────────────────────
TN_BOUNDS = {
    "lat_min": 8.0,
    "lat_max": 13.6,
    "lon_min": 76.2,
    "lon_max": 80.4,
}

CRS_WGS84 = "EPSG:4326"
CRS_UTM44N = "EPSG:32644"


def is_within_tamil_nadu(lat: float, lon: float) -> bool:
    """
    Returns True if the given lat/lon falls within the Tamil Nadu bounding box.

    Args:
        lat: Latitude in decimal degrees (WGS-84).
        lon: Longitude in decimal degrees (WGS-84).

    Returns:
        True if within TN bounds, False otherwise.
    """
    return (
        TN_BOUNDS["lat_min"] <= lat <= TN_BOUNDS["lat_max"]
        and TN_BOUNDS["lon_min"] <= lon <= TN_BOUNDS["lon_max"]
    )


def latlon_to_point_wgs84(lat: float, lon: float) -> Point:
    """Create a Shapely Point in WGS-84 from lat/lon."""
    return Point(lon, lat)   # Shapely uses (x=lon, y=lat) convention


def latlon_to_utm(lat: float, lon: float) -> Tuple[float, float]:
    """
    Convert WGS-84 lat/lon to UTM Zone 44N (EPSG:32644) easting/northing.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.

    Returns:
        (easting, northing) in metres.
    """
    gdf = gpd.GeoDataFrame(
        {"geometry": [Point(lon, lat)]},
        crs=CRS_WGS84,
    )
    gdf_utm = gdf.to_crs(CRS_UTM44N)
    geom = gdf_utm.geometry.iloc[0]
    return geom.x, geom.y


def reproject_gdf(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    """
    Reproject a GeoDataFrame to the given CRS.

    Args:
        gdf:        Input GeoDataFrame (must have a defined CRS).
        target_crs: Target CRS string (e.g. 'EPSG:32644').

    Returns:
        Reprojected GeoDataFrame.
    """
    if gdf is None or gdf.empty:
        return gdf
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_WGS84)
    return gdf.to_crs(target_crs)


def tn_bounding_box_wgs84():
    """Return the Tamil Nadu bounding box as a Shapely polygon (WGS-84)."""
    return box(
        TN_BOUNDS["lon_min"],
        TN_BOUNDS["lat_min"],
        TN_BOUNDS["lon_max"],
        TN_BOUNDS["lat_max"],
    )


def buffer_point_utm(lat: float, lon: float, radius_m: float):
    """
    Create a circular buffer around a point in UTM coordinates.

    Args:
        lat:      Latitude in decimal degrees.
        lon:      Longitude in decimal degrees.
        radius_m: Buffer radius in metres.

    Returns:
        Shapely Polygon (in EPSG:32644 coordinates).
    """
    easting, northing = latlon_to_utm(lat, lon)
    return Point(easting, northing).buffer(radius_m)


def format_distance(metres: float) -> str:
    """Human-readable distance string (metres or kilometres)."""
    if metres is None:
        return "Unknown"
    if metres < 1000:
        return f"{metres:.0f} m"
    return f"{metres / 1000:.2f} km"
