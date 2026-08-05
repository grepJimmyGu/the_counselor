"use client";

/**
 * <ConditionBuilder> — the 6-category condition panel (v3.1 §4, 問財 pattern).
 *
 * Replaces the catalog browser that used to open behind "Conditions". That was
 * a LIBRARY view built for the composer: it listed primitives and, on pick,
 * appended a bare name like "RSI", leaving the user to supply the value or go
 * to another surface. This is a BUILDER — six columns of pills, each opening a
 * dropdown of concrete choices, and every pick writes a complete, readable
 * condition into the query.
 *
 * The query text stays the single source of truth: each phrase is chosen to
 * round-trip through the backend's `screen_rule_parser`, so submitting the box
 * re-parses exactly what you see. The rules carried alongside exist only to
 * drive the live match count without a round trip through the parser.
 *
 * LIVE COUNT, HONESTLY SCOPED: `/api/screen/count` measures ~1.9s warm in
 * production (its schema comment claims sub-100ms; that is not what it does).
 * So the count updates on a debounce AFTER each selection — it deliberately
 * does not chase keystrokes, because a number that lags the input reads as
 * broken.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Loader2, X } from "lucide-react";

import { screenCount } from "@/lib/api";
import {
  CONDITION_GROUPS,
  type ConditionOption,
} from "@/lib/condition-groups";
import type { StrategyRule } from "@/lib/contracts";
import { cn } from "@/lib/utils";

const COUNT_DEBOUNCE_MS = 400;

interface Selected extends ConditionOption {
  uid: string;
  /** The pill this came from. A chip reading just "Under 15" or "Crossing
   *  down" doesn't say under-15 WHAT — the pill name is the missing half. */
  pillLabel: string;
}

export function ConditionBuilder({
  onAppend,
  universeId = "sp500",
}: {
  /** Append the chosen phrase to the query — the user's editable record. */
  onAppend: (phrase: string) => void;
  universeId?: string;
}) {
  const [openPill, setOpenPill] = useState<string | null>(null);
  const [selected, setSelected] = useState<Selected[]>([]);
  const [count, setCount] = useState<{ matched: number; universe: number } | null>(
    null,
  );
  const [counting, setCounting] = useState(false);
  const seq = useRef(0);

  const technicalRules: StrategyRule[] = selected
    .filter((s) => s.rule)
    .map((s, i) => ({
      ...(s.rule as object),
      logic_with_prior: i === 0 ? null : "AND",
    })) as StrategyRule[];

  const rulesKey = JSON.stringify(technicalRules);

  // Live count — debounced, and guarded by a sequence number so a slow earlier
  // response can't overwrite a newer one (the calls take ~2s, so overlap is
  // the normal case, not the edge case).
  useEffect(() => {
    if (technicalRules.length === 0) {
      setCount(null);
      setCounting(false);
      return;
    }
    const mine = ++seq.current;
    setCounting(true);
    const t = window.setTimeout(() => {
      screenCount({ universe_id: universeId, rules: technicalRules })
        .then((r) => {
          if (mine !== seq.current) return; // a newer request already won
          setCount({ matched: r.matched_count, universe: r.universe_size });
        })
        .catch(() => {
          if (mine === seq.current) setCount(null);
        })
        .finally(() => {
          if (mine === seq.current) setCounting(false);
        });
    }, COUNT_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rulesKey, universeId]);

  const choose = useCallback(
    (option: ConditionOption, pillLabel: string) => {
      setSelected((prev) => [
        ...prev,
        { ...option, pillLabel, uid: `${option.phrase}-${prev.length}` },
      ]);
      onAppend(option.phrase);
      setOpenPill(null);
    },
    [onAppend],
  );

  const fundamentalCount = selected.filter((s) => !s.rule).length;

  return (
    <div data-testid="condition-builder" className="flex flex-col gap-3">
      {/* Live count + what's selected */}
      {selected.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
          {selected.map((s) => (
            <span
              key={s.uid}
              data-testid="condition-chip"
              className="inline-flex items-center gap-1 rounded-full bg-primary/8 px-3 py-1 text-xs font-medium text-primary"
            >
              {s.pillLabel} · {s.label}
              <button
                type="button"
                onClick={() => setSelected((p) => p.filter((x) => x.uid !== s.uid))}
                aria-label={`Remove ${s.pillLabel} ${s.label}`}
                className="rounded-full p-0.5 hover:bg-primary/15"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
          <span
            data-testid="condition-count"
            className="ml-auto text-xs text-muted-foreground"
          >
            {counting ? (
              <span className="inline-flex items-center gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                counting…
              </span>
            ) : count ? (
              <>
                <span className="font-medium text-foreground">{count.matched}</span>
                {" of "}
                {count.universe} match
                {fundamentalCount > 0 && " (before fundamentals)"}
              </>
            ) : fundamentalCount > 0 && technicalRules.length === 0 ? (
              "run to see matches"
            ) : (
              "—"
            )}
          </span>
        </div>
      )}

      {/* The six columns */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-4 md:grid-cols-3 lg:grid-cols-6">
        {CONDITION_GROUPS.map((group) => (
          <div key={group.key} data-testid={`condition-group-${group.key}`}>
            <h4 className="mb-2 text-xs font-medium text-foreground">
              {group.label}
            </h4>
            <div className="flex flex-col gap-1.5">
              {group.pills.map((pill) => {
                const id = `${group.key}:${pill.label}`;
                const open = openPill === id;
                return (
                  <div key={id} className="relative">
                    <button
                      type="button"
                      onClick={() => setOpenPill(open ? null : id)}
                      aria-expanded={open}
                      data-testid={`condition-pill-${pill.label}`}
                      className={cn(
                        "inline-flex w-full items-center justify-between gap-1 rounded-full border px-3 py-1.5 text-xs transition-colors",
                        open
                          ? "border-primary bg-primary/5 text-primary"
                          : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
                      )}
                    >
                      <span className="truncate">{pill.label}</span>
                      <ChevronDown
                        className={cn("h-3 w-3 shrink-0 transition-transform", open && "rotate-180")}
                      />
                    </button>
                    {open && (
                      <div
                        data-testid={`condition-options-${pill.label}`}
                        className="absolute left-0 top-full z-30 mt-1 w-max min-w-full max-w-[220px] overflow-hidden rounded-lg border border-border bg-white shadow-lg"
                      >
                        {pill.options.map((option) => (
                          <button
                            key={option.label}
                            type="button"
                            onClick={() => choose(option, pill.label)}
                            className="block w-full px-3 py-2 text-left text-xs text-foreground transition-colors hover:bg-muted/60"
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
