import { useRef, useState } from "react";
import { api } from "../../services/api.js";
import { LAB_FLAG_META } from "../../constants/index.js";

export default function ReportUpload({ conversationId, onAnalyzed }) {
  const [file, setFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const inputRef = useRef(null);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file || isUploading) return;

    setError(null);
    setIsUploading(true);
    try {
      const data = await api.uploadReport({ conversationId, file });
      setAnalysis(data);
      onAnalyzed?.(data);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setError(err.message || "Upload failed. Please try again.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">
        Upload a medical report
      </h2>
      <p className="mb-3 text-[11px] text-slate-400">
        PDF, DOCX, JPG, or PNG. We'll flag any lab values outside typical
        reference ranges and explain them in plain language.
      </p>

      <form onSubmit={handleUpload} className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.jpg,.jpeg,.png"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          disabled={isUploading}
          className="flex-1 text-xs text-slate-600 file:mr-2 file:rounded-lg file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-xs file:font-medium file:text-slate-700 hover:file:bg-slate-200"
        />
        <button
          type="submit"
          disabled={!file || isUploading}
          className="rounded-xl bg-brand px-3 py-1.5 text-xs font-medium text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isUploading ? "Analyzing…" : "Upload"}
        </button>
      </form>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      {analysis && (
        <div className="mt-3 space-y-3 border-t border-slate-100 pt-3 text-sm">
          <p className="text-slate-700">{analysis.summary}</p>

          {analysis.flagged_values.length > 0 && (
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Flagged values
              </h3>
              <ul className="space-y-1">
                {analysis.flagged_values.map((v) => {
                  const meta = LAB_FLAG_META[v.flag] || LAB_FLAG_META.normal;
                  return (
                    <li
                      key={v.name}
                      className="flex items-center justify-between text-xs text-slate-700"
                    >
                      <span>
                        {v.name}: {v.value} {v.unit}{" "}
                        <span className="text-slate-400">
                          (ref {v.reference_low}-{v.reference_high})
                        </span>
                      </span>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${meta.className}`}
                      >
                        {meta.label}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {analysis.sources.length > 0 && (
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Sources
              </h3>
              <ul className="space-y-1">
                {analysis.sources.map((s, i) => (
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

          <p className="text-[11px] italic text-slate-400">{analysis.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
