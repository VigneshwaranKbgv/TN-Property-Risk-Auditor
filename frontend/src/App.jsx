/**
 * App.jsx
 * Root application component — orchestrates MapView and RiskReport.
 */

import { useState } from "react";
import MapView from "./components/MapView";
import RiskReport from "./components/RiskReport";

export default function App() {
  const [riskData, setRiskData] = useState(null);
  const [reportOpen, setReportOpen] = useState(false);

  const handleRiskData = (data) => {
    setRiskData(data);
    setReportOpen(true);
  };

  const handleCloseReport = () => {
    setReportOpen(false);
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-slate-950">
      {/* Full-screen map. On mobile the report panel covers the full screen
          when open, so the map only needs to make room for it on sm+ screens. */}
      <div
        className={`absolute top-0 bottom-0 left-0 right-0 transition-all duration-300 ${
          reportOpen ? "sm:right-[28rem]" : "sm:right-0"
        }`}
      >
        <MapView onRiskData={handleRiskData} reportOpen={reportOpen} onClearPin={handleCloseReport} />
      </div>

      {/* Slide-in report panel — full width on mobile, fixed sidebar on sm+.
          z-[9999] guarantees it stacks above MapView's own overlays
          (which use z-[4000]/z-[5000]) once it covers the same screen area
          on mobile. */}
      <div
        className={`
          absolute top-0 right-0 h-full w-full sm:w-[28rem] z-[9999]
          transform transition-transform duration-300 ease-out
          ${reportOpen ? "translate-x-0" : "translate-x-full"}
        `}
      >
        {riskData && (
          <RiskReport riskData={riskData} onClose={handleCloseReport} />
        )}
      </div>
    </div>
  );
}
