"use client";

/**
 * Landing surface for an ENTRY signal's action link (`?action=entered`).
 *
 * `signal_cron` has always detected entries — `flip_to_long` is the entry
 * signal, and it emails and banners like any other change. But until
 * 2026-08-19 its action link pointed at `?action=executed`, the same target
 * an EXIT sends. So a user told "your strategy entered NVDA" clicked
 * through and met a prompt reading "nothing has been sold… confirm what you
 * sold": wrong verb, wrong control, and the one thing they needed was never
 * offered.
 *
 * WHY THAT MATTERED BEYOND COPY. An entry that never becomes a declared
 * `PositionState` is invisible to the exit monitor. The stop and targets
 * the user configured never run on the trade they were configured for — the
 * strategy notices the entry, the user takes it, and the exit half of the
 * loop simply never engages. This prompt is the join between the two.
 *
 * It routes rather than transacting, for the same reason the exit prompt
 * does: declaring a position needs the user's real fill — symbol, shares,
 * entry price — and inventing those numbers would seed the ladder against
 * a position that never existed. `<DeclarePositionForm>` already collects
 * them on the dashboard below.
 *
 * COPY. §11 register: report what the rule did, hand the decision back.
 */

import { useState } from "react";
import { useSearchParams } from "next/navigation";

export function EnteredFromEmail({ strategyId }: { strategyId: string }) {
  const searchParams = useSearchParams();
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;
  if (searchParams?.get("action") !== "entered") return null;

  function scrollToDeclare() {
    document
      .querySelector("[data-testid='active-execution-dashboard']")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div
      data-testid="entered-from-email"
      data-strategy-id={strategyId}
      className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50/60 px-4 py-3"
    >
      <p className="text-sm font-semibold text-slate-900">
        Track what you bought
      </p>
      <p className="mt-0.5 text-[13px] leading-snug text-slate-600">
        Livermore did not buy anything — we do not place trades. Recording
        the position with the shares and price you actually paid is what
        starts the exit ladder watching it.
      </p>
      <div className="mt-2.5 flex items-center gap-3">
        <button
          type="button"
          onClick={scrollToDeclare}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-[13px] font-medium text-slate-800 transition hover:bg-slate-50"
        >
          Record the position
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-[12px] font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline"
        >
          I didn&apos;t take it
        </button>
      </div>
    </div>
  );
}
