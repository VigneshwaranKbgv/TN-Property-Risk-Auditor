import { useState, useCallback, useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMapEvents,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { assessRisk } from "../api/client";

// Fix Leaflet's broken default icon paths in Vite
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// ── Map Tile Layers Configuration ─────────────────────────────────────────────
const TILE_LAYERS = {
  satellite: {
    name: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
    subdomains: "abc"
  },
  dark: {
    name: "Dark Mode",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd"
  },
  light: {
    name: "Light Mode",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd"
  }
};


// ── Custom resizer hook component ────────────────────────────────────────────
function MapResizer({ reportOpen }) {
  const map = useMap();
  useEffect(() => {
    const timer = setTimeout(() => {
      map.invalidateSize({ animate: true });
    }, 310); // Wait for the 300ms CSS panel transition to finish
    return () => clearTimeout(timer);
  }, [reportOpen, map]);
  return null;
}


// Custom coloured pin icons
const createIcon = (color) =>
  new L.DivIcon({
    className: "",
    html: `
      <div style="
        width: 28px; height: 28px;
        background: ${color};
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        border: 3px solid white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4);
      "></div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 28],
    popupAnchor: [0, -28],
  });

const PIN_COLORS = {
  HIGH: "#ef4444",
  MEDIUM: "#f59e0b",
  LOW: "#10b981",
  DEFAULT: "#6366f1",
};

// ── Inner click handler (must be inside MapContainer) ─────────────────────────
function MapClickHandler({ onMapClick }) {
  useMapEvents({ click: (e) => onMapClick(e.latlng) });
  return null;
}

// ── Main MapView ──────────────────────────────────────────────────────────────
export default function MapView({ onRiskData, reportOpen, onClearPin }) {
  const [pin, setPin] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [pinRisk, setPinRisk] = useState("DEFAULT");
  const [activeTile, setActiveTile] = useState("satellite");

  const handleMapClick = useCallback(({ lat, lng }) => {
    setPin({ lat, lng });
    setError(null);
    setPinRisk("DEFAULT");
  }, []);

  const handleCheckRisk = async () => {
    if (!pin) return;
    setLoading(true);
    setError(null);

    try {
      const data = await assessRisk(pin.lat, pin.lng);
      setPinRisk(data.overall_risk || "LOW");
      onRiskData(data);
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to assess risk. Please try again.";
      setError(msg);
      setPinRisk("DEFAULT");
    } finally {
      setLoading(false);
    }
  };

  const pinIcon = createIcon(PIN_COLORS[pinRisk] || PIN_COLORS.DEFAULT);

  return (
    <div className="relative w-full h-full">
      {/* ── Map ─────────────────────────────────────────────────────────────── */}
      <MapContainer
        center={[11.0, 78.5]}   // Tamil Nadu center
        zoom={7}
        className="w-full h-full"
        style={{ background: "#0f172a" }}
        zoomControl={false}
      >
        <MapResizer reportOpen={reportOpen} />

        {/* Dynamic tile layer based on active switcher selection */}
        <TileLayer
          key={activeTile}
          attribution={TILE_LAYERS[activeTile].attribution}
          url={TILE_LAYERS[activeTile].url}
          subdomains={TILE_LAYERS[activeTile].subdomains}
          maxZoom={19}
        />

        {/* Zoom controls on right side */}
        <MapClickHandler onMapClick={handleMapClick} />

        {/* Dropped pin */}
        {pin && (
          <Marker position={[pin.lat, pin.lng]} icon={pinIcon}>
            <Popup className="custom-popup">
              <div className="text-xs text-slate-700 font-mono">
                <div className="font-bold text-slate-900 mb-1">📍 Selected Location</div>
                <div>Lat: {pin.lat.toFixed(6)}°N</div>
                <div>Lon: {pin.lng.toFixed(6)}°E</div>
              </div>
            </Popup>
          </Marker>
        )}
      </MapContainer>


      {/* ── Overlay UI ──────────────────────────────────────────────────────── */}

      {/* Header Banner */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[4000] pointer-events-none">
        <div className="bg-slate-900/90 backdrop-blur-xl px-5 py-2.5 rounded-2xl border border-slate-700/50 shadow-2xl flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-white font-bold text-sm tracking-tight">
            TN Property Risk Auditor
          </span>
          <span className="text-slate-400 text-xs hidden sm:block">
            Click anywhere on the map to check a property
          </span>
        </div>
      </div>

      {/* Instructions (shown when no pin) */}
      {!pin && !loading && (
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-[4000] pointer-events-none">
          <div className="bg-slate-900/80 backdrop-blur-lg px-4 py-2 rounded-xl border border-slate-700/40 text-slate-300 text-sm text-center">
            🗺 Click anywhere in Tamil Nadu to drop a pin
          </div>
        </div>
      )}

      {/* Pin info + Check button.
          On mobile the report panel covers the whole screen when open, so
          this card would otherwise float uselessly on top of it — hide it
          there and only show the side-by-side version on sm+ screens. */}
      {pin && !loading && (
        <div
          className={`
            absolute bottom-6 z-[4000]
            transition-all duration-300
            ${reportOpen ? "hidden sm:block left-4" : "left-1/2 -translate-x-1/2"}
          `}
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          onMouseUp={(e) => e.stopPropagation()}
          onDoubleClick={(e) => e.stopPropagation()}
        >
          <div className="bg-slate-900/95 backdrop-blur-xl rounded-2xl border border-slate-700/50 shadow-2xl p-4 min-w-64">
            {/* Coordinates */}
            <div className="flex items-start gap-3 mb-3">
              <div
                className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-white text-xs font-bold shadow-lg"
                style={{ background: PIN_COLORS[pinRisk] }}
              >
                📍
              </div>
              <div>
                <div className="text-white text-sm font-semibold">Selected Location</div>
                <div className="text-slate-400 text-xs font-mono mt-0.5">
                  {pin.lat.toFixed(6)}°N, {pin.lng.toFixed(6)}°E
                </div>
              </div>
            </div>

            {/* Error message */}
            {error && (
              <div className="mb-3 p-2 bg-red-900/40 border border-red-700/40 rounded-lg text-red-300 text-xs">
                ⚠ {error}
              </div>
            )}

            {/* Action buttons */}
            <div className="flex gap-2">
              <button
                id="check-property-btn"
                onClick={handleCheckRisk}
                disabled={loading}
                className="
                  flex-1 px-4 py-2 rounded-xl text-sm font-semibold text-white
                  bg-gradient-to-r from-indigo-600 to-purple-600
                  hover:from-indigo-500 hover:to-purple-500
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-all duration-200 shadow-lg shadow-indigo-900/40
                "
              >
                Check this property
              </button>
              <button
                onClick={() => {
                  setPin(null);
                  setPinRisk("DEFAULT");
                  setError(null);
                  onClearPin?.();
                }}
                className="px-3 py-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-700 transition-all"
                aria-label="Clear pin"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Loading overlay */}
      {loading && (
        <div className="absolute inset-0 z-[5000] bg-slate-950/75 backdrop-blur-md flex flex-col items-center justify-center gap-4">
          <div className="relative">
            <div className="w-16 h-16 rounded-full border-4 border-indigo-900 border-t-indigo-400 animate-spin" />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-xl">🗺</span>
            </div>
          </div>
          <div className="text-center">
            <div className="text-white font-semibold text-sm">Analysing property risk…</div>
            <div className="text-slate-400 text-xs mt-1">Checking CRZ, flood & water body data</div>
          </div>
        </div>
      )}

      {/* Map Switcher Controls */}
      <div className="absolute top-4 right-4 z-[4000] bg-slate-900/90 backdrop-blur-xl rounded-xl border border-slate-700/50 p-1 flex gap-1 shadow-2xl">
        {Object.entries(TILE_LAYERS).map(([key, config]) => (
          <button
            key={key}
            onClick={() => setActiveTile(key)}
            className={`
              px-3 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200
              ${
                activeTile === key
                  ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-900/30"
                  : "text-slate-400 hover:text-white hover:bg-slate-800"
              }
            `}
          >
            {config.name}
          </button>
        ))}
      </div>

      {/* Legend */}
      <div className="absolute top-20 right-4 z-[4000] bg-slate-900/90 backdrop-blur-xl rounded-xl border border-slate-700/50 p-3 shadow-2xl">
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Risk Level</div>
        {[
          { color: PIN_COLORS.HIGH, label: "High Risk" },
          { color: PIN_COLORS.MEDIUM, label: "Moderate" },
          { color: PIN_COLORS.LOW, label: "Low Risk" },
          { color: PIN_COLORS.DEFAULT, label: "Unassessed" },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2 mb-1.5 last:mb-0">
            <div
              className="w-3 h-3 rounded-full flex-shrink-0 shadow"
              style={{ background: color }}
            />
            <span className="text-slate-300 text-xs">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

