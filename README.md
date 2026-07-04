# TN Property Risk Auditor

> A civic tool that lets a homebuyer check if a property in Tamil Nadu sits inside environmentally restricted zones (CRZ, flood zones, protected water bodies) using Tamil Nadu's public GIS infrastructure and NVIDIA NIM LLMs.

---

## Tech Stack

| Layer    | Technology                                      |
|----------|-------------------------------------------------|
| Backend  | Python 3.11, FastAPI, GeoPandas, Shapely        |
| Frontend | React + Vite, Leaflet.js, TailwindCSS           |
| LLM      | NVIDIA NIM API (DeepSeek R1 / Phi-4-mini)       |
| Data     | TNGIS WFS, Static GeoJSON fallbacks             |

---

## Project Structure

```
tn-property-risk/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── routers/
│   │   ├── risk.py              # POST /api/risk
│   │   └── chat.py              # POST /api/chat (SSE streaming)
│   ├── services/
│   │   ├── spatial_engine.py    # Geospatial risk evaluation (EPSG:32644)
│   │   ├── data_fetcher.py      # TNGIS WFS + static GeoJSON loaders
│   │   └── llm_service.py       # NVIDIA NIM model routing + generation
│   ├── data/static/             # GeoJSON files (CRZ, flood zones, water bodies)
│   ├── utils/geo_utils.py       # CRS conversion, bounding box helpers
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Root component (map + slide-in report)
│   │   ├── components/
│   │   │   ├── MapView.jsx      # Leaflet map, pin drop, loading overlay
│   │   │   ├── RiskReport.jsx   # Slide-in panel + PDF export
│   │   │   ├── RiskBadge.jsx    # HIGH/MEDIUM/LOW colour badge
│   │   │   └── ChatPanel.jsx    # Follow-up AI Q&A with SSE streaming
│   │   └── api/client.js        # Axios + fetch API helpers
│   └── index.html
└── README.md
```

---

## Setup & Running

### 1. Backend

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env and add your NVIDIA_API_KEY

# Run the backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

The frontend will be available at **http://localhost:5173**

---

## API Endpoints

### `POST /api/risk`
Evaluates environmental risk for a property.

**Request:**
```json
{ "lat": 13.0827, "lon": 80.2707 }
```

**Response:**
```json
{
  "risk_metrics": {
    "coordinates": {"lat": 13.0827, "lon": 80.2707},
    "water_body": {
      "infringement": false,
      "distance_meters": 1240.5,
      "nearest_body_name": "Chembarambakkam Lake"
    },
    "crz": {
      "inside_zone": false,
      "zone_type": null,
      "distance_to_boundary_meters": 3200.0
    },
    "flood_zone": {
      "inside_zone": false,
      "risk_level": null
    },
    "overall_risk": "LOW"
  },
  "report": "This property appears to be in a safe location...",
  "overall_risk": "LOW"
}
```

### `POST /api/chat`
Streams an AI follow-up answer (Server-Sent Events).

**Request:**
```json
{
  "question": "What does CRZ-II mean for building?",
  "risk_metrics": { ... },
  "history": []
}
```

### `GET /health`
Returns `{"status": "ok"}`.

---

## Test with curl

```bash
# Health check
curl http://localhost:8000/health

# Risk assessment — Chennai Marina area (near coast, CRZ zone)
curl -X POST http://localhost:8000/api/risk \
  -H "Content-Type: application/json" \
  -d '{"lat": 13.0500, "lon": 80.2824}'

# Risk assessment — Inland Coimbatore (should be LOW risk)
curl -X POST http://localhost:8000/api/risk \
  -H "Content-Type: application/json" \
  -d '{"lat": 11.0168, "lon": 76.9558}'

# Risk assessment — Cauvery Delta (HIGH flood risk)
curl -X POST http://localhost:8000/api/risk \
  -H "Content-Type: application/json" \
  -d '{"lat": 10.9, "lon": 79.8}'

# Out-of-bounds check (should return 422)
curl -X POST http://localhost:8000/api/risk \
  -H "Content-Type: application/json" \
  -d '{"lat": 28.6139, "lon": 77.2090}'
```

---

## Risk Logic

| Condition                                  | Risk Level |
|--------------------------------------------|------------|
| Water body buffer (50 m) infringement      | **HIGH**   |
| Inside CRZ-I zone                          | **HIGH**   |
| Inside HIGH flood zone                     | **HIGH**   |
| Within 100 m of water body                 | **MEDIUM** |
| Inside CRZ-II or CRZ-III zone              | **MEDIUM** |
| Inside MEDIUM flood zone                   | **MEDIUM** |
| All clear                                  | **LOW**    |

---

## LLM Model Routing

| Scenario            | Model Used                             |
|---------------------|----------------------------------------|
| HIGH risk detected  | `deepseek-ai/deepseek-r1` (deep legal reasoning) |
| MEDIUM / LOW risk   | `microsoft/phi-4-mini-instruct` (fast) |
| All follow-up Q&A   | `microsoft/phi-4-mini-instruct`        |

---

## Environment Variables

### Backend (`backend/.env`)
```env
NVIDIA_API_KEY=nvapi-your-key-here
TNGIS_BASE_URL=https://tngis.tn.gov.in/geoserver/ows
CORS_ORIGIN=http://localhost:5173
```

### Frontend (`frontend/.env`)
```env
VITE_API_URL=http://localhost:8000
```

---

## Data Sources

- **TNGIS WFS**: Tamil Nadu Geographic Information System — `https://tngis.tn.gov.in/geoserver/ows`
- **CRZ Data**: Coastal Regulation Zone boundaries (static GeoJSON, sourced from MoEFCC notifications)
- **Flood Zones**: Major river delta and plain flood zones (Tamil Nadu SDMA data)
- **Water Bodies**: TNGIS `wrd_water_bodies` layer with local fallback

> **Disclaimer**: The static GeoJSON files included are representative/illustrative data for development. For production use, obtain official data from TNGIS, TNCZMA, and TNSDMA.

---

## Features

- 🗺 **Dark-mode Leaflet map** centered on Tamil Nadu
- 📍 **Pin-drop interface** — click to select any property location
- 🧠 **NVIDIA NIM AI** — DeepSeek R1 for HIGH risk, Phi-4-mini for routine analysis
- 💧 **Water body check** — 50 m buffer + distance to nearest body (UTM accurate)
- 🌊 **CRZ zone detection** — CRZ-I through CRZ-IV with regulatory notes
- 🌧 **Flood zone classification** — HIGH/MEDIUM/LOW flood risk
- 💬 **Follow-up AI chat** — streamed word-by-word via SSE
- 📄 **PDF report download** — jsPDF-generated one-pager
- 📋 **Query audit log** — coordinate-only logging to `queries.log`
