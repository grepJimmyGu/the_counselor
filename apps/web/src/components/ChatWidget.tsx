"use client";

/**
 * ChatWidget — floating bottom-right chat panel (Stage 7 / ticket #7).
 *
 * Mounts on workspace + stock-detail pages for Phase 1. The same component
 * is used for authed and anonymous users; it asks `useSession` what mode
 * to drive and routes to the appropriate backend endpoint via
 * `useChatStream`.
 *
 * Layout per spec §5.1:
 *   - Collapsed: floating circular button bottom-right
 *   - Expanded: 380×600 panel with header / scroll area / composer / footer
 *
 * Anonymous variants:
 *   - Turn-count chip in header reads from the streaming `started` frame
 *   - Compliance disclosure footer shown for everyone
 *
 * Citation chips per ticket #9: `<cite source="X" id="Y"/>` in the streamed
 * text gets replaced by a styled chip linking back to the tool that
 * produced the number.
 */
import { useMemo, useRef, useState, useEffect } from "react";
import { subscribeChatSeed } from "@/lib/chat-widget-event-bus";
import { usePathname } from "next/navigation";
import { useSession } from "next-auth/react";
import { MessageSquare, X, Send, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ChatContextType, UIChatMessage } from "@/lib/contracts";
import { useChatStream } from "@/lib/useChatStream";


/** Derive the chat context from the current URL — drives the backend's
 *  system-prompt anchoring ("looking at AAPL", "looking at workspace draft"). */
function useChatContext(pathname: string | null): ChatContextType {
  return useMemo<ChatContextType>(() => {
    if (!pathname) return "general";
    if (pathname.startsWith("/workspace")) return "workspace";
    const stockMatch = pathname.match(/^\/stocks\/([A-Z0-9.-]+)/i);
    if (stockMatch) return `stock:${stockMatch[1].toUpperCase()}`;
    const backtestMatch = pathname.match(/^\/backtest\/([^/]+)/);
    if (backtestMatch) return `backtest:${backtestMatch[1]}`;
    const sharedMatch = pathname.match(/^\/s\/([^/?]+)/);
    if (sharedMatch) return `community_strategy:${sharedMatch[1]}`;
    if (pathname.startsWith("/account/saved")) return "user_saved";
    return "general";
  }, [pathname]);
}


export function ChatWidget() {
  const pathname = usePathname();
  const { data: session, status: sessionStatus } = useSession();
  const contextType = useChatContext(pathname);

  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  // Seed greeting injected via `dispatchChatSeed()` (e.g. from the
  // stock-detail "Apply a Strategy" click). Rendered as the first
  // assistant turn so the user opens to a chat in progress, not a
  // blank input. No backend round-trip — purely display-side.
  const [seedGreeting, setSeedGreeting] = useState<string | null>(null);

  useEffect(() => {
    return subscribeChatSeed(({ greeting }) => {
      setSeedGreeting(greeting);
      setOpen(true);
    });
  }, []);

  // Stable conversation id per widget mount. React 19's purity rule
  // disallows Date.now / Math.random inside render, so we lazily init
  // via useState (the initializer runs exactly once at mount).
  const [conversationId] = useState(
    () => `conv-${Math.random().toString(36).slice(2)}-${Date.now()}`,
  );

  const isAnonymous = sessionStatus !== "authenticated";
  const backendToken =
    (session as unknown as { backendToken?: string } | null)?.backendToken ?? null;

  const { messages, sendMessage, isStreaming, error, anonTurnsRemaining } =
    useChatStream({
      conversationId,
      anonymous: isAnonymous,
      backendToken,
      contextType,
    });

  // Auto-scroll on new messages.
  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, open]);

  function handleSend() {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    void sendMessage(text);
  }

  // Collapsed state — just the floating launcher button.
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-foreground text-background shadow-lg transition-transform hover:scale-105"
        aria-label="Open chat"
      >
        <MessageSquare className="h-6 w-6" />
      </button>
    );
  }

  return (
    <div
      className="fixed bottom-6 right-6 z-40 flex h-[600px] w-[380px] flex-col rounded-xl border border-border bg-background shadow-2xl"
      role="dialog"
      aria-label="Livermore chat"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex flex-col">
          <span className="text-sm font-semibold">Research partner</span>
          <ContextChip contextType={contextType} />
        </div>
        <div className="flex items-center gap-2">
          {isAnonymous && anonTurnsRemaining !== null && (
            <span
              className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700"
              title="Anonymous users get 5 chat turns; sign up for unlimited"
            >
              {anonTurnsRemaining} of 5 free turns left
            </span>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close chat"
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Message list */}
      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-3 text-sm"
      >
        {messages.length === 0 && !seedGreeting && (
          <p className="text-muted-foreground">
            Ask me to build a strategy, research a stock, or explain a concept.
          </p>
        )}
        {seedGreeting && (
          <MessageRow
            message={{
              id: "__seed__",
              role: "assistant",
              content: seedGreeting,
            }}
          />
        )}
        {messages.map((m) => (
          <MessageRow key={m.id} message={m} />
        ))}
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="text-xs">{error}</span>
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-border px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            disabled={isStreaming}
            placeholder={
              isStreaming
                ? "Waiting for response…"
                : "Ask a research question…"
            }
            rows={2}
            className="flex-1 resize-none rounded-md border border-input bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
          />
          <Button
            type="button"
            size="sm"
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            aria-label="Send message"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <p className="mt-2 text-[10px] leading-tight text-muted-foreground">
          Research tooling only. Outputs are paper strategies and historical
          backtests, not financial advice.
        </p>
      </div>
    </div>
  );
}


// ── Sub-components ───────────────────────────────────────────────────────────


function ContextChip({ contextType }: { contextType: ChatContextType }) {
  let label: string | null = null;
  if (contextType === "workspace") label = "Looking at workspace";
  else if (contextType.startsWith("stock:"))
    label = `Looking at ${contextType.slice("stock:".length)}`;
  else if (contextType.startsWith("backtest:"))
    label = "Looking at backtest result";
  else if (contextType.startsWith("community_strategy:"))
    label = "Community strategy";
  else if (contextType === "user_saved") label = "Your saved strategies";
  if (!label) return null;
  return <span className="text-[11px] text-muted-foreground">{label}</span>;
}


function MessageRow({ message }: { message: UIChatMessage }) {
  if (message.role === "tool") {
    return (
      <div className="flex justify-start">
        <span className="rounded-md bg-muted/40 px-2 py-1 text-[11px] text-muted-foreground">
          {message.isStreaming ? "🔧 " : "✓ "}
          {message.content}
        </span>
      </div>
    );
  }

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-primary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] space-y-1">
        {message.refusalCategory && (
          <span className="inline-block rounded-full bg-orange-50 px-2 py-0.5 text-[10px] font-medium text-orange-700">
            Research-only · {humanizeRefusal(message.refusalCategory)}
          </span>
        )}
        <div className="whitespace-pre-wrap rounded-lg bg-muted/40 px-3 py-2">
          <AssistantText content={message.content} citations={message.citations} />
          {message.isStreaming && <span className="ml-1 animate-pulse">▍</span>}
        </div>
        {message.hasCitationWarning && (
          <p className="text-[10px] text-amber-700">
            Some figures could not be sourced to tool outputs — verify before acting.
          </p>
        )}
      </div>
    </div>
  );
}


function AssistantText({
  content,
  citations,
}: {
  content: string;
  citations?: UIChatMessage["citations"];
}) {
  if (!citations || citations.length === 0) {
    return <>{content}</>;
  }
  // Substitute `[cite:N]` tokens with chip components.
  const parts = content.split(/(\[cite:\d+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/^\[cite:(\d+)\]$/);
        if (m) {
          const idx = Number(m[1]);
          const cite = citations[idx];
          if (!cite) return null;
          return (
            <span
              key={i}
              title={`Source: ${cite.source}${cite.id ? ` · ${cite.id}` : ""}`}
              className="ml-0.5 inline-flex items-center rounded-full bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700"
            >
              {cite.source.replace(/_/g, " ")}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}


function humanizeRefusal(category: string): string {
  switch (category) {
    case "trade_execution":
      return "no trade execution";
    case "personalized_advice":
      return "no personalized advice";
    case "forward_prediction":
      return "no forward predictions";
    case "off_topic":
      return "off-topic";
    default:
      return category;
  }
}
