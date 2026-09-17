import { useEffect, useRef } from "react";
import Message from "./Message.jsx";
import MessageInput from "./MessageInput.jsx";
import TypingIndicator from "./TypingIndicator.jsx";

export default function ChatWindow({ messages, isLoading, error, onSend }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.map((m) => (
          <Message key={m.id} message={m} />
        ))}
        {isLoading && <TypingIndicator />}
        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <div ref={endRef} />
      </div>
      <div className="border-t border-slate-200 bg-white p-3">
        <MessageInput onSend={onSend} disabled={isLoading} />
      </div>
    </div>
  );
}
