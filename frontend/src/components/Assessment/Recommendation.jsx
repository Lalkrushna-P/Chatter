export default function Recommendation({ meta }) {
  if (!meta) return null;
  const { recommended_action, red_flags = [], possible_categories = [], sources = [] } =
    meta;

  return (
    <div className="space-y-3 text-sm">
      {recommended_action && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Recommended next step
          </h3>
          <p className="text-slate-700">{recommended_action}</p>
        </div>
      )}

      {possible_categories.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Possible explanations
          </h3>
          <ul className="list-inside list-disc text-slate-700">
            {possible_categories.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <p className="mt-1 text-[11px] italic text-slate-400">
            These are possibilities based on what you described, not a diagnosis.
          </p>
        </div>
      )}

      {red_flags.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-500">
            Warning signs detected
          </h3>
          <ul className="list-inside list-disc text-red-700">
            {red_flags.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      )}

      {sources.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Sources
          </h3>
          <ul className="space-y-1">
            {sources.map((s, i) => (
              <li key={i} className="text-xs text-slate-600">
                {s.source_url ? (
                  <a
                    href={s.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand hover:underline"
                  >
                    {s.title}
                  </a>
                ) : (
                  s.title
                )}
                {s.source ? ` — ${s.source}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
