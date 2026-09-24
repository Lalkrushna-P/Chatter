import { useState } from "react";
import ChatWindow from "./components/Chat/ChatWindow.jsx";
import RiskIndicator from "./components/Assessment/RiskIndicator.jsx";
import Recommendation from "./components/Assessment/Recommendation.jsx";
import SymptomSummary from "./components/Assessment/SymptomSummary.jsx";
import Disclaimer from "./components/Common/Disclaimer.jsx";
import ReportUpload from "./components/Reports/ReportUpload.jsx";
import { useChat } from "./hooks/useChat.js";
import { api } from "./services/api.js";

export default function App() {
  const {
    messages,
    conversationId,
    riskLevel,
    lastMeta,
    isLoading,
    error,
    send,
    reset,
    attachReport,
  } = useChat();
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(null);

  const handleEnd = async () => {
    if (!conversationId) return;
    setSummaryError(null);
    try {
      await api.endAssessment(conversationId);
      const data = await api.getSummary(conversationId);
      setSummary(data);
    } catch (e) {
      setSummaryError(e.message);
    }
  };

  const handleNew = () => {
    setSummary(null);
    setSummaryError(null);
    reset();
  };

  return (
    <div className="mx-auto flex h-screen max-w-6xl flex-col p-3 sm:p-4">
      {/* Header */}
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-slate-800">
            Health Screening Assistant
          </h1>
          <p className="text-xs text-slate-500">
            Conversational symptom screening &amp; triage
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleNew}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
          >
            New assessment
          </button>
          <button
            onClick={handleEnd}
            disabled={!conversationId}
            className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-40"
          >
            End &amp; summarize
          </button>
        </div>
      </header>

      <div className="mb-3">
        <Disclaimer />
      </div>

      {/* Main layout */}
      <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
        {/* Chat */}
        <div className="flex min-h-0 flex-[3] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <ChatWindow
            messages={messages}
            isLoading={isLoading}
            error={error}
            onSend={send}
          />
        </div>

        {/* Assessment side panel */}
        <aside className="flex min-h-0 flex-[2] flex-col gap-4 overflow-y-auto">
          <RiskIndicator riskLevel={riskLevel} />

          <ReportUpload conversationId={conversationId} onAnalyzed={attachReport} />

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-2 text-sm font-semibold text-slate-700">
              Current guidance
            </h2>
            {lastMeta ? (
              <Recommendation meta={lastMeta} />
            ) : (
              <p className="text-xs text-slate-400">
                Guidance will appear here as you describe your symptoms.
              </p>
            )}
          </div>

          {(summary || summaryError) && (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="mb-2 text-sm font-semibold text-slate-700">
                Assessment summary
              </h2>
              {summaryError ? (
                <p className="text-xs text-red-600">{summaryError}</p>
              ) : (
                <SymptomSummary summary={summary} />
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
