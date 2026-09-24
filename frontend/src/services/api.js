// API client (PRD section 25). Base URL is configurable via VITE_API_BASE_URL;
// in dev, Vite proxies /api to the FastAPI backend (see vite.config.js).
const BASE = import.meta.env.VITE_API_BASE_URL || "";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  sendMessage: ({ conversationId, message, reportIds }) =>
    request("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: conversationId,
        message,
        report_ids: reportIds || [],
      }),
    }),

  startAssessment: () =>
    request("/api/assessment/start", { method: "POST" }),

  getSummary: (conversationId) =>
    request(`/api/assessment/${conversationId}/summary`),

  endAssessment: (conversationId) =>
    request(`/api/assessment/${conversationId}/end`, { method: "POST" }),

  sendFeedback: ({ conversationId, rating, feedbackText }) =>
    request("/api/feedback", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: conversationId,
        rating,
        feedback_text: feedbackText,
      }),
    }),

  uploadReport: async ({ conversationId, file }) => {
    const form = new FormData();
    form.append("file", file);
    if (conversationId) form.append("conversation_id", conversationId);

    // Deliberately not using request(): FormData needs the browser to set its
    // own multipart Content-Type (with boundary), not the JSON header above.
    const res = await fetch(`${BASE}/api/reports/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  },

  getReport: (reportId) => request(`/api/reports/${reportId}`),
};
