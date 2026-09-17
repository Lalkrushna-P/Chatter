import { RISK_META } from "../../constants/index.js";

export default function RiskIndicator({ riskLevel }) {
  const meta = RISK_META[riskLevel] || RISK_META.unknown;
  return (
    <div className={`rounded-xl border p-3 ring-1 ${meta.ring} ${meta.bg}`}>
      <div className="flex items-center gap-2">
        <span className={`h-3 w-3 rounded-full ${meta.color}`} />
        <span className={`text-sm font-semibold ${meta.text}`}>{meta.label}</span>
      </div>
      <p className="mt-1 text-xs text-slate-600">{meta.description}</p>
    </div>
  );
}
