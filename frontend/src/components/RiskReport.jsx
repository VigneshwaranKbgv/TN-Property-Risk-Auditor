/**
 * RiskReport.jsx
 * Slide-in panel displaying the risk analysis, LLM report, and chat Q&A.
 */

import { useState } from "react";
import { jsPDF } from "jspdf";
import RiskBadge from "./RiskBadge";
import ChatPanel from "./ChatPanel";

// ── Collapsible section ───────────────────────────────────────────────────────
function CollapsibleSection({ title, icon, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-slate-700/50 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/60 hover:bg-slate-700/60 transition-colors duration-200 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
          <span>{icon}</span>
          {title}
        </span>
        <svg
          className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      <div
        className={`overflow-hidden transition-all duration-300 ${open ? "max-h-96" : "max-h-0"}`}
      >
        <div className="px-4 py-3 bg-slate-900/40 text-sm text-slate-300 space-y-2">
          {children}
        </div>
      </div>
    </div>
  );
}

// ── Metric row ────────────────────────────────────────────────────────────────
function MetricRow({ label, value, highlight }) {
  return (
    <div className="flex justify-between items-center py-1 border-b border-slate-700/30 last:border-0">
      <span className="text-slate-400 text-xs">{label}</span>
      <span
        className={`text-xs font-semibold ${
          highlight === "danger"
            ? "text-red-400"
            : highlight === "warn"
            ? "text-amber-400"
            : highlight === "good"
            ? "text-emerald-400"
            : "text-slate-200"
        }`}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

// ── Main RiskReport ───────────────────────────────────────────────────────────
export default function RiskReport({ riskData, onClose }) {
  if (!riskData) return null;

  const { risk_metrics, report, overall_risk } = riskData;
  const { coordinates, water_body, crz, flood_zone, land_use } = risk_metrics;

  const downloadPDF = () => {
    const doc = new jsPDF();
    const pageWidth = doc.internal.pageSize.getWidth();

    // Header
    doc.setFillColor(15, 23, 42);
    doc.rect(0, 0, pageWidth, 35, "F");
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(16);
    doc.setFont("helvetica", "bold");
    doc.text("TN Property Risk Auditor", 14, 14);
    doc.setFontSize(10);
    doc.setFont("helvetica", "normal");
    doc.text("Environmental Risk Report", 14, 22);
    doc.text(`Generated: ${new Date().toLocaleString("en-IN")}`, 14, 29);

    // Coordinates
    doc.setTextColor(50, 50, 50);
    doc.setFontSize(11);
    doc.setFont("helvetica", "bold");
    doc.text(`Property Coordinates`, 14, 48);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    doc.text(`Latitude: ${coordinates.lat}   Longitude: ${coordinates.lon}`, 14, 56);

    // Risk Level
    doc.setFontSize(13);
    doc.setFont("helvetica", "bold");
    const riskColor =
      overall_risk === "HIGH"
        ? [220, 38, 38]
        : overall_risk === "MEDIUM"
        ? [217, 119, 6]
        : [5, 150, 105];
    doc.setTextColor(...riskColor);
    doc.text(`Overall Risk: ${overall_risk}`, 14, 68);

    // Report text
    doc.setTextColor(30, 30, 30);
    doc.setFontSize(10);
    doc.setFont("helvetica", "bold");
    doc.text("Risk Assessment Report:", 14, 82);
    doc.setFont("helvetica", "normal");
    const lines = doc.splitTextToSize(report, pageWidth - 28);
    doc.text(lines, 14, 90);

    // Metrics table
    let y = 90 + lines.length * 5 + 10;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.text("Spatial Risk Metrics:", 14, y);
    y += 8;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);

    const rows = [
      ["Water Body Infringement", water_body?.infringement ? "YES" : "NO"],
      ["Distance to Nearest Water Body", water_body?.distance_meters != null ? `${water_body.distance_meters} m` : "N/A"],
      ["Nearest Water Body", water_body?.nearest_body_name || "N/A"],
      ["Inside CRZ Zone", crz?.inside_zone ? "YES" : "NO"],
      ["CRZ Zone Type", crz?.zone_type || "N/A"],
      ["Distance to CRZ Boundary", crz?.distance_to_boundary_meters != null ? `${crz.distance_to_boundary_meters} m` : "N/A"],
      ["Inside Flood Zone", flood_zone?.inside_zone ? "YES" : "NO"],
      ["Flood Risk Level", flood_zone?.risk_level || "N/A"],
    ];

    rows.forEach(([label, val]) => {
      doc.text(`${label}:`, 14, y);
      doc.text(val, 120, y);
      y += 7;
    });

    y += 8;
    doc.setFontSize(8);
    doc.setTextColor(120, 120, 120);
    doc.text(
      "Note: This report is for informational purposes only. Consult a licensed surveyor or property lawyer before making legal decisions.",
      14,
      y,
      { maxWidth: pageWidth - 28 }
    );

    doc.save(`property-risk-${coordinates.lat}-${coordinates.lon}.pdf`);
  };

  const reportParagraphs = report.split(/\n+/).filter(Boolean);

  return (
    <div
      className="
        relative h-full w-full
        flex flex-col bg-slate-900/95 backdrop-blur-xl
        border-l border-slate-700/50 shadow-2xl
        overflow-hidden
      "
      role="complementary"
      aria-label="Property Risk Report"
    >
      {/* ── Panel Header ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/50 bg-slate-800/60 flex-shrink-0">
        <div>
          <h2 className="text-base font-bold text-white tracking-tight">
            Property Risk Report
          </h2>
          {risk_metrics.location_address && risk_metrics.location_address !== "Unknown Location" && (
            <p className="text-xs text-indigo-400 font-semibold mt-0.5 max-w-[18rem] truncate" title={risk_metrics.location_address}>
              📍 {risk_metrics.location_address}
            </p>
          )}
          <p className="text-xs text-slate-400 mt-0.5">
            {coordinates.lat.toFixed(5)}°N, {coordinates.lon.toFixed(5)}°E
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition-all"
          aria-label="Close panel"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* ── Scrollable Content ───────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 scrollbar-thin scrollbar-thumb-slate-600 scrollbar-track-transparent">

        {/* Risk Badge */}
        <div className="flex justify-center pt-1">
          <RiskBadge level={overall_risk} />
        </div>

        {/* LLM Report */}
        <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/40">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            AI Risk Assessment
          </h3>
          <div className="space-y-2">
            {reportParagraphs.map((para, i) => (
              <p key={i} className="text-slate-300 text-sm leading-relaxed">
                {para}
              </p>
            ))}
          </div>
        </div>

        {/* Water Body Details */}
        <CollapsibleSection title="Water Body Details" icon="💧" defaultOpen={water_body?.infringement}>
          <MetricRow
            label="Buffer Infringement (50 m)"
            value={water_body?.infringement ? "YES — Property overlaps water body boundary" : "No infringement"}
            highlight={water_body?.infringement ? "danger" : "good"}
          />
          <MetricRow
            label="Distance to Nearest Water Body"
            value={water_body?.distance_meters != null ? `${water_body.distance_meters} m` : "N/A"}
            highlight={
              water_body?.distance_meters != null && water_body.distance_meters <= 50
                ? "danger"
                : water_body?.distance_meters != null && water_body.distance_meters <= 100
                ? "warn"
                : "good"
            }
          />
          <MetricRow
            label="Nearest Water Body"
            value={water_body?.nearest_body_name || "N/A"}
          />
        </CollapsibleSection>

        {/* CRZ Details */}
        <CollapsibleSection title="Coastal Regulation Zone (CRZ)" icon="🌊" defaultOpen={crz?.inside_zone}>
          <MetricRow
            label="Inside CRZ Zone"
            value={crz?.inside_zone ? `YES — ${crz.zone_type}` : "No"}
            highlight={crz?.inside_zone ? (crz.zone_type === "CRZ-I" ? "danger" : "warn") : "good"}
          />
          <MetricRow
            label="Zone Type"
            value={crz?.zone_type || "Not in CRZ"}
          />
          <MetricRow
            label="Distance to CRZ Boundary"
            value={crz?.distance_to_boundary_meters != null ? `${crz.distance_to_boundary_meters} m` : "N/A"}
            highlight={
              crz?.inside_zone
                ? "warn"
                : crz?.distance_to_boundary_meters != null && crz.distance_to_boundary_meters < 200
                ? "warn"
                : "good"
            }
          />
          {crz?.inside_zone && (
            <div className="mt-2 p-2 bg-amber-900/30 rounded-lg border border-amber-700/40 text-amber-300 text-xs">
              ⚠ Properties inside CRZ zones are subject to special coastal management regulations under the Environment Protection Act, 1986.
            </div>
          )}
        </CollapsibleSection>

        {/* Flood Zone Details */}
        <CollapsibleSection title="Flood Zone Details" icon="🌧️" defaultOpen={flood_zone?.inside_zone}>
          <MetricRow
            label="Inside Flood Zone"
            value={flood_zone?.inside_zone ? "YES" : "No"}
            highlight={flood_zone?.inside_zone ? "danger" : "good"}
          />
          <MetricRow
            label="Flood Risk Classification"
            value={flood_zone?.risk_level || "Not in flood zone"}
            highlight={
              flood_zone?.risk_level === "HIGH"
                ? "danger"
                : flood_zone?.risk_level === "MEDIUM"
                ? "warn"
                : "good"
            }
          />
          {flood_zone?.inside_zone && (
            <div className="mt-2 p-2 bg-blue-900/30 rounded-lg border border-blue-700/40 text-blue-300 text-xs">
              🌊 Insurance costs may be significantly higher. Consult TNSDMA flood maps before purchase.
            </div>
          )}
        </CollapsibleSection>

        {/* Land Use (Bhuvan LULC) */}
        {land_use && (
          <CollapsibleSection
            title="Land Use Classification (ISRO Bhuvan)"
            icon="🛰️"
            defaultOpen={land_use?.risk_flag === "HIGH"}
          >
            <MetricRow
              label="Satellite Land Classification"
              value={land_use?.lulc_class || "Unknown"}
              highlight={
                land_use?.risk_flag === "HIGH"
                  ? "danger"
                  : land_use?.risk_flag === "MEDIUM"
                  ? "warn"
                  : land_use?.risk_flag === "LOW"
                  ? "good"
                  : undefined
              }
            />
            <MetricRow
              label="LULC Code"
              value={land_use?.lulc_code != null ? `${land_use.lulc_code}` : "N/A"}
            />
            <MetricRow
              label="Risk Indication"
              value={land_use?.risk_flag || "Unknown"}
              highlight={
                land_use?.risk_flag === "HIGH" ? "danger"
                : land_use?.risk_flag === "MEDIUM" ? "warn"
                : land_use?.risk_flag === "LOW" ? "good"
                : undefined
              }
            />
            <MetricRow
              label="Data Source"
              value={land_use?.source === "bhuvan" ? "NRSC/ISRO Bhuvan LULC 1:50k" : "Unavailable"}
            />
            {land_use?.risk_flag === "HIGH" && (
              <div className="mt-2 p-2 bg-red-900/30 rounded-lg border border-red-700/40 text-red-300 text-xs">
                🛰️ Satellite data classifies this as <strong>{land_use?.lulc_class}</strong>.
                Construction on {land_use?.lulc_code === 6 ? "water bodies" : land_use?.lulc_code === 7 ? "wetlands" : "forests"}
                {" "}is heavily restricted under Indian environmental law.
              </div>
            )}
            {land_use?.source === "unavailable" && (
              <div className="mt-2 p-2 bg-slate-800/50 rounded-lg border border-slate-700/40 text-slate-400 text-xs">
                Bhuvan LULC data unavailable for this query (API timeout or out of coverage).
              </div>
            )}
          </CollapsibleSection>
        )}

        {/* Chat Panel */}
        <div>
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            Ask the Property Advisor
          </h3>
          <ChatPanel riskMetrics={risk_metrics} />
        </div>
      </div>

      {/* ── Footer ──────────────────────────────────────────────────────────── */}
      <div className="flex-shrink-0 px-5 py-3 border-t border-slate-700/50 bg-slate-800/40">
        <button
          onClick={downloadPDF}
          className="
            w-full flex items-center justify-center gap-2
            px-4 py-2.5 rounded-xl
            bg-gradient-to-r from-indigo-600 to-purple-600
            hover:from-indigo-500 hover:to-purple-500
            text-white text-sm font-semibold
            transition-all duration-200 shadow-lg shadow-indigo-900/40
          "
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Download Report (PDF)
        </button>
        <p className="text-center text-xs text-slate-500 mt-2">
          For informational purposes only. Consult a licensed surveyor.
        </p>
      </div>
    </div>
  );
}
