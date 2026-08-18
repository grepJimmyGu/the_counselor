"use client";

/**
 * Landing surface for the exit email's confirm link.
 *
 * `position_event` emails have always built
 * `{site}/strategies/{id}?action=executed` (`emails/position_event.py`), and
 * until 2026-08-18 nothing on the web read that parameter. The link dropped
 * the user on the strategy page with no acknowledgement that they had
 * clicked "I've executed this" and no control to finish the job — so the
 * one-click confirm in every exit email did nothing at all, and the
 * position's `shares_remaining` stayed stale.
 *
 * That staleness is not cosmetic: the suggested size for the NEXT tier is
 * capped by `shares_remaining`, so an unconfirmed exit makes the next
 * alert's share count describe a position the user no longer holds.
 *
 * Rendered only when the parameter is present, so it costs a normal visitor
 * nothing.
 *
 * COPY. §11 register — report what the rule did and hand the decision back.
 * Never "you should", never the word "advice", and never imply Livermore
 * sold anything.
 */

import { useState } from "react";
import { useSearchParams } from "next/navigation";

import { MarkAsExecutedButton } from "@/components/notifications/mark-as-executed-button";

export function ExecutedFromEmail({ strategyId }: { strategyId: string }) {
  const searchParams = useSearchParams();
  const [dismissed, setDismissed] = useState(false);
  const [marked, setMarked] = useState(false);

  if (dismissed) return null;
  if (searchParams?.get("action") !== "executed") return null;

  return (
    <div
      data-testid="executed-from-email"
      className="mb-6 rounded-xl border border-amber-200 bg-amber-50/60 px-4 py-3"
    >
      {marked ? (
        <p className="text-sm text-slate-700">
          Recorded. Your remaining position updates from here.
        </p>
      ) : (
        <>
          <p className="text-sm font-semibold text-slate-900">
            Did you act on this exit?
          </p>
          <p className="mt-0.5 text-[13px] leading-snug text-slate-600">
            Nothing has been sold by Livermore — we do not place trades.
            Confirming records what you did in your own brokerage so the
            remaining position stays accurate.
          </p>
          <div className="mt-2.5 flex items-center gap-3">
            <MarkAsExecutedButton
              strategyId={strategyId}
              onMarked={() => setMarked(true)}
            />
            <button
              type="button"
              onClick={() => setDismissed(true)}
              className="text-[12px] font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline"
            >
              I&apos;m holding
            </button>
          </div>
        </>
      )}
    </div>
  );
}
