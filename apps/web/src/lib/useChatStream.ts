"use client";

/**
 * useChatStream — React hook that drives a chat conversation via the SSE
 * endpoints in apps/api (Stage 7 tickets #5/#6 authed + anonymous).
 *
 * The hook is one-conversation-per-instance. Pass a stable conversationId
 * (a uuid generated on widget mount) and the hook handles:
 *
 *   - POST to /api/chat/conversations/{id}/messages (authed) or
 *     /api/anonymous/chat/conversations/{id}/messages (anon)
 *   - Stream parser: splits the response body into SSE frames, JSON-parses
 *     each, narrows to the typed ChatEvent union
 *   - State machine: builds UIChatMessage rows as tokens arrive, finalizes
 *     on `done`, surfaces errors
 *   - Anonymous turn count (from `started` frame) for the widget's chip
 *
 * Returns:
 *   - messages: UIChatMessage[]   (full conversation, including in-flight)
 *   - sendMessage(text)           (async; resolves when the stream closes)
 *   - isStreaming: boolean
 *   - error: string | null        (fatal errors only — non-fatal are surfaced
 *                                  inline as messages or guardrail badges)
 *   - anonTurnsRemaining: number | null  (anon only; null on authed surface)
 */
import { useCallback, useMemo, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/api";
import type {
  ChatContextType,
  ChatEvent,
  UIChatMessage,
} from "@/lib/contracts";


// Cite-chip regex. The backend emits `<cite source="X" id="Y"/>` (Y optional).
// Captured groups: 1=source, 2=id?
const CITE_RE = /<cite\s+source="([^"]+)"(?:\s+id="([^"]+)")?\s*\/?>(?:<\/cite>)?/g;


/** Extract citation chips from assistant text, returning the parsed list
 *  AND the text with chips replaced by a render-friendly token `[cite:N]`
 *  so the React renderer can substitute a component. */
export function parseCitations(text: string): {
  text: string;
  citations: Array<{ source: string; id?: string; raw: string }>;
} {
  const citations: Array<{ source: string; id?: string; raw: string }> = [];
  let i = 0;
  const rebuilt = text.replace(CITE_RE, (match, source, id) => {
    citations.push({ source, id, raw: match });
    return `[cite:${i++}]`;
  });
  return { text: rebuilt, citations };
}


interface UseChatStreamOpts {
  /** Generated client-side on widget mount; persists for the widget lifetime. */
  conversationId: string;
  /** Anonymous-mode flag. Routes to /api/anonymous/chat/* instead of /api/chat/*. */
  anonymous: boolean;
  /** Auth token for authed mode; ignored in anonymous mode. */
  backendToken?: string | null;
  /** Page context the backend uses for system-prompt anchoring. */
  contextType?: ChatContextType;
  contextPayload?: Record<string, unknown>;
}


export function useChatStream({
  conversationId,
  anonymous,
  backendToken,
  contextType,
  contextPayload,
}: UseChatStreamOpts) {
  const [messages, setMessages] = useState<UIChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anonTurnsRemaining, setAnonTurnsRemaining] = useState<number | null>(null);

  // The currently-streaming assistant message ID, if any. We mutate by id
  // rather than by ref-to-object because React state updates need a fresh
  // array on every render.
  const streamingAssistantIdRef = useRef<string | null>(null);

  const endpoint = useMemo(() => {
    const base = `${API_BASE_URL.replace(/\/$/, "")}`;
    return anonymous
      ? `${base}/api/anonymous/chat/conversations/${conversationId}/messages`
      : `${base}/api/chat/conversations/${conversationId}/messages`;
  }, [anonymous, conversationId]);

  const sendMessage = useCallback(async (text: string): Promise<void> => {
    if (!text.trim()) return;
    if (isStreaming) return;  // ignore re-sends during an active stream

    setError(null);
    setIsStreaming(true);

    // Optimistically append the user message + an empty assistant placeholder.
    const userId = `m-user-${Date.now()}`;
    const assistantId = `m-asst-${Date.now()}`;
    streamingAssistantIdRef.current = assistantId;
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: text },
      { id: assistantId, role: "assistant", content: "", isStreaming: true },
    ]);

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      };
      if (!anonymous && backendToken) {
        headers.Authorization = `Bearer ${backendToken}`;
      }

      const res = await fetch(endpoint, {
        method: "POST",
        credentials: anonymous ? "include" : "same-origin",
        headers,
        body: JSON.stringify({
          content: text,
          context_type: contextType ?? null,
          context_payload: contextPayload ?? null,
        }),
      });

      if (!res.ok) {
        // 402 = quota exhausted; the body carries the entitlement envelope.
        // We surface as a plain error string for now; ticket #8 can wire
        // the UpgradeModal / signup CTA depending on detail.is_anonymous.
        let errMsg = `Chat failed (${res.status})`;
        try {
          const body = await res.json();
          if (body?.detail?.entitlement?.detail) {
            errMsg = body.detail.entitlement.detail;
          } else if (body?.detail && typeof body.detail === "string") {
            errMsg = body.detail;
          }
        } catch {/* ignore JSON parse */}
        setError(errMsg);
        // Drop the assistant placeholder — no response coming.
        setMessages((prev) => prev.filter((m) => m.id !== assistantId));
        return;
      }

      if (!res.body) {
        setError("Browser does not support streaming responses.");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by blank lines (\n\n). Process whole
        // frames, leave the trailing partial in the buffer.
        let sepIdx = buffer.indexOf("\n\n");
        while (sepIdx !== -1) {
          const rawFrame = buffer.slice(0, sepIdx);
          buffer = buffer.slice(sepIdx + 2);
          handleSseFrame(rawFrame, assistantId, {
            setMessages, setError, setAnonTurnsRemaining,
          });
          sepIdx = buffer.indexOf("\n\n");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsStreaming(false);
      streamingAssistantIdRef.current = null;
      // Mark the streaming assistant message as no-longer-streaming.
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, isStreaming: false } : m
        )
      );
    }
  }, [
    endpoint,
    anonymous,
    backendToken,
    contextType,
    contextPayload,
    isStreaming,
  ]);

  return {
    messages,
    sendMessage,
    isStreaming,
    error,
    anonTurnsRemaining,
  };
}


/** Process one SSE frame (a `data: <json>` line). Updates state via the
 *  provided setters. Pure-ish — closed over by sendMessage, no shared state. */
function handleSseFrame(
  raw: string,
  assistantId: string,
  setters: {
    setMessages: React.Dispatch<React.SetStateAction<UIChatMessage[]>>;
    setError: React.Dispatch<React.SetStateAction<string | null>>;
    setAnonTurnsRemaining: React.Dispatch<React.SetStateAction<number | null>>;
  },
): void {
  const line = raw.trim();
  if (!line.startsWith("data:")) return;
  const json = line.slice("data:".length).trim();
  if (!json) return;

  let evt: ChatEvent;
  try {
    evt = JSON.parse(json) as ChatEvent;
  } catch {
    return; // malformed frame — skip silently; not fatal
  }

  const { setMessages, setError, setAnonTurnsRemaining } = setters;

  switch (evt.type) {
    case "started":
      if (typeof evt.anon_turns_remaining === "number") {
        setAnonTurnsRemaining(evt.anon_turns_remaining);
      }
      return;

    case "token":
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId ? { ...m, content: m.content + evt.text } : m
        )
      );
      return;

    case "tool_call_start":
      // Insert a "tool" placeholder for visual feedback; will be marked
      // complete by the matching tool_result event.
      setMessages((prev) => [
        ...prev,
        {
          id: `m-tool-${evt.call_id}`,
          role: "tool",
          content: `Running ${evt.name}…`,
          toolName: evt.name,
          isStreaming: true,
        },
      ]);
      return;

    case "tool_result":
      setMessages((prev) =>
        prev.map((m) =>
          m.id === `m-tool-${evt.call_id}`
            ? { ...m, content: `Used ${evt.name}`, isStreaming: false }
            : m
        )
      );
      return;

    case "guardrail":
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== assistantId) return m;
          if (evt.action === "refusal_logged" && evt.category) {
            return { ...m, refusalCategory: evt.category };
          }
          if (evt.action === "citation_warning_appended") {
            return { ...m, hasCitationWarning: true };
          }
          if (evt.action === "citation_reprompt_succeeded" && evt.rewritten_text) {
            // Replace the streamed text with the cleaned version.
            const parsed = parseCitations(evt.rewritten_text);
            return { ...m, content: parsed.text, citations: parsed.citations };
          }
          return m;
        }),
      );
      return;

    case "done":
      // Finalize the assistant message: parse out citations from the
      // accumulated text so the renderer can swap chip placeholders.
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== assistantId) return m;
          if (m.citations) return { ...m, isStreaming: false };  // already replaced
          const parsed = parseCitations(m.content);
          return {
            ...m,
            content: parsed.text,
            citations: parsed.citations,
            isStreaming: false,
          };
        }),
      );
      return;

    case "error":
      if (evt.fatal) {
        setError(evt.message);
      }
      return;
  }
}
