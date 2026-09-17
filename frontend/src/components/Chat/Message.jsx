function formatTime(date) {
  try {
    return new Date(date).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default function Message({ message }) {
  const isUser = message.role === "user";
  const emergency = message.isEmergency;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={[
            "whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm shadow-sm",
            isUser
              ? "rounded-br-sm bg-brand text-white"
              : emergency
              ? "rounded-bl-sm border border-red-300 bg-red-50 text-red-900"
              : "rounded-bl-sm border border-slate-200 bg-white text-slate-800",
          ].join(" ")}
        >
          {emergency && (
            <div className="mb-1 flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-red-600">
              ⚠ Emergency
            </div>
          )}
          {message.content}
        </div>
        <div
          className={`mt-1 px-1 text-[11px] text-slate-400 ${
            isUser ? "text-right" : "text-left"
          }`}
        >
          {formatTime(message.at)}
        </div>
      </div>
    </div>
  );
}
