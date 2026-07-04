"""
validate_geodata.py
Quick validation script to check all spatial data layers before running the server.
Run: python validate_geodata.py
"""

import sys
import io

# Force UTF-8 stdout on Windows to avoid cp1252 encode errors
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import zipfile
from pathlib import Path

DATA_STATIC = Path("data/static")


def check(label, condition, detail=""):
    status = "[OK]  " if condition else "[FAIL]"
    print(f"  {status} {label}")
    if detail:
        print(f"         {detail}")
    return condition

print("=" * 60)
print("  TN Property Risk Auditor — Data Validation")
print("=" * 60)

all_ok = True

# ── 1. Check dependencies importable ─────────────────────────────────────────
print("\n[1] Python dependencies")
try:
    import geopandas as gpd
    import shapely
    import pyproj
    check("geopandas", True, f"v{gpd.__version__}")
    check("shapely", True, f"v{shapely.__version__}")
    check("pyproj", True, f"v{pyproj.__version__}")
except ImportError as e:
    all_ok = False
    check("Dependencies", False, str(e))
    print("\nRun: pip install -r requirements.txt")
    sys.exit(1)

# ── 2. Check static files ─────────────────────────────────────────────────────
print("\n[2] Static data files")
crz_path   = DATA_STATIC / "crz_tn.geojson"
flood_path = DATA_STATIC / "flood_zones_tn.geojson"
wb_zip     = DATA_STATIC / "wb_tn_shp.zip"
wb_geojson = DATA_STATIC / "waterbodies_tn.geojson"
wb_fallback= DATA_STATIC / "waterbodies_fallback.geojson"

check("crz_tn.geojson",            crz_path.exists())
check("flood_zones_tn.geojson",    flood_path.exists())
check("wb_tn_shp.zip (NWIC)",      wb_zip.exists(),
      f"Size: {wb_zip.stat().st_size/1e6:.1f} MB" if wb_zip.exists() else "Not downloaded")
check("waterbodies_tn.geojson",    wb_geojson.exists(), "(pre-processed, speeds up startup)")
check("waterbodies_fallback.geojson", wb_fallback.exists())

# ── 3. Validate CRZ GeoJSON ───────────────────────────────────────────────────
print("\n[3] CRZ Layer Validation")
if crz_path.exists():
    gdf = gpd.read_file(crz_path)
    check("Can be read by GeoPandas", True)
    check(f"CRS defined", gdf.crs is not None, str(gdf.crs) if gdf.crs else "MISSING")
    check("Is WGS-84 (EPSG:4326)", gdf.crs and gdf.crs.to_epsg() == 4326)
    check(f"Feature count > 0", len(gdf) > 0, f"{len(gdf)} features")
    check("Has zone_type column", "zone_type" in gdf.columns,
          f"Columns: {list(gdf.columns)[:5]}")
    check("All geometries valid", gdf.geometry.is_valid.all(),
          f"{(~gdf.geometry.is_valid).sum()} invalid")
    if not gdf.empty:
        print(f"       Zone types: {gdf['zone_type'].unique().tolist() if 'zone_type' in gdf.columns else 'N/A'}")
else:
    all_ok = False
    check("CRZ file readable", False, "File missing")

# ── 4. Validate Flood Zone GeoJSON ────────────────────────────────────────────
print("\n[4] Flood Zone Layer Validation")
if flood_path.exists():
    gdf = gpd.read_file(flood_path)
    check("Can be read by GeoPandas", True)
    check("CRS defined", gdf.crs is not None, str(gdf.crs) if gdf.crs else "MISSING")
    check("Is WGS-84 (EPSG:4326)", gdf.crs and gdf.crs.to_epsg() == 4326)
    check(f"Feature count > 0", len(gdf) > 0, f"{len(gdf)} features")
    check("Has flood_risk column", "flood_risk" in gdf.columns,
          f"Columns: {list(gdf.columns)[:5]}")
    check("All geometries valid", gdf.geometry.is_valid.all())
else:
    all_ok = False
    check("Flood file readable", False, "File missing")

# ── 5. Validate NWIC Water Body ZIP ───────────────────────────────────────────
print("\n[5] NWIC Water Body Shapefile Validation")
if wb_zip.exists():
    try:
        with zipfile.ZipFile(wb_zip) as z:
            names = z.namelist()
        shp_files = [n for n in names if n.endswith(".shp")]
        check("ZIP is valid",      True)
        check("Contains .shp",    bool(shp_files), str(shp_files[:2]))

        if shp_files:
            extract_dir = DATA_STATIC / "wb_tn_extracted"
            if not extract_dir.exists():
                print("       Extracting ZIP …")
                with zipfile.ZipFile(wb_zip) as z:
                    z.extractall(extract_dir)

            shp_path = next(Path(extract_dir).rglob("*.shp"))
            gdf = gpd.read_file(shp_path)
            print(f"       Raw CRS: {gdf.crs}")
            print(f"       Feature count: {len(gdf):,}")
            print(f"       Columns: {list(gdf.columns)[:8]}")
            check("Feature count > 0", len(gdf) > 0)
            check("Geometry column present", gdf.geometry is not None)

            # Reproject and validate
            if gdf.crs and gdf.crs.to_epsg() != 4326:
                print(f"       Reprojecting {gdf.crs} → EPSG:4326 …")
                gdf = gdf.to_crs("EPSG:4326")
            elif gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")

            check("After reproject: WGS-84", gdf.crs.to_epsg() == 4326)
            valid_count = gdf.geometry.is_valid.sum()
            check(f"Valid geometries", valid_count == len(gdf),
                  f"{valid_count:,}/{len(gdf):,} valid")

            # Sample spatial test — point near Chennai
            from shapely.geometry import Point
            chennai = Point(80.2707, 13.0827)
            distances = gdf.geometry.apply(lambda g: chennai.distance(g) if g else float("inf"))
            nearest_dist_deg = distances.min()
            nearest_idx = distances.idxmin()
            name_col = next((c for c in ["NAME", "name", "wb_name", "WB_NAME", "OBJNAM"] if c in gdf.columns), None)
            nearest_name = str(gdf.iloc[nearest_idx][name_col]) if name_col else "N/A"
            print(f"\n       Sample: Nearest water body to Chennai (80.27,13.08):")
            print(f"         Name: {nearest_name}")
            print(f"         Distance: {nearest_dist_deg:.4f}° (~{nearest_dist_deg*111:.1f} km)")

    except zipfile.BadZipFile:
        all_ok = False
        check("ZIP is valid", False, "Corrupt or HTML redirect — re-download needed")
    except Exception as e:
        all_ok = False
        check("ZIP processing", False, str(e))
elif wb_geojson.exists():
    gdf = gpd.read_file(wb_geojson)
    check("Pre-processed GeoJSON loaded", True, f"{len(gdf):,} features")
else:
    all_ok = False
    check("NWIC water body data", False, "Neither ZIP nor processed GeoJSON found")

# ── 6. Spatial test: Chennai Marina ──────────────────────────────────────────
print("\n[6] Spatial Engine Sanity Check")
try:
    import sys
    sys.path.insert(0, str(Path(".").resolve()))
    from services.spatial_engine import evaluate_property_risk

    # Marina Beach, Chennai — should be near CRZ
    result = evaluate_property_risk(lat=13.0500, lon=80.2824)
    check("spatial_engine runs without crash", True)
    check("Returns overall_risk key", "overall_risk" in result, result.get("overall_risk"))
    check("Returns water_body key", "water_body" in result)
    check("Returns crz key", "crz" in result)
    check("Returns flood_zone key", "flood_zone" in result)
    print(f"\n       Results for Chennai Marina (13.05°N, 80.28°E):")
    print(f"         Overall Risk:  {result['overall_risk']}")
    print(f"         CRZ Inside:    {result['crz']['inside_zone']} (type: {result['crz']['zone_type']})")
    print(f"         Flood Zone:    {result['flood_zone']['inside_zone']} (risk: {result['flood_zone']['risk_level']})")
    wb = result['water_body']
    print(f"         Water Body:    {wb['distance_meters']:.1f} m to '{wb['nearest_body_name']}'")
    print(f"                        Infringement: {wb['infringement']}")
except Exception as e:
    all_ok = False
    check("Spatial engine test", False, str(e))

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if all_ok:
    print("  ✓  All checks passed — backend data is ready")
else:
    print("  ✗  Some checks failed — review output above")
print("=" * 60)
