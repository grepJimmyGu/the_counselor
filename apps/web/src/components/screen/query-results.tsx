"use client";

/**
 * Query results — the landing page for a screen (item D, 2026-08-09).
 *
 * Jimmy's routing decision: this is a NEW surface standing alongside
 * `/stocks`, not a replacement. Both converge on the same destination:
 *
 *     query  -> here     -> click a row -> /stocks/[ticker]
 *     browse -> /stocks  -> click a row -> /stocks/[ticker]
 *
 * State lives in the URL (`?q=...&universe=...`) rather than in flow context,
 * so a result is shareable and survives a refresh — the two things people
 * actually do with a screen they like.
 *
 * PER-CONDITION COUNTS ARE FETCHED IN PARALLEL. The reference UI shows a count
 * beside each condition (`量比大于等于1 (2377个)`), which is one
 * `/api/screen/count` per condition — and that endpoint is ~1.9s warm, despite
 * its schema comment claiming sub-100ms. Six conditions run serially would be
 * a twelve-second page. They fire together and land as they arrive.
 */

import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useSession } from "next-auth/react";
import { ArrowUpDown, Plus, X } from "lucide-react";

import { parseSearch, screenScan, screenCount } from "@/lib/api";
import type { ScreenScanResponse, StrategyRule } from "@/lib/contracts";

interface ConditionChip {
  /** The plain-English reading, e.g. "RSI below 30 (oversold)". */
  reading: string;
  rule: StrategyRule;
  /** How many names this condition matches ALONE. undefined = still loading. */
  count?: number;
  /** Distinguishes "still counting" from "counted, and it failed". */
  countFailed?: boolean;
}

export function QueryResults({
  query,
  universeId,
}: {
  query: string;
  universeId: string;
}) {
  const router = useRouter();
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as { backendToken?: string } | null)?.backendToken;

  const [chips, setChips] = useState<ConditionChip[]>([]);
  const [scan, setScan] = useState<ScreenScanResponse | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // Parse → scan. Both are anonymous-capable, but pass the token when we have
  // one so a signed-in user gets their own tier's limits (trap #19).
  useEffect(() => {
    if (sessionStatus === "loading") return;
    let live = true;

    (async () => {
      setLoading(true);
      setNote(null);
      try {
        const parsed = await parseSearch(query, universeId);
        if (!live) return;

        if (parsed.intent !== "screen" || !parsed.screen) {
          setNote(parsed.note ?? "That didn't resolve to a screen.");
          setChips([]);
          setScan(null);
          return;
        }

        const rules = parsed.screen.rules ?? [];
        const readings = parsed.screen.readings ?? [];
        setNote(parsed.note ?? null);
        setChips(
          rules.map((rule, i) => ({
            reading: readings[i] ?? rule.primitive_id ?? `condition ${i + 1}`,
            rule,
          })),
        );

        const result = await screenScan(
          {
            universe_id: parsed.screen.universe_id,
            rules,
            symbols: parsed.screen.symbols?.length ? parsed.screen.symbols : undefined,
          },
          { backendToken },
        );
        if (live) setScan(result);
      } catch {
        if (live) setNote("Couldn't run that screen. Try again.");
      } finally {
        if (live) setLoading(false);
      }
    })();

    return () => {
      live = false;
    };
  }, [query, universeId, sessionStatus, backendToken]);

  // Per-condition counts, in parallel. Each lands independently so one slow or
  // failing condition never holds up the others.
  useEffect(() => {
    if (chips.length === 0) return;
    let live = true;

    chips.forEach((chip, i) => {
      if (chip.count !== undefined || chip.countFailed) return;
      screenCount({ universe_id: universeId, rules: [chip.rule] }, { backendToken })
        .then((r) => {
          if (!live) return;
          setChips((prev) =>
            prev.map((c, j) => (j === i ? { ...c, count: r.matched_count } : c)),
          );
        })
        .catch(() => {
          if (!live) return;
          // Mark it rather than leaving a spinner forever — a chip that never
          // resolves reads as the page being broken.
          setChips((prev) => prev.map((c, j) => (j === i ? { ...c, countFailed: true } : c)));
        });
    });

    return () => {
      live = false;
    };
    // Only re-run when the SET of conditions changes, not when a count lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chips.length, query, universeId, backendToken]);

  /** Dropping a condition re-runs the screen with the rest. */
  const removeChip = useCallback(
    (index: number) => {
      const kept = chips.filter((_, i) => i !== index);
      if (kept.length === 0) {
        router.push("/" as Route);
        return;
      }
      // Rebuild the query from the readings we kept. The query text is the
      // source of truth on submit, so editing it — not the rule array — is
      // what keeps this page consistent with the box.
      const next = kept.map((c) => c.reading).join(" and ");
      router.push(`/screen?q=${encodeURIComponent(next)}&universe=${universeId}` as Route);
    },
    [chips, router, universeId],
  );

  // One column per screened condition. Deduped by primitive: two rules on the
  // same primitive (RSI > 30 and RSI < 70) read the same value, so a second
  // identical column would be noise.
  const columns = useMemo(() => {
    const seen = new Set<string>();
    const out: { primitiveId: string; label: string }[] = [];
    chips.forEach((c) => {
      const pid = c.rule.primitive_id;
      if (!pid || seen.has(pid)) return;
      seen.add(pid);
      out.push({ primitiveId: pid, label: c.reading });
    });
    return out;
  }, [chips]);

  const rows = useMemo(() => {
    if (!scan) return [];
    const vals = scan.values ?? {};
    const base = scan.matched.map((symbol) => ({
      symbol,
      readings: scan.readings[symbol] ?? [],
      values: vals[symbol] ?? {},
    }));
    if (!sortBy) return base;
    return [...base].sort((a, b) => {
      const av = a.values[sortBy];
      const bv = b.values[sortBy];
      // Names without a value sink to the bottom in BOTH directions — they
      // aren't "lowest", they're unknown, and floating them to the top of an
      // ascending sort would read as though they scored zero.
      if (av === undefined && bv === undefined) return 0;
      if (av === undefined) return 1;
      if (bv === undefined) return -1;
      return sortDir === "asc" ? av - bv : bv - av;
    });
  }, [scan, sortBy, sortDir]);

  const toggleSort = useCallback(
    (primitiveId: string) => {
      if (sortBy === primitiveId) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortBy(primitiveId);
        setSortDir("desc");
      }
    },
    [sortBy],
  );

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-8" data-testid="query-results">
      <Link href={"/" as Route} className="text-sm text-muted-foreground hover:text-foreground">
        ← New search
      </Link>

      <h1 className="mt-3 font-heading text-2xl font-bold">{query}</h1>

      {/* Conditions, each with its own match count and a way to drop it. */}
      {chips.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2" data-testid="condition-chips">
          {chips.map((c, i) => (
            <span
              key={`${c.reading}-${i}`}
              data-testid="condition-chip"
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-white px-3 py-1 text-sm"
            >
              {c.reading}
              <span className="text-muted-foreground">
                {c.count !== undefined
                  ? `(${c.count.toLocaleString()})`
                  : c.countFailed
                    ? "(—)"
                    : "(…)"}
              </span>
              <button
                type="button"
                onClick={() => removeChip(i)}
                aria-label={`Remove ${c.reading}`}
                className="text-muted-foreground transition-colors hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}

          {/* The reference has "+ 添加条件" beside the chips. Without it the
              page is a dead end: you can narrow a screen but never widen it
              except by starting over. Goes back to the builder carrying the
              current query, so nothing is lost. */}
          <Link
            href={`/?q=${encodeURIComponent(query)}` as Route}
            data-testid="add-condition"
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            Add condition
          </Link>
        </div>
      )}

      <div className="mt-5 flex items-baseline gap-3">
        <span className="font-heading text-xl font-bold" data-testid="match-count">
          {loading ? "…" : `${scan?.matched_count ?? 0} match`}
        </span>
        {scan && (
          <span className="text-sm text-muted-foreground">
            of {scan.universe_size.toLocaleString()}
          </span>
        )}
        {scan?.as_of_date && (
          <span className="ml-auto text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            As of {scan.as_of_date}
          </span>
        )}
      </div>

      {note && <p className="mt-2 text-sm text-muted-foreground">{note}</p>}

      {/* Surfaced, never silent: a rule whose primitive isn't in the daily
          snapshot can't match, and the user would otherwise read the empty
          result as "nothing qualifies". */}
      {scan?.unsupported_primitives?.length ? (
        <p className="mt-2 text-sm text-amber-700" data-testid="unsupported-warning">
          Not screened: {scan.unsupported_primitives.join(", ")} — not in the daily
          snapshot yet.
        </p>
      ) : null}

      {loading ? (
        <div className="mt-6 space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-muted/50" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="mt-6 text-sm text-muted-foreground">
          No names match. Drop a condition above to widen it.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm" data-testid="results-table">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="w-10 py-2 font-medium">#</th>
                <th className="py-2 font-medium">Symbol</th>
                {columns.map((col) => (
                  <th key={col.primitiveId} className="py-2 font-medium">
                    <button
                      type="button"
                      onClick={() => toggleSort(col.primitiveId)}
                      data-testid={`sort-${col.primitiveId}`}
                      className="inline-flex items-center gap-1 transition-colors hover:text-foreground"
                    >
                      <span className="max-w-[14rem] truncate">{col.label}</span>
                      <ArrowUpDown
                        className={`h-3 w-3 shrink-0 ${
                          sortBy === col.primitiveId ? "text-primary" : "opacity-40"
                        }`}
                        aria-hidden="true"
                      />
                      <span className="sr-only">
                        {sortBy === col.primitiveId
                          ? `sorted ${sortDir === "asc" ? "ascending" : "descending"}`
                          : "sort by this"}
                      </span>
                    </button>
                    {/* Date stamps must be readable at a glance, not buried
                        (product invariant). Every column is as of the same
                        snapshot, so it's stated once per header row. */}
                    {scan?.as_of_date && (
                      <div className="mt-0.5 text-[10px] font-normal text-muted-foreground/70">
                        {scan.as_of_date}
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={r.symbol}
                  data-testid="result-row"
                  className="cursor-pointer border-b border-border/60 transition-colors hover:bg-muted/40"
                  onClick={() => router.push(`/stocks/${r.symbol}` as Route)}
                >
                  <td className="py-2.5 text-xs text-muted-foreground">{i + 1}</td>
                  <td className="py-2.5">
                    <Link
                      href={`/stocks/${r.symbol}` as Route}
                      className="font-mono font-semibold text-primary hover:underline"
                      onClick={(e: MouseEvent) => e.stopPropagation()}
                    >
                      {r.symbol}
                    </Link>
                  </td>
                  {columns.map((col) => {
                    const v = r.values[col.primitiveId];
                    return (
                      <td
                        key={col.primitiveId}
                        data-testid={`cell-${col.primitiveId}`}
                        className="py-2.5 tabular-nums"
                      >
                        {v === undefined ? (
                          // Absent, not zero. Rendering 0 would look like a
                          // real reading and sort as the lowest value.
                          <span className="text-muted-foreground/50">—</span>
                        ) : (
                          v.toFixed(2)
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
