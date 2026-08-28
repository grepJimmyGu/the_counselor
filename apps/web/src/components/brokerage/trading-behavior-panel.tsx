"use client";

/**
 * "How you actually trade" — the user's own transaction log, read back to
 * them.
 *
 * The record already contains the answer to questions almost nobody can
 * answer about themselves: how often you're right, what you make when you
 * are, what you lose when you're not, and how long you sit with each. This
 * panel computes none of that — the backend does the FIFO lot matching — it
 * decides which of those numbers are worth a person's attention and which
 * claims the data cannot support.
 *
 * THREE RULES IT FOLLOWS, and they're the whole design:
 *
 *   1. WIN RATE NEVER APPEARS ALONE. A 70% win rate with a 0.25 win/loss
 *      ratio is a losing method, and the win rate on its own reads as praise.
 *      They render as one line or not at all.
 *
 *   2. A PATTERN IS SHOWN ONLY WHEN BOTH SIDES EXIST. `holds_losers_longer`
 *      is null when there are no wins or no losses; a two-trade history can't
 *      support "you hold your losers longer" and we don't say it.
 *
 *   3. WHAT'S EXCLUDED IS STATED. Sells of positions opened before the window
 *      have no knowable cost basis. They're counted, named, and left out of
 *      P/L rather than guessed at — and the panel says so, because a realised
 *      P/L that quietly omits your biggest sale is worse than no number.
 *
 * Nothing here scores the user or predicts anything. It reports.
 */

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { getTradingBehavior } from "@/lib/api";
import { MirrorWhenSection } from "@/components/brokerage/mirror-when-section";
import type { SymbolSummary, TradingBehavior } from "@/lib/contracts";

function money(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${(v * 100).toFixed(0)}%`;
}

function days(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  if (v < 1) return "same day";
  return v === 1 ? "1 day" : `${Math.round(v)} days`;
}

/** Copy for the roll-up's parts and the remedies. Kept next to the render so
 *  a new key added on the backend shows as its raw slug rather than silently
 *  vanishing from the sentence. */
const COMPONENT_LABEL: Record<string, string> = {
  exit_gap: "when you sold",
  fees: "fees",
  execution: "the prices you bought at",
};

const REMEDY_LABEL: Record<string, string> = {
  exit_rule: "An exit rule — decided in advance, so the sell isn't a judgement call in the moment.",
  entry_timing: "Entry timing — what the days after your buys actually did, so you can see whether the price or the week was the problem.",
};

function Stat({
  label,
  value,
  tone,
  testid,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad";
  testid?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-2.5">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        data-testid={testid}
        className={
          "mt-0.5 font-mono text-base font-semibold tabular-nums " +
          (tone === "bad"
            ? "text-rose-600"
            : tone === "good"
              ? "text-emerald-700"
              : "text-foreground")
        }
      >
        {value}
      </div>
    </div>
  );
}

function SymbolRow({ s }: { s: SymbolSummary }) {
  return (
    <tr className="border-t border-border" data-testid={`behavior-symbol-${s.symbol}`}>
      <td className="px-3 py-2 font-medium">{s.symbol}</td>
      <td className="px-3 py-2 text-right font-mono tabular-nums text-muted-foreground">
        {s.buys}/{s.sells}
      </td>
      <td className="px-3 py-2 text-right font-mono tabular-nums text-muted-foreground">
        {days(s.avg_holding_days)}
      </td>
      <td
        className={
          "px-3 py-2 text-right font-mono tabular-nums " +
          (s.realised_pnl < 0 ? "text-rose-600" : "text-emerald-700")
        }
      >
        {money(s.realised_pnl)}
      </td>
    </tr>
  );
}

function SymbolTable({
  title,
  rows,
  testid,
}: {
  title: string;
  rows: SymbolSummary[];
  testid: string;
}) {
  if (rows.length === 0) return null;
  return (
    <div>
      <h3 className="mb-1.5 text-[13px] font-semibold text-foreground">{title}</h3>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[24rem] border-collapse text-sm">
          <thead>
            <tr className="bg-muted/40 text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-3 py-2 text-left font-semibold">Symbol</th>
              <th className="px-3 py-2 text-right font-semibold">Buys/Sells</th>
              <th className="px-3 py-2 text-right font-semibold">Held</th>
              <th className="px-3 py-2 text-right font-semibold">Realised</th>
            </tr>
          </thead>
          <tbody data-testid={testid}>
            {rows.map((s) => (
              <SymbolRow key={s.symbol} s={s} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function TradingBehaviorPanel({
  backendToken,
  startDate,
}: {
  backendToken: string;
  /** Same window the trade list is showing. Passed in rather than chosen here
   *  so the summary can never describe a different period than the trades
   *  directly below it. */
  startDate: string;
}) {
  const [data, setData] = useState<TradingBehavior | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null);
    setFailed(false);
    getTradingBehavior(backendToken, { startDate })
      .then((b) => {
        if (live) setData(b);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [backendToken, startDate]);

  // Fails alone: this panel is an interpretation of the trade list below it,
  // and the list is still worth reading without it.
  if (failed) return null;

  if (!data) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (data.round_trips === 0) {
    return (
      <p data-testid="behavior-empty" className="text-[13px] text-muted-foreground">
        {data.total_buys > 0
          ? "You haven't closed a position in this window yet — nothing to measure until you sell."
          : "No trades in this window."}
      </p>
    );
  }

  // Only `split_unreconciled` exists today; reading the reason rather than
  // assuming it keeps the copy honest when a second reason is added.
  const excluded = (data.excluded ?? [])
    .filter(([, reason]) => reason === "split_unreconciled")
    .map(([symbol]) => symbol);

  const roll = data.recoverable;
  const gap = data.exit_gap;
  const xq = data.execution;

  const ratio = data.win_loss_ratio;
  // The sentence a person can act on. Ratio under 1 means the losses are
  // bigger than the wins, which is the finding regardless of win rate.
  const ratioLine =
    ratio === null || ratio === undefined
      ? null
      : ratio >= 1
        ? `Your average win (${money(data.avg_win)}) is ${ratio.toFixed(1)}× your average loss (${money(data.avg_loss)}).`
        : `Your average loss (${money(data.avg_loss)}) is ${(1 / ratio).toFixed(1)}× your average win (${money(data.avg_win)}).`;

  return (
    <div className="space-y-5" data-testid="behavior-panel">
      {/* ZONE 1 — the record. What happened, no counterfactual anywhere.
          Complete on its own, and what a Level-0 user came for. */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">

        <Stat
          label="Realised P/L"
          value={money(data.realised_pnl)}
          tone={data.realised_pnl < 0 ? "bad" : "good"}
          testid="behavior-realised"
        />
        <Stat
          label="Closed trades"
          value={String(data.round_trips)}
          testid="behavior-round-trips"
        />
        <Stat
          label="Win rate"
          value={`${pct(data.win_rate)} (${data.wins}W/${data.losses}L)`}
          testid="behavior-win-rate"
        />
        <Stat
          label="Typical hold"
          value={days(data.median_holding_days ?? data.avg_holding_days)}
          testid="behavior-hold"
        />
      </div>

      {/* Rule 1 — the win rate never stands on its own. */}
      {ratioLine && (
        <p
          data-testid="behavior-ratio"
          className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-[13px] text-foreground"
        >
          {ratioLine}
          {data.realised_pnl < 0 && (data.win_rate ?? 0) >= 0.5 && (
            <>
              {" "}
              <strong className="font-medium">
                You were right more often than not and still lost money over
                this window
              </strong>{" "}
              — the size of the losses, not how often they happen.
            </>
          )}
        </p>
      )}

      {/* Rule 2 — only when both sides exist. */}
      {data.holds_losers_longer !== null &&
        data.holds_losers_longer !== undefined && (
          <div
            data-testid="behavior-holding"
            className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-[13px]"
          >
            <div className="flex flex-wrap gap-x-6 gap-y-1">
              <span>
                Winners held{" "}
                <span className="font-mono tabular-nums">
                  {days(data.avg_holding_days_winners)}
                </span>
              </span>
              <span>
                Losers held{" "}
                <span className="font-mono tabular-nums">
                  {days(data.avg_holding_days_losers)}
                </span>
              </span>
            </div>
            <p className="mt-1.5 text-muted-foreground">
              {data.holds_losers_longer
                ? "You sell winners sooner than losers. Cutting a loss means admitting it; leaving it open keeps it a maybe."
                : "You sit with winners longer than losers — the harder discipline, and the less common one."}
            </p>
          </div>
        )}

      {/* THE HEADLINE, and the only number on this page that is not something
          that happened. It is a ceiling built from counterfactuals, and the
          bound is stated in the sentence itself — not a tooltip, not a
          footnote (§0.1). Rendered only when there is something to recover:
          "$0 recoverable" as a headline reads as a verdict on the user. */}
      {roll && roll.dollars > 0 && (
        <div
          data-testid="behavior-recoverable"
          className="rounded-lg border border-border bg-card px-4 py-3.5"
        >
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Worth changing
          </div>
          <div className="mt-1 font-mono text-2xl font-semibold tabular-nums text-foreground">
            up to {money(roll.dollars)}
          </div>
          <p className="mt-1.5 text-[13px] text-muted-foreground">
            over this window, across {roll.components.length}{" "}
            {roll.components.length === 1 ? "thing" : "things"}:{" "}
            {roll.components.map((c) => COMPONENT_LABEL[c] ?? c).join(", ")}.{" "}
            <strong className="font-medium text-foreground">
              That is a ceiling, not an expectation
            </strong>{" "}
            — each part assumes a different decision went perfectly, and you
            could not have taken all of them at once.
          </p>
        </div>
      )}

      {/* ZONE 3 — the lenses (§3.7.1).
          A section renders only once its lens has shipped; an empty section
          is noise. WHEN is the only one live, so the trichotomy is explained
          in one line rather than held open with placeholder slots. */}
      <div className="space-y-3" data-testid="mirror-lenses">
        <p className="text-[12px] text-muted-foreground">
          Three things decide how this goes: <strong className="font-medium text-foreground">what</strong>{" "}
          you buy, <strong className="font-medium text-foreground">when</strong> you buy and sell it, and{" "}
          <strong className="font-medium text-foreground">how much</strong> you put in each. Only the
          middle one is measured so far.
        </p>

        <div
          className="rounded-lg border border-border bg-card px-4 py-3.5"
          data-testid="lens-when"
        >
          <div className="text-[14px] font-semibold text-foreground">
            Did I buy and sell at the right time?
          </div>
          {/* THE FIGURE SLOT. Three states, and collapsing the third into the
              second is the failure mode: a dollar, a measured $0, or no figure
              WITH the reason there isn't one. Today every recoverable dollar
              in the product lives in this section, so its figure is the whole
              ceiling above — and saying that is the design, not a caveat. */}
          {roll && roll.dollars > 0 ? (
            <p className="mt-1 text-[13px] text-muted-foreground" data-testid="lens-when-figure">
              All <span className="font-mono tabular-nums text-foreground">{money(roll.dollars)}</span>{" "}
              of that ceiling sits here — the other two aren&rsquo;t measured yet, and neither is
              carrying a hidden number.
            </p>
          ) : (
            <p className="mt-1 text-[13px] text-muted-foreground" data-testid="lens-when-figure">
              Nothing recoverable turned up in your timing over this window.
            </p>
          )}

          <div className="mt-3 space-y-3">
            {/* M1 — reported in BOTH directions. An exit that saved money is the
                same finding with the sign flipped, and showing it only when it
                flatters the thesis would be measuring ourselves, not the user. */}
            {gap && gap.sells_measured > 0 && (
              <p
                data-testid="behavior-exit-gap"
                className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-[13px] text-foreground"
              >
                {gap.dollars > 0 ? (
                  <>
                    What you sold is worth{" "}
                    <strong className="font-medium">{money(gap.dollars)} more</strong>{" "}
                    today than what you sold it for
                    {gap.largest_symbol && <> — most of it {gap.largest_symbol}</>}.
                    This measures exits only, and assumes you would have held every
                    one of them to today.
                  </>
                ) : (
                  <>
                    Your exits{" "}
                    <strong className="font-medium">
                      saved you {money(-gap.dollars)}
                    </strong>{" "}
                    — what you sold is worth less now than what you got for it.
                  </>
                )}
                {gap.as_of && (
                  <span className="text-muted-foreground"> Priced at {gap.as_of}.</span>
                )}
              </p>
            )}

            {/* M4 */}
            {xq && xq.fills_measured > 0 && (
              <p
                data-testid="behavior-execution"
                className="rounded-lg border border-border bg-muted/30 px-4 py-3 text-[13px] text-foreground"
              >
                {xq.buy_percentile !== null && xq.buy_percentile !== undefined && (
                  <>
                    Your buys filled at the{" "}
                    <strong className="font-medium">
                      {(xq.buy_percentile * 100).toFixed(0)}th percentile
                    </strong>{" "}
                    of the day&rsquo;s range on average
                    {xq.sell_percentile !== null &&
                      xq.sell_percentile !== undefined && (
                        <>, your sells at the {(xq.sell_percentile * 100).toFixed(0)}th</>
                      )}
                    .{" "}
                  </>
                )}
                {xq.dollars > 0
                  ? `Filling at each day's midpoint instead would have been worth ${money(xq.dollars)}.`
                  : `You beat the day's midpoint by ${money(-xq.dollars)} overall.`}{" "}
                <span className="text-muted-foreground">
                  Measured on {xq.fills_measured} of {xq.fills_total} fills.
                </span>
              </p>
            )}

            {/* Every finding names what would answer it. A diagnosis with no
                remedy is a verdict, and we do not ship verdicts. No tier chip and
                no link: neither tool is built, and offering an upgrade for
                something that does not exist is worse than naming it plainly. */}
            {data.remedies.length > 0 && (
              <div
                data-testid="behavior-remedies"
                className="rounded-lg border border-dashed border-border px-4 py-3"
              >
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  What would answer this
                </div>
                <ul className="mt-1.5 space-y-1">
                  {data.remedies.map((r) => (
                    <li key={r} data-testid={`behavior-remedy-${r}`} className="text-[13px]">
                      {REMEDY_LABEL[r] ?? r}
                    </li>
                  ))}
                </ul>
                <p className="mt-1.5 text-[11px] text-muted-foreground">
                  Neither is built yet. They&rsquo;re named here because the number
                  above is only useful if something can be done about it.
                </p>
              </div>
            )}

            <MirrorWhenSection backendToken={backendToken} />
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <SymbolTable
          title="Traded most"
          rows={data.top_symbols_by_trades}
          testid="behavior-most-traded"
        />
        <SymbolTable
          title="Made and lost the most"
          rows={[...data.top_symbols_by_pnl, ...data.worst_symbols_by_pnl]
            .filter(
              (s, i, all) => all.findIndex((o) => o.symbol === s.symbol) === i,
            )
            .sort((a, b) => b.realised_pnl - a.realised_pnl)}
          testid="behavior-by-pnl"
        />
      </div>

      {/* Rule 3 — say what the numbers leave out. */}
      <div className="space-y-1 text-[11px] text-muted-foreground">
        {/* A dropped symbol is the most consequential omission on this panel
            and gets the strongest treatment: named, with the reason, above
            the ordinary footnotes rather than inside them. */}
        {excluded.length > 0 && (
          <p
            data-testid="behavior-excluded"
            className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900"
          >
            <strong className="font-medium">
              {excluded.join(", ")} {excluded.length === 1 ? "is" : "are"} left
              out of everything above.
            </strong>{" "}
            {excluded.length === 1 ? "It" : "They"} split during this window,
            and the buy and sell records don&rsquo;t line up either as your
            broker reported them or once adjusted for the split — so any
            profit or loss we showed you would be invented rather than
            measured.
          </p>
        )}
        <p>
          Matched oldest-lot-first within each account
          {data.symbols_total > 0 &&
            data.symbols_included < data.symbols_total && (
              <span data-testid="behavior-coverage">
                , across {data.symbols_included} of {data.symbols_total}{" "}
                symbols you traded
              </span>
            )}
          . Fees are deducted: {money(data.fees_paid)} paid over this window.
        </p>
        {data.splits_adjusted > 0 && (
          <p data-testid="behavior-splits">
            {data.splits_adjusted === 1
              ? "One stock split was"
              : `${data.splits_adjusted} stock splits were`}{" "}
            accounted for so the share counts line up. This changes no
            dollars — it only lets a position held through a split match to
            the buy that opened it.
          </p>
        )}
        {data.unmatched_sells > 0 && (
          <p data-testid="behavior-unmatched">
            {data.unmatched_sells === 1 ? "One sale" : `${data.unmatched_sells} sales`}{" "}
            ({data.unmatched_sell_symbols.join(", ")}) closed a position opened
            before this window. There&rsquo;s no cost basis for those here, so
            they&rsquo;re left out of the P/L rather than guessed at.
          </p>
        )}
        {data.open_lots > 0 && (
          <p>
            {data.open_lots === 1 ? "One lot is" : `${data.open_lots} lots are`}{" "}
            still open — unrealised gains and losses aren&rsquo;t counted above.
          </p>
        )}
      </div>
    </div>
  );
}
