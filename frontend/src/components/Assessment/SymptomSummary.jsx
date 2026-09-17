import { RISK_META } from "../../constants/index.js";

export default function SymptomSummary({ summary }) {
  if (!summary) return null;
  const meta = RISK_META[summary.risk_level] || RISK_META.unknown;

  return (
    <div className="space-y-3 text-sm">
      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Main symptoms
        </h3>
        {summary.symptoms?.length ? (
          <ul className="list-inside list-disc text-slate-700">
            {summary.symptoms.map((s) => (
              <li key={s.name}>
                {s.name}
                {s.severity != null ? ` — ${s.severity}/10` : ""}
                {s.duration ? `, ${s.duration}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-400">None recorded yet.</p>
        )}
      </div>

      <div>
        <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Assessment
        </h3>
        <p className={`font-medium ${meta.text}`}>{meta.label}</p>
      </div>

      {summary.possible_explanations?.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Possible explanations
          </h3>
          <ul className="list-inside list-disc text-slate-700">
            {summary.possible_explanations.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {summary.recommended_action && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Recommended next step
          </h3>
          <p className="text-slate-700">{summary.recommended_action}</p>
        </div>
      )}

      {summary.seek_urgent_care_if?.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-500">
            Seek urgent care if
          </h3>
          <ul className="list-inside list-disc text-red-700">
            {summary.seek_urgent_care_if.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
