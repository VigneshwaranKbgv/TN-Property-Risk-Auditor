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
      {/* Full-screen map */}
      <div
        className={`absolute top-0 bottom-0 left-0 transition-all duration-300 ${
          reportOpen ? "right-[28rem]" : "right-0"
        }`}
      >
        <MapView onRiskData={handleRiskData} reportOpen={reportOpen} />
      </div>

      {/* Slide-in report panel */}
      <div
        className={`
          absolute top-0 right-0 h-full w-[28rem] z-50
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
