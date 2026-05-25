"use client";

/**
 * Global event bus for the floating ChatWidget. Mirrors the pattern
 * in `upgrade-modal-event-bus.ts` — a tiny event-emitter so any code
 * (React or otherwise) can ask the ChatWidget to open with a pre-seeded
 * assistant greeting.
 *
 * The seed message is rendered inline as the FIRST assistant turn so
 * the user sees a chat already in progress instead of a blank input.
 * No backend call is made for the seed — it's purely display-side.
 *
 * Originally added 2026-05-24 to power the stock-detail page's
 * "Apply a Strategy" click: that handler dispatches a seed like
 * "I'll help you build a strategy on AAPL — pick from the wizard
 * or describe your own idea." alongside opening the strategy
 * builder modal.
 */

export interface ChatSeedPayload {
  /** The assistant greeting copy to render as the first message. */
  greeting: string;
  /** Optional context tag (e.g. ticker symbol) — currently unused but
   *  kept for future telemetry / context-aware backend prompts. */
  contextHint?: string;
}

type Listener = (payload: ChatSeedPayload) => void;

const _listeners = new Set<Listener>();

export function dispatchChatSeed(payload: ChatSeedPayload): void {
  for (const fn of _listeners) {
    try {
      fn(payload);
    } catch {
      // Listeners must not break dispatch
    }
  }
}

export function subscribeChatSeed(fn: Listener): () => void {
  _listeners.add(fn);
  return () => {
    _listeners.delete(fn);
  };
}
