"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

// ── Data ─────────────────────────────────────────────────────────────────────

const SUPPORTED_STRATEGIES = [
  {
    name: "Moving Average Filter",
    desc: "Hold when price is above its N-day moving average; exit when it falls below.",
    params: "Lookback: 5 – 250 days",
    examples: ["Buy SPY when above 200-day MA", "Hold GLD above its 50-day MA"],
  },
  {
    name: "MA Crossover",
    desc: "Buy when a fast MA crosses above a slow MA (golden cross); sell on death cross.",
    params: "Fast: 5 – 50d · Slow: 50 – 200d",
    examples: ["50/200-day golden cross on SPY", "20/50-day MACD-style crossover"],
  },
  {
    name: "Momentum Rotation",
    desc: "Rank assets by N-month return and hold the top N — rebalance monthly.",
    params: "Top N: 1 – 5 · Lookback: 21 – 252 days",
    examples: ["Top 2 ETFs by 3-month return", "Commodity momentum rotation"],
  },
  {
    name: "RSI Mean Reversion",
    desc: "Buy oversold conditions (low RSI); sell into overbought strength (high RSI).",
    params: "Period: 7 – 21 · Entry: 20 – 40 · Exit: 60 – 80",
    examples: ["Buy AAPL when RSI < 30, sell when RSI > 60"],
  },
  {
    name: "Breakout",
    desc: "Enter on an N-day high breakout; exit on N-day low or stop loss.",
    params: "Entry window: 10 – 60d · Stop: 5 – 15%",
    examples: ["20-day high breakout on GLD", "Donchian channel entry"],
  },
  {
    name: "Static Allocation",
    desc: "Hold a fixed-weight portfolio, rebalanced on a schedule.",
    params: "Rebalance: daily / weekly / monthly / quarterly",
    examples: ["60% SPY / 40% TLT rebalanced monthly", "Equal-weight commodity basket"],
  },
];

const AVAILABLE_ASSETS = [
  {
    category: "US Equities & ETFs",
    items: ["Any NYSE / NASDAQ ticker (e.g. AAPL, MSFT, NVDA)", "Sector ETFs: XLK, XLE, XLF, XLV, …", "Index ETFs: SPY (S&P 500), QQQ (Nasdaq 100), IWM (Russell 2000), DIA (Dow Jones)"],
  },
  {
    category: "Commodity ETFs",
    items: ["GLD (Gold)", "SLV (Silver)", "USO (Crude Oil)", "UNG (Natural Gas)", "DBA (Agriculture)", "DBC (Broad Commodities)", "CPER (Copper)"],
  },
  {
    category: "Bond ETFs",
    items: ["TLT (20Y Treasury)", "IEF (7-10Y Treasury)", "SHY (1-3Y Treasury)"],
  },
  {
    category: "A-Shares (China)",
    items: ["Shanghai stocks: use .SHH suffix (e.g. 600519.SHH)", "Shenzhen stocks: use .SHZ suffix", "CSI 300 ETF: 510300.SHH (default benchmark)"],
  },
];

const NOT_SUPPORTED = [
  "Cross-asset signals — using asset A's price to trade asset B (e.g. buy gold when oil rises)",
  "Fundamental data — P/E ratio, earnings, revenue, book value",
  "Macro & sentiment — VIX, CPI, Fed rate, news sentiment, economic indicators",
  "Short selling, leverage, or options",
  "Intraday data — signals defined in minutes or hours",
  "Real-time streaming prices",
];

// ── Sub-components ────────────────────────────────────────────────────────────

function StrategyCard({ name, desc, params, examples }: typeof SUPPORTED_STRATEGIES[0]) {
  return (
    <div className="rounded-xl border border-border bg-white p-4 shadow-sm">
      <div className="flex items-start gap-2">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--profit)]" aria-hidden="true" />
        <div>
          <div className="font-heading text-sm font-semibold">{name}</div>
          <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{desc}</p>
          <div className="mt-2 rounded-md bg-muted/40 px-2 py-1 font-mono text-[10px] text-foreground/70">{params}</div>
          <div className="mt-2 space-y-0.5">
            {examples.map((ex) => (
              <div key={ex} className="flex items-start gap-1 text-[11px] text-muted-foreground">
                <span className="mt-1 text-primary">·</span>
                <span>{ex}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface CapabilityGlossaryProps {
  /** When true, renders as a compact collapsible sidebar panel */
  compact?: boolean;
}

export function CapabilityGlossary({ compact = false }: CapabilityGlossaryProps) {
  const [notSupportedOpen, setNotSupportedOpen] = useState(false);
  const [open, setOpen] = useState(!compact);

  if (compact) {
    return (
      <div className="overflow-hidden rounded-xl border border-border bg-white shadow-sm">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left transition-colors hover:bg-muted/30"
        >
          <span className="font-heading text-sm font-semibold">Strategy Building Blocks</span>
          {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
        </button>

        {open && (
          <div className="border-t border-border px-4 py-3 space-y-4">
            {/* Supported strategies — compact list */}
            <div>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Supported Strategies</div>
              <div className="space-y-1">
                {SUPPORTED_STRATEGIES.map((s) => (
                  <div key={s.name} className="flex items-start gap-1.5 text-xs text-foreground/80">
                    <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-[var(--profit)]" />
                    <div>
                      <span className="font-medium">{s.name}</span>
                      <span className="text-muted-foreground"> · {s.params}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Available assets — compact */}
            <div>
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Available Assets</div>
              <div className="space-y-2">
                {AVAILABLE_ASSETS.map((group) => (
                  <div key={group.category}>
                    <div className="text-[10px] font-semibold text-foreground/60">{group.category}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground leading-relaxed">{group.items.slice(0, 2).join(" · ")}{group.items.length > 2 ? ` +${group.items.length - 2} more` : ""}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Not supported — compact toggle */}
            <button
              type="button"
              onClick={() => setNotSupportedOpen((v) => !v)}
              className="flex w-full cursor-pointer items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground hover:text-foreground"
            >
              {notSupportedOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              Not yet supported
            </button>
            {notSupportedOpen && (
              <div className="space-y-1 rounded-lg border border-border bg-muted/20 p-3">
                {NOT_SUPPORTED.map((item) => (
                  <div key={item} className="flex items-start gap-1.5 text-xs text-muted-foreground">
                    <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-[var(--loss)]/60" />
                    {item}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── Full homepage version ──────────────────────────────────────────────────
  return (
    <section className="space-y-8">
      <div className="text-center">
        <h2 className="font-heading text-2xl font-bold">What You Can Build</h2>
        <p className="mt-2 text-muted-foreground">
          Livermore supports price-based strategies. Here's exactly what's available — so you know before you type.
        </p>
      </div>

      {/* Supported strategies grid */}
      <div>
        <div className="mb-4 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-[var(--profit)]" />
          <h3 className="font-heading text-base font-semibold">Supported Strategy Types</h3>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SUPPORTED_STRATEGIES.map((s) => <StrategyCard key={s.name} {...s} />)}
        </div>
      </div>

      {/* Available assets + Not supported row */}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">

        {/* Available assets */}
        <div className="rounded-xl border border-border bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-[var(--profit)]" />
            <h3 className="font-heading text-base font-semibold">Available Asset Universe</h3>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {AVAILABLE_ASSETS.map((group) => (
              <div key={group.category}>
                <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.category}</div>
                <ul className="space-y-1">
                  {group.items.map((item) => (
                    <li key={item} className="flex items-start gap-1.5 text-sm text-foreground/80">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary" aria-hidden="true" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        {/* Not yet supported */}
        <div className="rounded-xl border border-border bg-muted/30 p-5">
          <div className="mb-4 flex items-center gap-2">
            <XCircle className="h-4 w-4 text-[var(--loss)]/70" />
            <h3 className="font-heading text-base font-semibold text-muted-foreground">Not Yet Supported</h3>
          </div>
          <ul className="space-y-2">
            {NOT_SUPPORTED.map((item) => (
              <li key={item} className={cn("flex items-start gap-2 text-sm text-muted-foreground")}>
                <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--loss)]/50" aria-hidden="true" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
