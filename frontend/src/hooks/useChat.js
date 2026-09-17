import { useCallback, useRef, useState } from "react";
import { api } from "../services/api.js";
import { GREETING } from "../constants/index.js";

let idCounter = 0;
const nextId = () => `m${++idCounter}`;

export function useChat() {
  const [messages, setMessages] = useState([
    { id: nextId(), role: "assistant", content: GREETING, at: new Date() },
  ]);
  const [conversationId, setConversationId] = useState(null);
  const [riskLevel, setRiskLevel] = useState("unknown");
  const [lastMeta, setLastMeta] = useState(null); // { possible_categories, red_flags, recommended_action, sources }
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const convRef = useRef(null);

  const send = useCallback(async (text) => {
    const trimmed = text.trim();
    if (!trimmed || isLoading) return;

    setError(null);
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user", content: trimmed, at: new Date() },
    ]);
    setIsLoading(true);

    try {
      const data = await api.sendMessage({
        conversationId: convRef.current,
        message: trimmed,
      });
      convRef.current = data.conversation_id;
      setConversationId(data.conversation_id);
      setRiskLevel(data.risk_level || "unknown");
      setLastMeta({
        possible_categories: data.possible_categories || [],
        red_flags: data.red_flags || [],
        recommended_action: data.recommended_action,
        sources: data.sources || [],
        is_emergency: data.is_emergency,
        disclaimer: data.disclaimer,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          content: data.message,
          at: new Date(),
          isEmergency: data.is_emergency,
        },
      ]);
    } catch (e) {
      setError(e.message || "Something went wrong. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [isLoading]);

  const reset = useCallback(() => {
    convRef.current = null;
    setConversationId(null);
    setRiskLevel("unknown");
    setLastMeta(null);
    setError(null);
    setMessages([
      { id: nextId(), role: "assistant", content: GREETING, at: new Date() },
    ]);
  }, []);

  return {
    messages,
    conversationId,
    riskLevel,
    lastMeta,
    isLoading,
    error,
    send,
    reset,
  };
}
