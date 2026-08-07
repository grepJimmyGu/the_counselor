"use client";

/**
 * Home block 1 — today's movers + where money is flowing.
 *
 * Replaces `<MarketSnapshot>`, which showed a hardcoded four-ticker watchlist
 * (SPY/QQQ/GLD/NVDA). That answered "how are these four doing?" — a question
 * nobody asked. This answers "what moved today, and which industries are money
 * going into?", which is a read worth acting on.
 *
 * Both halves come from `/api/market/pulse`, already computed and cached:
 * `top_assets` is ranked by CMF over the full universe, and every sector card
 * carries `cmf_20` (Chaikin Money Flow, -1..+1) — the closest thing we have to
 * 資金面. No new backend.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { getMarketPulse } from "@/lib/api";
import type { AssetCard, SectorCard } from "@/lib/contracts";

/** Movers shown. Three, per the spec — enough to scan, not a leaderboard. */
const MOVER_COUNT = 3;
/** Sectors shown. The pulse response is already sorted by CMF descending, so
 *  this is "strongest inflow" — we append the single weakest so the block
 *  shows money leaving as well as arriving. */
const SECTOR_COUNT = 4;

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`;
}

function toneFor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-muted-foreground";
  return v >= 0 ? "text-emerald-600" : "text-red-600";
}

function MoverTile({ a }: { a: AssetCard }) {
  return (
    <Link
      href={`/stocks/${a.symbol}` as Route}
      className="flex-1 rounded-lg bg-muted/40 px-3 py-2 transition-colors hover:bg-muted"
      data-testid="pulse-mover"
    >
      <div className="text-sm font-semibold">{a.symbol}</div>
      <div className="text-xs text-muted-foreground">
        {a.price !== null ? a.price.toFixed(2) : "—"}{" "}
        <span className={toneFor(a.perf_1d)}>{pct(a.perf_1d)}</span>
      </div>
    </Link>
  );
}

function SectorRow({ s, max }: { s: SectorCard; max: number }) {
  const cmf = s.cmf_20 ?? 0;
  // Bar width is relative to the strongest absolute flow on screen, so the
  // comparison stays readable on a quiet day when every value is near zero.
  const width = max > 0 ? Math.max(4, (Math.abs(cmf) / max) * 100) : 4;
  return (
    <Link
      href={`/stocks?sector=${encodeURIComponent(s.name)}` as Route}
      className="flex items-center gap-3 rounded px-1 py-1 text-sm transition-colors hover:bg-muted/60"
      data-testid="pulse-sector"
    >
      <span className="flex-1 truncate">{s.name}</span>
      <span className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-muted">
        <span
          className={`block h-full rounded-full ${cmf >= 0 ? "bg-emerald-500" : "bg-red-500"}`}
          style={{ width: `${width}%` }}
        />
      </span>
      <span className={`w-12 shrink-0 text-right text-xs tabular-nums ${toneFor(cmf)}`}>
        {cmf >= 0 ? "+" : ""}
        {cmf.toFixed(2)}
      </span>
    </Link>
  );
}

export function HomeMarketPulseBlock() {
  const [movers, setMovers] = useState<AssetCard[]>([]);
  const [sectors, setSectors] = useState<SectorCard[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    getMarketPulse("US")
      .then((d) => {
        if (!live) return;
        setMovers((d.top_assets ?? []).slice(0, MOVER_COUNT));
        const all = d.sectors ?? [];
        // Already CMF-descending. Take the top few, then the weakest — a block
        // that only ever shows inflow can't answer "what's being sold?".
        const lead = all.slice(0, SECTOR_COUNT - 1);
        const laggard = all.length > SECTOR_COUNT ? [all[all.length - 1]] : [];
        setSectors([...lead, ...laggard]);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, []);

  if (failed) return null;

  const maxFlow = Math.max(...sectors.map((s) => Math.abs(s.cmf_20 ?? 0)), 0.01);

  return (
    <section
      className="rounded-xl border border-border bg-white p-5"
      data-testid="home-market-pulse"
    >
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-heading text-base font-semibold">Moving today</h2>
        <Link href={"/stocks" as Route} className="text-xs text-primary hover:underline">
          Market Pulse →
        </Link>
      </div>

      <div className="flex gap-2">
        {movers.length > 0
          ? movers.map((a) => <MoverTile key={a.symbol} a={a} />)
          : Array.from({ length: MOVER_COUNT }).map((_, i) => (
              <div key={i} className="h-12 flex-1 animate-pulse rounded-lg bg-muted/50" />
            ))}
      </div>

      <div className="mt-4">
        <div className="mb-1.5 text-xs text-muted-foreground">
          Money flow by industry
        </div>
        {sectors.length > 0 ? (
          <div className="flex flex-col gap-0.5">
            {sectors.map((s) => (
              <SectorRow key={s.symbol} s={s} max={maxFlow} />
            ))}
          </div>
        ) : (
          <div className="h-24 animate-pulse rounded bg-muted/50" />
        )}
      </div>
    </section>
  );
}
