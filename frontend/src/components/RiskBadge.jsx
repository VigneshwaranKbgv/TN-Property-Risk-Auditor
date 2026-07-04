/**
 * RiskBadge.jsx
 * Displays a colour-coded risk level badge (HIGH / MEDIUM / LOW).
 */

export default function RiskBadge({ level }) {
  const config = {
    HIGH: {
      label: "⚠ High Risk",
      bg: "bg-red-600",
      glow: "shadow-red-500/60",
      pulse: "animate-pulse",
      text: "text-white",
      border: "border-red-400",
    },
    MEDIUM: {
      label: "⚡ Moderate Risk",
      bg: "bg-amber-500",
      glow: "shadow-amber-400/60",
      pulse: "",
      text: "text-white",
      border: "border-amber-300",
    },
    LOW: {
      label: "✓ Low Risk",
      bg: "bg-emerald-500",
      glow: "shadow-emerald-400/60",
      pulse: "",
      text: "text-white",
      border: "border-emerald-300",
    },
  };

  const cfg = config[level] || {
    label: "Unknown Risk",
    bg: "bg-slate-600",
    glow: "",
    pulse: "",
    text: "text-white",
    border: "border-slate-400",
  };

  return (
    <div
      className={`
        inline-flex items-center gap-2 px-5 py-2.5 rounded-full border
        ${cfg.bg} ${cfg.text} ${cfg.border} ${cfg.pulse}
        shadow-lg ${cfg.glow} font-bold text-base tracking-wide select-none
        transition-all duration-300
      `}
      role="status"
      aria-label={`Risk level: ${cfg.label}`}
    >
      {cfg.label}
    </div>
  );
}
