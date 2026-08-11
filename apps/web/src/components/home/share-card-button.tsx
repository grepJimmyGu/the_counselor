"use client";

/**
 * The share control on "Moving today".
 *
 * Everything behind this button already existed — payload, copy generation,
 * the guard, the renderer, the ornament — and none of it was reachable. This
 * is the surface.
 *
 * WHY THE FIRST CLICK IS SLOW AND THE REST ARE INSTANT. The POST generates
 * once per trading day; every later caller gets the same row untouched, so a
 * forwarded link shows what the sharer saw. That means the first click of the
 * day pays for an LLM call and the rest are a DB read. The button says so
 * rather than looking hung.
 *
 * WHY THE LANGUAGE PICKER ASKS FIRST. Chinese needs a bundled CJK font that
 * isn't committed yet (~4-5 MB), so the backend can't draw it on Railway. It
 * reports what it can render and we only offer that — a language we can't draw
 * is a 503 or a card of empty boxes, and both are worse than the option not
 * being there. When only one language is available the picker is absent
 * entirely rather than shown with a single dead option.
 */

import { useCallback, useEffect, useState } from "react";
import { createDailyCard, dailyCardImageUrl, getDailyCardLanguages } from "@/lib/api";
import type { CardLang } from "@/lib/contracts";

const LABELS: Record<CardLang, string> = { en: "English", zh: "中文" };

/** A reason the reader can act on.
 *
 * `fetch` rejects with a bare `TypeError: Failed to fetch` for every network
 * failure — offline, DNS, CORS, server unreachable — and showing that string
 * verbatim tells a user nothing and gives them nothing to do. Backend errors
 * carry a real `detail` and are worth surfacing as-is; network failures are
 * worth translating. */
function explain(e: unknown): string {
  if (e instanceof TypeError) return "Couldn't reach the server. Check your connection and try again.";
  const msg = e instanceof Error ? e.message.trim() : "";
  return msg || "Something went wrong building the card.";
}

export function ShareCardButton({ market = "US" }: { market?: string }) {
  const [open, setOpen] = useState(false);
  const [lang, setLang] = useState<CardLang>("en");
  const [available, setAvailable] = useState<CardLang[]>(["en"]);
  /** Whether the capability probe has answered. Generation waits for it: a
   *  fast click would otherwise fire in the default language before the
   *  backend has said which ones it can actually draw. */
  const [probed, setProbed] = useState(false);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [tradingDate, setTradingDate] = useState<string | null>(null);

  // Probe on first open, not on mount. This component sits on the home page,
  // so probing on mount would cost every visitor a request to support the few
  // who actually share. The extra latency lands on a click that is already
  // waiting on card generation.
  useEffect(() => {
    if (!open || probed) return;
    let cancelled = false;
    getDailyCardLanguages()
      .then((r) => {
        if (cancelled || !r.languages?.length) return;
        setAvailable(r.languages);
        // Don't strand the user on a language the backend just said it can't
        // draw — if the current pick vanished, fall back to the first offered.
        setLang((cur) => (r.languages.includes(cur) ? cur : r.languages[0]));
      })
      .catch(() => {
        /* Capability probe only. English is bundled and always drawable, so a
           failed probe degrades to English rather than blocking the button. */
      })
      .finally(() => {
        if (!cancelled) setProbed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open, probed]);

  const generate = useCallback(
    async (which: CardLang) => {
      setStatus("loading");
      setError(null);
      try {
        const card = await createDailyCard(which, market);
        setTradingDate(card.trading_date);
        // Cache-bust per language so switching doesn't show the previous
        // card's bytes from the browser cache — the PNG is served immutable.
        setImageUrl(`${dailyCardImageUrl(which, card.trading_date)}`);
        setStatus("ready");
      } catch (e) {
        setError(explain(e));
        setStatus("error");
      }
    },
    [market],
  );

  const openSheet = useCallback(() => setOpen(true), []);

  // Generation waits for the probe. Firing on click instead would race it:
  // a fast click generates in the default language before the backend has
  // said which languages it can draw — English if English isn't drawable is
  // a 503, and the wrong language even when it isn't.
  useEffect(() => {
    if (open && probed && status === "idle") void generate(lang);
  }, [open, probed, status, lang, generate]);

  const pick = useCallback(
    (next: CardLang) => {
      if (next === lang) return;
      setLang(next);
      void generate(next);
    },
    [generate, lang],
  );

  return (
    <>
      <button
        type="button"
        onClick={openSheet}
        data-testid="share-card-button"
        className="rounded-md border border-border px-2 py-1 text-[11px] font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        Share
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Share today's market card"
          data-testid="share-card-sheet"
          onClick={() => setOpen(false)}
        >
          <div
            className="flex max-h-[90vh] w-full max-w-sm flex-col gap-3 overflow-y-auto rounded-lg bg-card p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-heading text-base font-semibold">Today&apos;s card</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="rounded px-2 text-lg leading-none text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </div>

            {/* One drawable language means no choice to make. */}
            {available.length > 1 && (
              <div className="flex gap-1" data-testid="share-card-langs">
                {available.map((l) => (
                  <button
                    key={l}
                    type="button"
                    onClick={() => pick(l)}
                    aria-pressed={l === lang}
                    className={`rounded-md border px-2 py-1 text-xs transition-colors ${
                      l === lang
                        ? "border-foreground bg-foreground text-background"
                        : "border-border text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    {LABELS[l]}
                  </button>
                ))}
              </div>
            )}

            {status === "loading" && (
              <div
                className="flex aspect-[3/4] items-center justify-center rounded-md border border-border bg-muted text-center text-xs text-muted-foreground"
                data-testid="share-card-loading"
              >
                {/* The honest version of a spinner: the first click of the day
                    really is slow, and saying so beats looking hung. */}
                Drawing today&apos;s card — the first one each day takes a moment.
              </div>
            )}

            {status === "error" && (
              <div
                className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs"
                data-testid="share-card-error"
              >
                <p className="font-semibold">Couldn&apos;t build today&apos;s card.</p>
                <p className="mt-1 text-muted-foreground">{error}</p>
                <button
                  type="button"
                  onClick={() => void generate(lang)}
                  className="mt-2 rounded border border-border px-2 py-1 font-semibold hover:bg-muted"
                >
                  Try again
                </button>
              </div>
            )}

            {status === "ready" && imageUrl && (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element -- the
                    PNG is served by the API on another origin and is already
                    sized for sharing; next/image would proxy it for nothing. */}
                <img
                  src={imageUrl}
                  alt="Today's market snapshot card"
                  data-testid="share-card-image"
                  className="w-full rounded-md border border-border"
                />
                <div className="flex gap-2">
                  <a
                    href={imageUrl}
                    download={`livermore-${tradingDate ?? "card"}-${lang}.png`}
                    className="flex-1 rounded-md bg-foreground px-3 py-2 text-center text-xs font-semibold text-background hover:opacity-90"
                  >
                    Download
                  </a>
                  <button
                    type="button"
                    onClick={() => void navigator.clipboard?.writeText(imageUrl)}
                    className="flex-1 rounded-md border border-border px-3 py-2 text-xs font-semibold hover:bg-muted"
                  >
                    Copy link
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
