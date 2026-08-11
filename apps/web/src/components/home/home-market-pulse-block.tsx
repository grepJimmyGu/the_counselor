"use client";

/**
 * Home block 1 — "Moving today", the market snapshot.
 *
 * Reads `/api/market/daily-brief`, which assembles the tape, the macro trend,
 * the day's biggest movers, sector leadership and money flow. Every number
 * here is deterministic and checkable against the market.
 *
 * THE TWO SOURCE SWAPS THAT MATTER. This block used to read SPY/QQQ/DIA and
 * VXX off `/api/market/pulse`. SPY is ~$650; the S&P 500 is ~7,750 — an ETF
 * share price shown as an index level is wrong, not merely different, and
 * this block is built to be shared. Same for VXX, which is a VIX-*futures*
 * ETF, not the volatility level. The brief endpoint reads `^GSPC`/`^IXIC`/
 * `^DJI`/`^VIX` instead.
 *
 * FITTED TO A HALF-WIDTH SLOT. The block lives in the home page's 2-up grid
 * (`max-w-[1200px]`, `lg:grid-cols-2`), so its real width is ~568px — not the
 * full row. Type is on the same scale as its sibling blocks (`text-base`
 * heading, `text-xs` labels); anything larger makes this card shout next to
 * the three it sits with.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { getDailyBrief } from "@/lib/api";
import { ShareCardButton } from "@/components/home/share-card-button";
import type { BriefMover, BriefQuote, BriefSector, DailyBrief } from "@/lib/contracts";

/** Percent, signed. Values arrive already scaled. */
function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function level(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function tone(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "text-muted-foreground";
  return v >= 0 ? "text-emerald-600" : "text-red-600";
}

/** VIX is a LEVEL, not a return — "VIX down 1.65%" is not good news the way
 *  "S&P up 0.62%" is. Left in neutral ink with a plain-English gloss so the
 *  green/red coding keeps meaning exactly one thing. */
function vixMood(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "";
  if (v < 15) return "calm";
  if (v < 20) return "steady";
  if (v < 30) return "jumpy";
  return "fearful";
}

function IndexTile({ q }: { q: BriefQuote }) {
  return (
    <div className="flex flex-col gap-0.5 px-3 py-2" data-testid="brief-index">
      <span className="truncate text-[11px] text-muted-foreground">{q.name}</span>
      <span className="font-mono text-[15px] font-semibold tabular-nums">{level(q.price)}</span>
      <span className={`font-mono text-xs font-semibold tabular-nums ${tone(q.change_percent)}`}>
        {pct(q.change_percent)}
      </span>
    </div>
  );
}

function MoverRow({ m }: { m: BriefMover }) {
  return (
    <Link
      href={`/stocks/${m.symbol}` as Route}
      data-testid="brief-mover"
      className="flex items-baseline gap-2 border-b border-border/60 py-1.5 text-xs last:border-b-0 hover:bg-muted/40"
    >
      <span className="w-12 shrink-0 font-mono font-semibold">{m.symbol}</span>
      <span className="truncate text-muted-foreground">{m.name ?? ""}</span>
      <span className={`ml-auto shrink-0 font-mono font-semibold tabular-nums ${tone(m.change_percent)}`}>
        {pct(m.change_percent)}
      </span>
    </Link>
  );
}

/** Sector names stay clickable — the old block linked each one to the
 *  screener filtered by that sector, and dropping a working affordance in a
 *  redesign is a regression even when the new layout is better. */
function SectorName({ s }: { s: BriefSector | null }) {
  if (!s) return <span className="text-muted-foreground">—</span>;
  return (
    <Link
      href={`/stocks?sector=${encodeURIComponent(s.name)}` as Route}
      data-testid="brief-sector"
      className="font-semibold hover:underline"
    >
      {s.name}
    </Link>
  );
}

export function HomeMarketPulseBlock() {
  const [brief, setBrief] = useState<DailyBrief | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    getDailyBrief("US")
      .then((b) => live && setBrief(b))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  if (failed) {
    return (
      <section className="rounded-lg border border-border bg-card p-4" data-testid="home-market-pulse">
        <h2 className="font-heading text-base font-semibold">Moving today</h2>
        <p className="mt-2 text-xs text-muted-foreground">
          Couldn&apos;t load today&apos;s snapshot. It&apos;ll be back on the next refresh.
        </p>
      </section>
    );
  }

  if (!brief) {
    return (
      <section className="rounded-lg border border-border bg-card p-4" data-testid="home-market-pulse">
        <div className="h-4 w-28 animate-pulse rounded bg-muted" />
        <div className="mt-3 h-16 animate-pulse rounded bg-muted/60" />
        <div className="mt-3 h-24 animate-pulse rounded bg-muted/60" />
      </section>
    );
  }

  const asOfDate = brief.as_of ? brief.as_of.slice(0, 10) : null;

  return (
    <section
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
      data-testid="home-market-pulse"
    >
      {/* Date ABOVE the headline, 11px semibold uppercase — the repo's
          newspaper-byline pattern. A calendar anchor has to be readable at a
          glance, not buried in footer text (product invariant). */}
      <div>
        {asOfDate && (
          <div
            className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
            data-testid="brief-as-of"
          >
            Close · {asOfDate}
          </div>
        )}
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-heading text-base font-semibold">Moving today</h2>
          <ShareCardButton />
        </div>
      </div>

      {/* The tape. 2×2 at this width rather than a 4-wide row that would
          squeeze every index level to four characters. */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border">
        {brief.indices.map((q) => (
          <div key={q.symbol} className="bg-card">
            <IndexTile q={q} />
          </div>
        ))}
        {brief.vix && (
          <div className="bg-card">
            <div className="flex flex-col gap-0.5 px-3 py-2" data-testid="brief-vix">
              <span className="truncate text-[11px] text-muted-foreground">{brief.vix.name}</span>
              <span className="font-mono text-[15px] font-semibold tabular-nums">
                {level(brief.vix.price)}
              </span>
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {pct(brief.vix.change_percent)} · {vixMood(brief.vix.price)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Macro. Direction is the point — the level alone doesn't say whether
          the backdrop is tightening or easing. */}
      {brief.macro.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid="brief-macro">
          {brief.macro.map((m) => (
            <span
              key={m.category}
              title={m.takeaway}
              className="inline-flex items-baseline gap-1.5 rounded-full border border-border bg-muted px-2 py-0.5 text-[11px]"
            >
              <span className="text-muted-foreground">{m.label}</span>
              {m.trend && (
                <span className={m.direction === "up" ? "font-semibold text-amber-600" : "font-semibold text-muted-foreground"}>
                  {m.direction === "up" ? "↑" : m.direction === "down" ? "↓" : "→"} {m.trend.toLowerCase()}
                </span>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Gainers | losers, side by side even at this width — the comparison is
          the point, and stacking them doubles the block's height. */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Biggest gainers
          </h3>
          <div className="flex flex-col">
            {brief.gainers.map((m) => (
              <MoverRow key={m.symbol} m={m} />
            ))}
          </div>
        </div>
        <div>
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Biggest losers
          </h3>
          <div className="flex flex-col">
            {brief.losers.map((m) => (
              <MoverRow key={m.symbol} m={m} />
            ))}
          </div>
        </div>
      </div>

      {/* Sector leadership and where money actually went — two different
          rankings, deliberately. A sector can lead on price while money
          leaves it, and that gap is the most useful thing on the block. */}
      <div className="flex flex-col gap-1.5 rounded-md border border-border px-3 py-2 text-xs">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Sector leading</span>
          <span className="truncate">
            <SectorName s={brief.sector_leading} />{" "}
            <span className={`font-mono tabular-nums ${tone(brief.sector_leading?.change_percent)}`}>
              {pct(brief.sector_leading?.change_percent)}
            </span>
          </span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-muted-foreground">Sector lagging</span>
          <span className="truncate">
            <SectorName s={brief.sector_lagging} />{" "}
            <span className={`font-mono tabular-nums ${tone(brief.sector_lagging?.change_percent)}`}>
              {pct(brief.sector_lagging?.change_percent)}
            </span>
          </span>
        </div>
        {brief.flow_into && brief.flow_out_of && (
          <div
            className="flex flex-col gap-0.5 border-t border-border/60 pt-1.5"
            data-testid="brief-flow"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-muted-foreground">Money flowing</span>
              <span className="truncate">
                <SectorName s={brief.flow_out_of} />{" "}
                <span className="font-mono text-muted-foreground">→</span>{" "}
                <SectorName s={brief.flow_into} />
              </span>
            </div>
            {/* The numbers behind the arrow. Without them "money flowing" is
                an assertion the reader has to take on faith; Chaikin Money
                Flow is a bounded −1..+1 score, so both ends are readable. */}
            <div className="flex items-baseline justify-between gap-2 text-[11px] text-muted-foreground">
              <span>Chaikin flow, 20d</span>
              <span className="font-mono tabular-nums">
                {brief.flow_out_of.money_flow?.toFixed(2)} → {brief.flow_into.money_flow?.toFixed(2)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Only on a day that earned it. Below the threshold the "biggest move"
          is just the top of a quiet leaderboard, and flagging it every
          session cries wolf. */}
      {brief.unusual && (
        <Link
          href={`/stocks/${brief.unusual.symbol}` as Route}
          data-testid="brief-unusual"
          className="flex items-baseline gap-2 rounded-md border border-amber-300/60 bg-amber-50 px-3 py-2 text-xs transition-colors hover:bg-amber-100/70"
        >
          <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700">
            Unusual
          </span>
          <span className="font-mono font-bold">{brief.unusual.symbol}</span>
          <span className={`font-mono font-semibold tabular-nums ${tone(brief.unusual.change_percent)}`}>
            {pct(brief.unusual.change_percent)}
          </span>
          <span className="ml-auto truncate text-muted-foreground">
            biggest move in the index
          </span>
        </Link>
      )}
    </section>
  );
}
