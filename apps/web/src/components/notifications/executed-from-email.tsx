"use client";

/**
 * Landing surface for the exit email's confirm link.
 *
 * `position_event` emails have always built
 * `{site}/strategies/{id}?action=executed` (`emails/position_event.py`), and
 * until 2026-08-18 nothing on the web read that parameter. The link dropped
 * the user on the strategy page with no acknowledgement that they had
 * clicked "I've executed this" and no route to finish the job — so the
 * one-click confirm in every exit email did nothing, and the position's
 * `shares_remaining` stayed stale.
 *
 * That staleness is not cosmetic: the suggested size for the NEXT tier is
 * capped by `shares_remaining`, so an unconfirmed exit makes the following
 * alert's share count describe a position the user no longer holds.
 *
 * WHY THIS DOES NOT OFFER A ONE-CLICK CONFIRM. Two endpoints look like they
 * confirm an exit and only one does:
 *
 *   - `POST /{id}/mark-executed` is a RETENTION METRIC. It writes a
 *     `MarkAsExecutedEvent`, never touches `shares_remaining`, and 404s
 *     unless a `SignalEvent` exists — which the position monitors never
 *     write. On a position-only strategy it fails outright.
 *   - `POST /{id}/positions/{pid}/confirm-exit` is the real one, and it is
 *     "the ONLY path that mutates shares_remaining".
 *
 * `confirm-exit` needs the user's ACTUAL fill — which tier, how many
 * shares, at what price. A single button cannot supply that, and inventing
 * the numbers would corrupt the position's P&L with a fill that never
 * happened. So this prompt does the one honest thing: acknowledges why the
 * user is here and sends them to the position card, where the existing
 * confirm affordance collects the real numbers.
 *
 * COPY. §11 register — report what the rule did and hand the decision back.
 * Never "you should", never the word "advice", never imply Livermore sold.
 */

import { useState } from "react";
import { useSearchParams } from "next/navigation";

export function ExecutedFromEmail({ strategyId }: { strategyId: string }) {
  const searchParams = useSearchParams();
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;
  if (searchParams?.get("action") !== "executed") return null;

  function scrollToPositions() {
    document
      .querySelector("[data-testid='active-execution-dashboard']")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div
      data-testid="executed-from-email"
      data-strategy-id={strategyId}
      className="mb-6 rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3"
    >
      <p className="text-sm font-semibold text-slate-900">
        Recording what you did
      </p>
      <p className="mt-0.5 text-[13px] leading-snug text-slate-600">
        Nothing has been sold by Livermore — we do not place trades. Confirm
        on the position below with the shares and price you actually got, so
        what&apos;s left stays accurate.
      </p>
      <div className="mt-2.5 flex items-center gap-3">
        <button
          type="button"
          onClick={scrollToPositions}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-800 transition hover:bg-slate-50"
        >
          Go to the position
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-[12px] font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline"
        >
          I&apos;m holding
        </button>
      </div>
    </div>
  );
}
