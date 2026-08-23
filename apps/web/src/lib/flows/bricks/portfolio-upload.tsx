"use client";

/**
 * <PortfolioUpload> — PRD-13b brick.
 *
 * The entry step of `portfolio_mode`. The primary input is a ticker
 * search (type a symbol/company → click → it's added to the holdings
 * table). Bulk import (CSV drop / paste) is kept but demoted below the
 * search + the editable holdings table.
 *
 * Validates locally:
 *   - At least one ticker.
 *   - Weights either all present (sum-to-1 warned, not blocked) or
 *     uniformly absent (engine defaults to equal-weight downstream).
 *
 * No backend call here except the symbol-search typeahead — the next step
 * (<PortfolioDiagnosis>) is what hits POST /api/portfolio/diagnose.
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { ConnectBrokerage } from "@/components/execution/connect-brokerage";
import { useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { listBrokerPositions } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { searchSymbols } from "@/lib/api";
import type { Holding, SymbolSearchItem } from "@/lib/contracts";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

registerModeCopy("portfolio_mode", {
  upload_title: "Upload your portfolio",
  upload_subtitle: "Search a ticker to add it, or import your holdings in bulk.",
  upload_search_label: "Search & add a ticker",
  upload_search_placeholder: "Search by symbol or company — AAPL, Nvidia…",
  upload_bulk_label: "Or import in bulk",
  upload_paste_label: "Paste CSV",
  upload_manual_label: "Add ticker",
  upload_csv_help: "One row per holding. Columns: ticker, weight (optional)",
  upload_continue: "Continue → Diagnose",
});

interface ManualRow {
  ticker: string;
  weightText: string;
  /** Real share count from a connected broker. Absent for typed rows. */
  shares?: number;
  /** The broker's cost basis. THIS is what makes connecting worth doing:
   *  `declare_position` needs symbol + shares + entry price, and a typed
   *  cost basis is a guess. It does not affect the backtest — a backtest
   *  runs over history and has no business knowing what you paid. */
  costBasis?: number;
  /** Marks rows that came from a brokerage rather than the keyboard. */
  fromBroker?: boolean;
}

function parseCsv(text: string): ManualRow[] {
  // Lenient CSV: per-line "TICKER" or "TICKER,WEIGHT" (header row tolerated).
  const out: ManualRow[] = [];
  const lines = text.split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;
    const lower = line.toLowerCase();
    if (lower.startsWith("ticker") || lower.startsWith("symbol")) continue;
    const [tk, w] = line.split(/[,\t]/);
    const ticker = (tk || "").toUpperCase().trim();
    if (!ticker) continue;
    out.push({ ticker, weightText: (w || "").trim() });
  }
  return out;
}

function rowsToHoldings(rows: ManualRow[]): Holding[] {
  const out: Holding[] = [];
  for (const r of rows) {
    if (!r.ticker) continue;
    const w = r.weightText ? Number(r.weightText) : NaN;
    const basis =
      r.costBasis !== undefined ? { cost_basis_per_share: r.costBasis } : {};
    if (Number.isFinite(w) && w > 0 && w <= 1) {
      out.push({ ticker: r.ticker, weight: w, ...basis });
    } else if (r.shares !== undefined && r.shares > 0) {
      // A real share count from the broker. Carried through rather than
      // flattened to 1 — it is half of what `declare_position` needs, and
      // the other half is the cost basis beside it.
      out.push({ ticker: r.ticker, shares: r.shares, ...basis });
    } else {
      // Equal-weight downstream: store with no weight (engine fallback).
      out.push({ ticker: r.ticker, shares: 1, ...basis });
    }
  }
  return out;
}

export function PortfolioUpload({
  context,
  updateContext,
  advance,
}: FlowStepProps<PortfolioModeContext>) {
  const title = useFlowCopy("portfolio_mode", "upload_title");
  const subtitle = useFlowCopy("portfolio_mode", "upload_subtitle");
  const searchLabel = useFlowCopy("portfolio_mode", "upload_search_label");
  const searchPlaceholder = useFlowCopy("portfolio_mode", "upload_search_placeholder");
  const bulkLabel = useFlowCopy("portfolio_mode", "upload_bulk_label");
  const pasteLabel = useFlowCopy("portfolio_mode", "upload_paste_label");
  const manualLabel = useFlowCopy("portfolio_mode", "upload_manual_label");
  const csvHelp = useFlowCopy("portfolio_mode", "upload_csv_help");
  const continueLabel = useFlowCopy("portfolio_mode", "upload_continue");

  const [rows, setRows] = React.useState<ManualRow[]>(() => {
    if (context.holdings && context.holdings.length > 0) {
      return context.holdings.map((h) => ({
        ticker: h.ticker,
        weightText: h.weight !== undefined ? String(h.weight) : "",
        shares: h.shares,
        costBasis: h.cost_basis_per_share,
      }));
    }
    return [{ ticker: "", weightText: "" }];
  });
  const [pasteText, setPasteText] = React.useState("");
  const [brokerCount, setBrokerCount] = React.useState(0);
  const [brokerError, setBrokerError] = React.useState<string | null>(null);

  // ── returning from the brokerage portal ──────────────────────────────────
  //
  // `<ConnectBrokerage>` sends the user to SnapTrade with a return path of
  // `/flow/portfolio_mode?connected=1`. This is the other half: without it
  // the user authorises their broker, comes back, and finds the same empty
  // form they left — which reads as the connection having failed.
  //
  // MERGES, NEVER CLOBBERS. Someone may have typed three tickers before
  // deciding to connect, and losing them would punish the exact user who
  // engaged most. Where both sources have a ticker the BROKER wins, because
  // its share count and cost basis are real and the typed row was a guess.
  const searchParams = useSearchParams();
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;
  const justConnected = searchParams?.get("connected") === "1";

  React.useEffect(() => {
    if (!justConnected) return;
    if (sessionStatus === "loading" || !backendToken) return;
    let live = true;
    listBrokerPositions(backendToken)
      .then((positions) => {
        if (!live || positions.length === 0) return;
        setBrokerCount(positions.length);
        setRows((prev) => {
          const fromBroker: ManualRow[] = positions.map((p) => ({
            ticker: p.symbol.toUpperCase(),
            weightText: "",
            shares: p.units,
            costBasis: p.average_purchase_price ?? undefined,
            fromBroker: true,
          }));
          const brokerTickers = new Set(fromBroker.map((r) => r.ticker));
          const typed = prev.filter(
            (r) => r.ticker && !brokerTickers.has(r.ticker.toUpperCase()),
          );
          return [...fromBroker, ...typed];
        });
      })
      .catch(() => {
        if (live) {
          setBrokerError(
            "Connected, but we couldn't read your holdings just now. " +
              "You can still add them below.",
          );
        }
      });
    return () => {
      live = false;
    };
  }, [justConnected, sessionStatus, backendToken]);

  // ── Symbol-search typeahead (the primary add path) ──────────────────────
  const [query, setQuery] = React.useState("");
  const [suggestions, setSuggestions] = React.useState<SymbolSearchItem[]>([]);
  const [searching, setSearching] = React.useState(false);

  React.useEffect(() => {
    if (!query.trim()) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    setSearching(true);
    // Debounce 200ms so the paid-cached /api/symbols/search isn't pummelled
    // on every keystroke (mirrors the one-asset ticker typeahead).
    const t = window.setTimeout(() => {
      searchSymbols(query.trim())
        .then((results) => {
          if (!cancelled) setSuggestions(results.slice(0, 6));
        })
        .catch(() => {
          if (!cancelled) setSuggestions([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
      setSearching(false);
    };
  }, [query]);

  const addTicker = (symbol: string) => {
    const tk = symbol.trim().toUpperCase();
    if (!tk) return;
    setRows((prev) => {
      // Already in the list → no-op (no duplicate holdings).
      if (prev.some((r) => r.ticker.trim().toUpperCase() === tk)) return prev;
      // Fill the first empty row if there is one, else append.
      const firstEmpty = prev.findIndex((r) => !r.ticker.trim());
      if (firstEmpty >= 0) {
        return prev.map((r, i) => (i === firstEmpty ? { ...r, ticker: tk } : r));
      }
      return [...prev, { ticker: tk, weightText: "" }];
    });
    setQuery("");
    setSuggestions([]);
  };

  const setRow = (i: number, patch: Partial<ManualRow>) => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };

  const removeRow = (i: number) => {
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((_, idx) => idx !== i)));
  };

  const addRow = () => {
    setRows((prev) => [...prev, { ticker: "", weightText: "" }]);
  };

  const onPaste = () => {
    const parsed = parseCsv(pasteText);
    if (parsed.length > 0) {
      setRows(parsed);
      setPasteText("");
    }
  };

  const onCsvFile = (file: File) => {
    file.text().then((txt) => {
      const parsed = parseCsv(txt);
      if (parsed.length > 0) setRows(parsed);
    });
  };

  const validHoldings = rowsToHoldings(rows);
  const totalWeight = validHoldings.reduce((s, h) => s + (h.weight ?? 0), 0);
  const weightWarning =
    totalWeight > 0 && Math.abs(totalWeight - 1.0) > 0.02
      ? `Weights sum to ${(totalWeight * 100).toFixed(0)}% (not 100%) — we'll normalize.`
      : null;

  const onContinue = () => {
    if (validHoldings.length === 0) return;
    updateContext({ holdings: validHoldings });
    advance();
  };

  return (
    <section className="flex flex-col gap-6" data-testid="portfolio-upload">
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      {/* Connect a broker — a PEER to the manual paths, never a gate.
          A brokerage login is a high-trust action and a real share of users
          decline it on first contact, so it carries its own dismissal and
          the search + CSV paths below are untouched.

          It returns the user here, to this step, because losing your place
          immediately after the most trust-demanding thing we ask is how a
          connection flow gets abandoned. */}
      <ConnectBrokerage
        returnPath="/flow/portfolio_mode?connected=1"
        dismissible
      />

      {brokerCount > 0 && (
        <p
          data-testid="portfolio-upload-from-broker"
          className="text-[13px] text-muted-foreground"
        >
          {brokerCount === 1
            ? "1 holding loaded from your broker"
            : `${brokerCount} holdings loaded from your broker`}
          , with the shares and cost basis it reports. Edit anything that
          looks wrong.
        </p>
      )}
      {brokerError && (
        <p
          data-testid="portfolio-upload-broker-error"
          className="text-[13px] text-muted-foreground"
        >
          {brokerError}
        </p>
      )}

      {/* Primary: search → add */}
      <div className="grid gap-2">
        <label className="text-xs font-medium text-muted-foreground">{searchLabel}</label>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value.toUpperCase())}
          placeholder={searchPlaceholder}
          autoComplete="off"
          spellCheck={false}
          className="font-mono"
          data-testid="portfolio-upload-search"
        />
        {searching && suggestions.length === 0 ? (
          <p className="text-xs text-muted-foreground">Searching…</p>
        ) : null}
        {suggestions.length > 0 ? (
          <ul
            className="rounded-xl border border-border bg-card"
            data-testid="portfolio-upload-suggestions"
          >
            {suggestions.map((s) => (
              <li key={s.symbol} className="border-b border-border last:border-b-0">
                <button
                  type="button"
                  onClick={() => addTicker(s.symbol)}
                  className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-muted/30"
                  data-testid={`portfolio-upload-suggestion-${s.symbol}`}
                >
                  <span className="font-mono text-sm font-semibold">{s.symbol}</span>
                  <span className="truncate text-xs text-muted-foreground">{s.name}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {/* The holdings being built (editable). */}
      <div className="grid gap-2">
        <div className="grid grid-cols-[1fr_140px_40px] gap-2 text-xs font-medium text-muted-foreground">
          <span>Ticker</span>
          <span>Weight (0–1, optional)</span>
          <span></span>
        </div>
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-[1fr_140px_40px] gap-2">
            <Input
              value={r.ticker}
              onChange={(e) =>
                setRow(i, { ticker: e.target.value.toUpperCase() })
              }
              placeholder="AAPL"
              className="font-mono"
              data-testid={`portfolio-upload-ticker-${i}`}
            />
            <Input
              value={r.weightText}
              onChange={(e) => setRow(i, { weightText: e.target.value })}
              placeholder="0.4"
              className="font-mono"
              data-testid={`portfolio-upload-weight-${i}`}
            />
            <button
              type="button"
              onClick={() => removeRow(i)}
              aria-label={`Remove row ${i + 1}`}
              className="text-muted-foreground hover:text-foreground"
              data-testid={`portfolio-upload-remove-${i}`}
            >
              ×
            </button>
          </div>
        ))}
        <div>
          <Button variant="outline" size="sm" onClick={addRow} data-testid="portfolio-upload-add">
            + {manualLabel}
          </Button>
        </div>
      </div>

      {weightWarning ? (
        <p className="text-xs text-amber-700">{weightWarning}</p>
      ) : null}

      {/* Demoted: bulk import (CSV drop + paste). */}
      <details className="rounded-xl border border-border/60 bg-muted/10">
        <summary className="cursor-pointer px-4 py-2.5 text-xs font-medium text-muted-foreground">
          {bulkLabel}
        </summary>
        <div className="flex flex-col gap-4 px-4 pb-4 pt-1">
          <div
            className="rounded-xl border border-dashed border-border bg-muted/30 p-4 text-sm"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files?.[0];
              if (f) onCsvFile(f);
            }}
          >
            <div className="flex items-center gap-2">
              <label className="cursor-pointer text-primary underline underline-offset-2">
                Drop a CSV here or click to pick
                <input
                  type="file"
                  accept=".csv,text/csv,text/plain"
                  className="hidden"
                  data-testid="portfolio-upload-file"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) onCsvFile(f);
                  }}
                />
              </label>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{csvHelp}</p>
          </div>

          <div className="grid gap-2">
            <label className="text-xs font-medium text-muted-foreground">{pasteLabel}</label>
            <textarea
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              placeholder={"AAPL,0.4\nMSFT,0.3\nNVDA,0.3"}
              rows={3}
              className="w-full rounded-xl border border-border bg-background px-3 py-2 font-mono text-xs leading-relaxed placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              data-testid="portfolio-upload-paste"
            />
            <div>
              <Button
                variant="outline"
                size="sm"
                onClick={onPaste}
                disabled={!pasteText.trim()}
                data-testid="portfolio-upload-paste-apply"
              >
                Apply paste
              </Button>
            </div>
          </div>
        </div>
      </details>

      <div>
        <Button
          onClick={onContinue}
          disabled={validHoldings.length === 0}
          data-testid="portfolio-upload-continue"
        >
          {continueLabel}
        </Button>
      </div>
    </section>
  );
}
