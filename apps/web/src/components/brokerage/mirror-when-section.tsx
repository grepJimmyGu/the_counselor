"use client";

/**
 * The Mirror's WHEN section — PRD-43a §3.7.1 Zone 3, deepened by PRD-43b P0.
 *
 * "Did I enter and exit at the right time?" — the user's question, not the
 * lens's name. Of the trichotomy (WHAT / WHEN / HOW MUCH) this is the only
 * section that carries a dollar today, and the only one whose lens has
 * shipped.
 *
 * THREE RULES, and each exists because breaking it produced a wrong finding
 * on a real account:
 *
 *   1. A NOISE PROFILE RENDERS AS NOISE. When every horizon's quartiles
 *      straddle zero, the medians mean nothing, and the section says "no
 *      consistent timing pattern" — which is itself a useful finding. The
 *      first live account looked exactly like this, and letting a diagnosis
 *      be read out of its medians was the v1 script's worst defect. The
 *      box plot exists so the dispersion is visible, not just asserted.
 *
 *   2. EVERY NUMBER CARRIES ITS N. A 126-trade record split by setup gives
 *      16-trade cells. A row without its sample size cannot be read safely,
 *      and low-N rows are shown but never promoted.
 *
 *   3. THE MEASURED SHARE IS STATED. `price_bars` holds no ETFs or ADRs, so
 *      a user who trades them gets a profile computed on part of their
 *      record — 33 of 57 episodes on the first live account, omitting their
 *      most-traded symbol. Saying "your trades" when we measured 58% of them
 *      is the kind of quiet overreach this whole packet exists to avoid.
 *
 * Nothing here is market evidence. Every figure is measured on this user's
 * own episodes, and the copy never lets that read as a validated edge.
 */

import { useEffect, useState } from "react";

import { getMirrorTiming } from "@/lib/api";
import type { MarkoutProfile, TimingView } from "@/lib/contracts";
import { SaveRuleButton } from "@/components/rules/save-rule-button";

function money(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString(undefined, {
    maximumFractionDigits: 0,
  })}`;
}

function signedPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const s = (v * 100).toFixed(digits);
  return v > 0 ? `+${s}%` : `${s}%`.replace("-", "−");
}

/** Copy for the retrospective diagnoses. These name what happened; none of
 *  them may become a trading rule (PRD-43b §3.6.2). */
const LEAK_LABEL: Record<string, string> = {
  giveback: "letting a gain come back",
  panic_exit: "selling into a drawdown that recovered",
  premature_exit: "selling before the move finished",
  early_entry: "buying a good idea a week early",
  chased: "buying after a run had already stretched",
  efficient_stop: "cutting a loser that kept falling",
  trend_exhaustion_exit: "exiting as momentum faded",
};

const SETUP_LABEL: Record<string, string> = {
  extended_momentum: "Extended momentum",
  pullback: "Pullback",
  breakout: "Breakout",
  oversold: "Oversold",
  trend_continuation: "Trend continuation",
  unclassified: "Matched no setup",
};

/** One horizon as a box plot: the interquartile band, a median tick, and a
 *  zero line. Reading a median without its dispersion is how a noise profile
 *  becomes a finding, so the two are never separable here. */
function MarkoutRow({
  horizon,
  n,
  median,
  q1,
  q3,
  scale,
}: {
  horizon: number;
  n: number;
  median?: number | null;
  q1?: number | null;
  q3?: number | null;
  scale: number;
}) {
  const has = q1 !== null && q1 !== undefined && q3 !== null && q3 !== undefined;
  // Map a return onto 0–100% of the track, with zero pinned at the centre.
  const at = (v: number) => 50 + (v / scale) * 50;
  const left = has ? Math.max(0, at(q1 as number)) : 50;
  const right = has ? Math.min(100, at(q3 as number)) : 50;
  const mid =
    median === null || median === undefined ? null : Math.min(100, Math.max(0, at(median)));

  return (
    <div
      className="grid grid-cols-[2.2rem_1fr_3.6rem_2.4rem] items-center gap-2 py-1"
      data-testid={`when-markout-${horizon}`}
    >
      <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
        {horizon}D
      </span>
      <div className="relative h-4 rounded-sm bg-muted/40">
        {/* Zero line. Everything is read against this, so it is drawn first
            and never hidden behind the band. */}
        <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border" />
        {has && (
          <div
            className="absolute inset-y-[3px] rounded-[2px] bg-foreground/15"
            style={{ left: `${left}%`, width: `${Math.max(right - left, 0.8)}%` }}
          />
        )}
        {mid !== null && (
          <div
            className="absolute inset-y-0 w-[2px] -translate-x-1/2 rounded-full bg-foreground"
            style={{ left: `${mid}%` }}
          />
        )}
      </div>
      <span className="text-right font-mono text-[11px] tabular-nums text-foreground">
        {signedPct(median)}
      </span>
      <span className="text-right font-mono text-[11px] tabular-nums text-muted-foreground">
        n={n}
      </span>
    </div>
  );
}

function MarkoutBlock({
  title,
  caption,
  profile,
  testid,
}: {
  title: string;
  caption: string;
  profile: MarkoutProfile;
  testid: string;
}) {
  const rows = profile.horizons.filter((h) => h.n > 0);
  if (rows.length === 0) return null;

  const scale = Math.max(
    0.02,
    ...rows.flatMap((h) => [Math.abs(h.q1 ?? 0), Math.abs(h.q3 ?? 0)]),
  );

  return (
    <div data-testid={testid}>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </div>
      {/* THE HONESTY BRANCH. When the quartiles cross zero at every horizon
          there is no pattern to describe, and the medians are noise. Saying so
          is a finding; extracting a story from them is not. */}
      {profile.has_consistent_pattern ? (
        <p className="mt-1 text-[13px] text-muted-foreground">{caption}</p>
      ) : (
        <p className="mt-1 text-[13px] text-muted-foreground" data-testid={`${testid}-noise`}>
          No consistent timing pattern — the spread of outcomes crosses zero at
          every horizon, so the middle values below aren&apos;t telling you
          anything you could act on.
        </p>
      )}
      <div className="mt-2">
        {rows.map((h) => (
          <MarkoutRow key={h.horizon} scale={scale} {...h} />
        ))}
      </div>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Bar spans the middle half of outcomes; the tick is the median. Measured
        in trading days after the fill.
      </p>
    </div>
  );
}

export function MirrorWhenSection({ backendToken }: { backendToken: string }) {
  const [data, setData] = useState<TimingView | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    getMirrorTiming(backendToken)
      .then((t) => {
        if (live) setData(t);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [backendToken]);

  // Fails quietly: this is the DEEP view of a section whose summary rendered
  // above it from a different endpoint. Losing the depth should not take the
  // summary with it.
  if (failed || !data) return null;

  const cov = data.coverage;
  if (cov.episodes_analysed === 0) return null;

  const ex = data.excursions;
  const leak = data.leaks[0];
  const setups = data.setups.filter((s) => s.n > 0);
  const partial = cov.episodes_analysed < cov.episodes_total;

  return (
    <div className="space-y-4 border-t border-border pt-4" data-testid="when-deep">
      <MarkoutBlock
        testid="when-entry-profile"
        title="After you buy"
        caption="What the stock did in the days after your opening purchases."
        profile={data.opening_entry_profile}
      />

      <MarkoutBlock
        testid="when-exit-profile"
        title="After you sell"
        caption="Scored so that a stock rising after you sell counts against the exit."
        profile={data.final_exit_profile}
      />

      {/* The paired statistic that teaches the most — and the one that must
          never be read alone. A stop set between these two numbers can still
          kill a quarter of the winners, which is why the exclusion note and
          the sample sizes sit right next to it. */}
      {(ex.winner_n > 0 || ex.loser_n > 0) && (
        <div data-testid="when-excursions">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            How far they went against you
          </div>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-[11px] text-muted-foreground">
                Trades that worked
              </div>
              <div className="font-mono text-lg font-semibold tabular-nums text-foreground">
                {signedPct(ex.winner_mae)}
              </div>
              <div className="text-[11px] text-muted-foreground">
                n={ex.winner_n}
              </div>
            </div>
            <div className="rounded-md border border-border px-3 py-2">
              <div className="text-[11px] text-muted-foreground">
                Trades that didn&apos;t
              </div>
              <div className="font-mono text-lg font-semibold tabular-nums text-foreground">
                {signedPct(ex.loser_mae)}
              </div>
              <div className="text-[11px] text-muted-foreground">
                n={ex.loser_n}
              </div>
            </div>
          </div>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Deepest drawdown while you held.
            {ex.same_day_excluded > 0 && (
              <span data-testid="when-sameday-note">
                {" "}
                {ex.same_day_excluded}{" "}
                {ex.same_day_excluded === 1 ? "position" : "positions"} opened and
                closed the same day {ex.same_day_excluded === 1 ? "is" : "are"} left
                out — we know the day&apos;s range, not where in it you were.
              </span>
            )}
          </p>
        </div>
      )}

      {/* setup_type CONDITIONING the outcome measures. Legitimate, and the
          engine's most valuable output. What would not be legitimate is a
          category defined by its own consequences. */}
      {setups.length > 0 && (
        <div data-testid="when-setups">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            What you were buying into
          </div>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="pb-1 font-medium">Setup</th>
                  <th className="pb-1 text-right font-medium">Trades</th>
                  <th className="pb-1 text-right font-medium">Worked</th>
                  <th className="pb-1 text-right font-medium">Median</th>
                  <th className="pb-1" />
                </tr>
              </thead>
              <tbody>
                {setups.map((s) => (
                  <tr
                    key={s.setup}
                    className="border-t border-border"
                    data-testid={`when-setup-${s.setup}`}
                  >
                    <td className="py-1.5 text-foreground">
                      {SETUP_LABEL[s.setup] ?? s.setup}
                    </td>
                    <td className="py-1.5 text-right font-mono tabular-nums text-muted-foreground">
                      {s.n}
                    </td>
                    <td className="py-1.5 text-right font-mono tabular-nums text-foreground">
                      {s.wins}
                    </td>
                    <td className="py-1.5 text-right font-mono tabular-nums text-foreground">
                      {signedPct(s.median_return)}
                    </td>
                    <td className="py-1.5 pl-3 text-right">
                      {/* Only for a NAMED setup. "Matched no setup" is not a
                          category (43b §3.6.1), so there is nothing to make a
                          rule about — offering one would invent the category
                          the taxonomy deliberately withholds. */}
                      {s.setup !== "unclassified" && (
                        <SaveRuleButton
                          backendToken={backendToken}
                          testid={`when-save-setup-${s.setup}`}
                          label="Save a rule"
                          rule={{
                            rule_type: "entry",
                            scope: "behavioural",
                            source: "trade_analysis",
                            name: `Think twice about ${(SETUP_LABEL[s.setup] ?? s.setup).toLowerCase()} entries`,
                            // A behavioural rule enters a Playbook as an
                            // EXCLUSION, never as an edge (§3.1.1) — so what
                            // is stored is the setup to avoid, not a market
                            // condition it never earned the right to assert.
                            conditions: { exclude_setup: s.setup },
                            sample_size: s.n,
                            historical_effect: `${s.wins} of ${s.n} worked${
                              s.median_return !== null && s.median_return !== undefined
                                ? `, ${signedPct(s.median_return)} median`
                                : ""
                            }`,
                            confidence: s.n >= 10 ? "medium" : "low",
                          }}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Named categories cover only part of a real record by design, and
              the remainder is information rather than a gap to paper over. */}
          {cov.unclassified_share !== null &&
            cov.unclassified_share !== undefined &&
            cov.unclassified_share > 0 && (
              <p className="mt-1 text-[11px] text-muted-foreground" data-testid="when-unclassified">
                {Math.round(cov.unclassified_share * 100)}% of your entries
                matched none of these — they aren&apos;t a category, so they
                aren&apos;t given one.
              </p>
            )}
        </div>
      )}

      {leak && leak.dollars > 0 && (
        <div
          className="rounded-md border border-border bg-muted/30 px-3 py-2.5"
          data-testid="when-leak"
        >
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Costliest habit
          </div>
          <p className="mt-1 text-[13px] text-foreground">
            <span className="font-mono font-semibold tabular-nums">
              {money(leak.dollars)}
            </span>{" "}
            across {leak.n} {leak.n === 1 ? "trade" : "trades"} —{" "}
            {LEAK_LABEL[leak.key] ?? leak.key.replace(/_/g, " ")}.
          </p>
          <div className="mt-2">
            <SaveRuleButton
              backendToken={backendToken}
              testid="when-save-leak"
              rule={{
                rule_type: "exit",
                scope: "behavioural",
                source: "trade_analysis",
                name: `Watch for ${LEAK_LABEL[leak.key] ?? leak.key.replace(/_/g, " ")}`,
                conditions: { avoid_outcome: leak.key },
                sample_size: leak.n,
                historical_effect: `${money(leak.dollars)} across ${leak.n} ${
                  leak.n === 1 ? "trade" : "trades"
                }`,
                confidence: leak.n >= 10 ? "medium" : "low",
              }}
            />
          </div>
        </div>
      )}

      {/* What this was computed ON. `price_bars` carries no ETFs or ADRs, so
          for some users this is a large share and the number has to be visible
          rather than implied away. */}
      <p className="text-[11px] text-muted-foreground" data-testid="when-coverage">
        Measured on {cov.episodes_analysed} of {cov.episodes_total} closed
        positions across {cov.symbols_measured}{" "}
        {cov.symbols_measured === 1 ? "symbol" : "symbols"}
        {partial && ". The rest are symbols we hold no price history for"}.
      </p>
    </div>
  );
}
