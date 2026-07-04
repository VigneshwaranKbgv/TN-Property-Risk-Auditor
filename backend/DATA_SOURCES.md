# Data Source Reality — TN Property Risk Auditor

This document records the **actual state of each data source** as verified
during development. Read this before debugging data issues.

---

## TNGIS (tngis.tn.gov.in)

**Status: Login-gated — NOT a public WFS**

```
GET https://tngis.tn.gov.in → HTTP 200 (login portal page)
GET https://tngis.tn.gov.in/geoserver/ows → HTTP 404
```

The TNGIS portal exists and has a GeoServer backend, but the public WFS/WMS
endpoint requires authenticated access. The `get_capabilities()` function will
fail gracefully and log a warning. Do not treat this as a bug.

**If you gain official access:** Add session tokens / Basic Auth to the
`requests.get()` calls in `data_fetcher.py`.

---

## Water Bodies — NWIC (National Water Informatics Centre)

**Status: ✅ Public direct download — WORKING**

```
URL: https://nwdp.nwic.gov.in/dataset/811f6a62-61c2-4d79-b90b-deeee4151f6d
     /resource/b53491de-0ab9-4f59-8071-8a9cfead60c3/download/wb_tn_shp.zip
Size: ~83 MB (real shapefile, not HTML)
```

The ZIP is downloaded to `data/static/wb_tn_shp.zip` and auto-extracted on
first run. The processed GeoJSON is cached at `data/static/waterbodies_tn.geojson`.

**CRS verification needed** — government shapefiles may be in a non-WGS84 CRS.
Run `validate_geodata.py` to check and fix automatically.

---

## CRZ (Coastal Regulation Zone)

**Status: ⚠️ Not publicly downloadable as vector data**

Official CRZ shapefiles (from NCSCM/TNSCZMA) are restricted to government use.
Our `crz_tn.geojson` is a **representative dataset** based on the CRZ 2011 and
CRZ 2019 notification maps.

**Honest framing for interviews / README:**
> *"Official CRZ vectors are restricted to government use. The system uses
> representative boundaries drawn from published CRZ 2011/2019 notification
> maps, and explicitly flags users to verify with CMDA for Chennai-specific
> plots. The architecture is designed to swap in official data the moment it
> becomes available — the `load_crz_layer()` function reads from a single
> GeoJSON file, so replacing it requires no code changes."*

**For production-grade accuracy:**
1. Contact NCSCM directly: https://www.ncscm.res.in/
2. File RTI with TNSCZMA (Tamil Nadu State Coastal Zone Management Authority)
   under the Environment, Climate Change and Forests Department
3. Use CMDA's online property check: https://www.cmda.tn.gov.in for
   individual plot verification in Chennai district

---

## Flood Zones — TNSDMA / NDEM

**Status: ⚠️ Broad zones only — no public WFS vector download**

Our `flood_zones_tn.geojson` is based on:
- NDMA National Flood Hazard Atlas (river basin level)
- TNSDMA flood inundation historical records

**For hyper-local accuracy**, use the Bhuvan NDEM annual flood maps:
- Portal: https://ndem.nrsc.gov.in
- WMS: `https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms`
- These are raster layers (not vector), good for visual overlay but not
  for programmatic containment checks.

---

## Bhuvan WMS (ISRO NRSC)

**Status: ✅ Public WMS — raster tiles + per-point GetFeatureInfo queryable**

```
Base URL: https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms
```

### What you CAN do with Bhuvan even without WFS

**1. Leaflet tile overlay (visual context)**

Add as a WMS tile layer in `MapView.jsx` so users see land-use context:

```js
L.tileLayer.wms("https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms", {
  layers: "lulc50k_1516",   // Land Use Land Cover 1:50k (2015–16)
  format: "image/png",
  transparent: true,
  attribution: "NRSC/ISRO Bhuvan",
  opacity: 0.4,
}).addTo(map);
```

**2. GetFeatureInfo — land use classification per coordinate (4th risk dimension)**

This IS queryable per-point without WFS. It returns whether a location is
classified as agricultural land, wetland, built-up, forest, or water body.
No existing property app surfaces this data point.

```
GET https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms
  ?SERVICE=WMS
  &VERSION=1.1.1
  &REQUEST=GetFeatureInfo
  &LAYERS=lulc50k_1516
  &QUERY_LAYERS=lulc50k_1516
  &INFO_FORMAT=application/json
  &FEATURE_COUNT=1
  &X=128&Y=128&WIDTH=256&HEIGHT=256
  &BBOX={lon-0.01},{lat-0.01},{lon+0.01},{lat+0.01}
  &SRS=EPSG:4326
```

Key `lulc50k_1516` class codes relevant to property risk:

| Code | Class                | Risk Implication                          |
|------|----------------------|-------------------------------------------|
| 6    | Water bodies         | High — construction restricted            |
| 7    | Wetlands             | High — CRZ-I / eco-sensitive likely       |
| 2    | Agricultural land    | Medium — conversion restrictions apply   |
| 5    | Scrub / degraded     | Low — usually buildable                  |
| 4    | Forest               | High — Forest Conservation Act applies   |
| 1    | Built-up             | Low — already urbanised                  |

**Implementation:** Add `check_land_use_bhuvan(lat, lon)` to `spatial_engine.py`
and a new `land_use` key to the risk response. This gives a **5th independent
risk signal** without requiring any shapefile download.

**Other useful Bhuvan layers:**
- `india_flood_17` — Flood inundation extent (varies by year suffix)
- `urban_extent_2011` — Urban boundary for FSI zone determination
- `coast_tn` — Coastal layer if available in GetCapabilities

---

## CRS Notes for Indian Government Data

Most government shapefiles are published in one of:
- `EPSG:4326` — WGS-84 (correct, no conversion needed)
- `EPSG:7755` — GRS 1980 / India - NSF LCC (convert with `to_crs("EPSG:4326")`)
- `EPSG:32643` — UTM Zone 43N (parts of western TN)
- `EPSG:32644` — UTM Zone 44N (most of TN — what we use for calculations)
- `EPSG:24344` — Indian 1975 / UTM Zone 44N (old Survey of India)

`validate_geodata.py` handles auto-detection and reprojection.

---

## Quick Data Refresh Commands

```powershell
# Re-download NWIC water body shapefile
Remove-Item "data/static/wb_tn_shp.zip" -Force
Remove-Item "data/static/waterbodies_tn.geojson" -Force
Remove-Item "data/static/wb_tn_extracted" -Recurse -Force
# Then restart the backend — it auto-downloads on startup

# Run full data validation
.\venv\Scripts\python validate_geodata.py
```
