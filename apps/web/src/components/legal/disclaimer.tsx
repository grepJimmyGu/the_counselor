"use client";

/**
 * The §11 disclaimer: short form visible, full text one click away.
 *
 * §11 of `build_specs/research_execution_v0_signals_and_alerts.md` specified
 * this placement and it was never implemented — what shipped was a short
 * footer hardcoded into three email templates, and the full text existed
 * nowhere a user could reach.
 *
 * FETCHED, NOT HARDCODED. The wording lives in
 * `apps/api/app/services/disclaimer.py` and is served from
 * `/api/legal/disclaimer`. Compliance copy that exists in two places
 * drifts, and the half nobody is looking at is the half that goes stale.
 *
 * WHAT CHANGED IN THE TEXT. The spec's original said "we do not know your
 * financial situation". Since the brokerage connection shipped, that is
 * false — and a disclaimer containing a false statement is worse than an
 * awkward one, because being true is the entire point of the artifact. The
 * replacement says the thing that carries the actual legal weight: we can
 * see connected holdings, and we do not use them to change what any
 * strategy says. That second half is enforced by
 * `tests/test_no_personalization_guard.py`, not merely claimed here.
 *
 * RENDERS NOTHING ON FAILURE. A disclaimer that shows a loading spinner or
 * an error where legal text should be is worse than absent — it reads as
 * broken exactly where a reader most needs confidence.
 */

import { useEffect, useState } from "react";

import { getDisclaimer } from "@/lib/api";
import type { DisclaimerText } from "@/lib/contracts";

export function Disclaimer({ className }: { className?: string }) {
  const [text, setText] = useState<DisclaimerText | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let live = true;
    getDisclaimer()
      .then((d) => {
        if (live) setText(d);
      })
      .catch(() => {
        /* stay silent rather than render an error where legal text goes */
      });
    return () => {
      live = false;
    };
  }, []);

  if (!text) return null;

  return (
    <div
      data-testid="disclaimer"
      className={className ?? "mt-4 border-t border-border pt-3"}
    >
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {text.short}{" "}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          data-testid="disclaimer-toggle"
          className="underline underline-offset-2 hover:text-foreground"
        >
          {expanded ? "Hide full disclaimer" : "Read full disclaimer"}
        </button>
      </p>
      {expanded && (
        <div data-testid="disclaimer-full" className="mt-2 space-y-2">
          {text.full.split("\n\n").map((para, i) => (
            <p
              key={i}
              className="text-[11px] leading-relaxed text-muted-foreground"
            >
              {para}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
