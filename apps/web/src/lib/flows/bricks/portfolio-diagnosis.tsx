"use client";

/**
 * <PortfolioDiagnosis> — PRD-13b brick.
 *
 * Step 2 of portfolio_mode. Calls POST /api/portfolio/diagnose for the
 * holdings the user uploaded, then renders:
 *   - style mix bars (growth / value / defensive / commodity / macro)
 *   - top factor exposures
 *   - sector breakdown
 *   - behavior aggregate (% trending / mean-reverting / mixed)
 *   - realized vol + 5y drawdown summary line
 *
 * Skeleton during load. Idle-prefetch the next step's static lib chunk
 * via dynamic import once the diagnosis lands. <300ms perceived load:
 * skeleton appears immediately (<50ms) and we hold for the API call.
 */

import * as React from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";
import { ChevronDown, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { diagnosePortfolio, getCompanyOverview, UpgradeRequiredError } from "@/lib/api";
import type {
  CompanyOverviewResponse,
  Holding,
  PortfolioDiagnosis as PortfolioDiagnosisPayload,
} from "@/lib/contracts";
// Reuse the stock-profile sections verbatim so the in-place preview matches
// /stocks/<ticker>. (Editorial follow-up: these are route-private `_`
// components; relocating them to @/components/stocks is a clean-up for later.)
import { EvaluationDashboard } from "@/app/stocks/[ticker]/_evaluation-dashboard";
import { BusinessModelSection } from "@/app/stocks/[ticker]/_business-model-section";
import type { FlowStepProps } from "../types";
import { registerModeCopy, useFlowCopy } from "../copy";
import type { PortfolioModeContext } from "../portfolio-mode-context";

registerModeCopy("portfolio_mode", {
  diagnose_title: "Your portfolio at a glance",
  diagnose_subtitle: "Read this before you pick an overlay.",
  diagnose_style_label: "Style mix",
  diagnose_factor_label: "Factor exposure",
  diagnose_sector_label: "Sector concentration",
  diagnose_behavior_label: "Behavior",
  diagnose_risk_label: "Realized risk (trailing 5y)",
  diagnose_holdings_label: "Your holdings",
  diagnose_continue: "Continue → Pick overlay",
  diagnose_error: "We couldn't diagnose your portfolio. Try again.",
  diagnose_rate_limited: "You've hit your hourly diagnose limit. Upgrade for more.",
});

function pct(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(0)}%`;
}

function fmtSigned(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const sign = x > 0 ? "+" : "";
  return `${sign}${x.toFixed(digits)}`;
}

function DiagSkeleton() {
  return (
    <section data-testid="portfolio-diagnosis-skeleton" className="space-y-4">
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    </section>
  );
}

function StyleMixView({ diag }: { diag: PortfolioDiagnosisPayload }) {
  const buckets: Array<[string, number]> = [
    ["Growth", diag.style_mix.growth],
    ["Value", diag.style_mix.value],
    ["Defensive", diag.style_mix.defensive],
    ["Commodity", diag.style_mix.commodity],
    ["Macro-sensitive", diag.style_mix.macro_sensitive],
  ];
  if (diag.style_mix.unclassified_weight > 0) {
    buckets.push(["Unclassified", diag.style_mix.unclassified_weight]);
  }
  return (
    <ul className="space-y-1.5">
      {buckets
        .filter(([, w]) => w > 0)
        .map(([label, w]) => (
          <li key={label} className="text-sm">
            <div className="flex justify-between">
              <span>{label}</span>
              <span className="font-mono text-muted-foreground">{pct(w)}</span>
            </div>
            <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary"
                style={{ width: `${Math.max(0, Math.min(1, w)) * 100}%` }}
              />
            </div>
          </li>
        ))}
    </ul>
  );
}

function FactorView({ diag }: { diag: PortfolioDiagnosisPayload }) {
  const fe = diag.factor_exposure;
  const rows: Array<[string, number | null | undefined]> = [
    ["Size", fe.size],
    ["Value", fe.value],
    ["Momentum", fe.momentum],
    ["Quality", fe.quality],
    ["Low vol", fe.low_vol],
    ["Beta vs SPY", fe.beta_to_spy],
  ];
  return (
    <ul className="space-y-1 text-sm">
      {rows.map(([label, val]) => (
        <li key={label} className="flex justify-between">
          <span>{label}</span>
          <span className="font-mono text-muted-foreground">{fmtSigned(val ?? null)}</span>
        </li>
      ))}
    </ul>
  );
}

function SectorView({ diag }: { diag: PortfolioDiagnosisPayload }) {
  const items = Object.entries(diag.sectors.sectors)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  if (diag.sectors.unknown_sector_weight > 0) {
    items.push(["Unknown", diag.sectors.unknown_sector_weight]);
  }
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground">No sector data available.</p>;
  }
  return (
    <ul className="space-y-1 text-sm">
      {items.map(([sec, w]) => (
        <li key={sec} className="flex justify-between">
          <span className="truncate" title={sec}>{sec || "—"}</span>
          <span className="font-mono text-muted-foreground">{pct(w)}</span>
        </li>
      ))}
    </ul>
  );
}

function BehaviorView({ diag }: { diag: PortfolioDiagnosisPayload }) {
  return (
    <ul className="space-y-1 text-sm">
      <li className="flex justify-between">
        <span>Trending</span>
        <span className="font-mono text-muted-foreground">{pct(diag.behavior.trending_pct)}</span>
      </li>
      <li className="flex justify-between">
        <span>Mean-reverting</span>
        <span className="font-mono text-muted-foreground">{pct(diag.behavior.mean_reverting_pct)}</span>
      </li>
      <li className="flex justify-between">
        <span>Mixed / volatile</span>
        <span className="font-mono text-muted-foreground">{pct(diag.behavior.mixed_pct)}</span>
      </li>
    </ul>
  );
}

// ── Per-holding explorer (in-place preview + link to the full profile) ───────

function HoldingPreview({
  ticker,
  data,
}: {
  ticker: string;
  data: CompanyOverviewResponse;
}) {
  return (
    <div className="space-y-5">
      {/* Fundamental Analysis — the scored Health / Valuation / Trend cards
          from the stock profile, reused verbatim. */}
      <section>
        <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Fundamental analysis
        </h4>
        <EvaluationDashboard data={data} />
      </section>

      {/* Business Model — revenue-by-segment + geographic mix + the
          model / customers / pricing rows, reused from the stock profile. */}
      <section>
        <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Business model
        </h4>
        <BusinessModelSection seg={data.revenue_segments} bm={data.business_map} />
      </section>

      <Link
        href={`/stocks/${ticker}` as Route}
        target="_blank"
        rel="noopener noreferrer"
        data-testid={`holding-profile-link-${ticker}`}
        className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
      >
        Full details <ExternalLink className="h-3 w-3" />
      </Link>
    </div>
  );
}

function HoldingsExplorer({ holdings, label }: { holdings: Holding[]; label: string }) {
  const [open, setOpen] = React.useState<string | null>(null);
  const [cache, setCache] = React.useState<
    Record<string, CompanyOverviewResponse | "loading" | "error">
  >({});

  if (holdings.length === 0) return null;

  const toggle = (ticker: string) => {
    const next = open === ticker ? null : ticker;
    setOpen(next);
    // Lazy fetch on first expand only — one ticker at a time keeps it cheap.
    if (next && cache[next] === undefined) {
      setCache((c) => ({ ...c, [next]: "loading" }));
      getCompanyOverview(next)
        .then((d) => setCache((c) => ({ ...c, [next]: d })))
        .catch(() => setCache((c) => ({ ...c, [next]: "error" })));
    }
  };

  return (
    <div data-testid="portfolio-diagnosis-holdings">
      <h2 className="mb-2 text-sm font-semibold">{label}</h2>
      <ul className="overflow-hidden rounded-xl border border-border">
        {holdings.map((h, i) => {
          const isOpen = open === h.ticker;
          const entry = cache[h.ticker];
          return (
            <li key={h.ticker} className={i > 0 ? "border-t border-border" : ""}>
              <button
                type="button"
                onClick={() => toggle(h.ticker)}
                aria-expanded={isOpen}
                data-testid={`holding-row-${h.ticker}`}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/30"
              >
                <span className="flex-1 font-mono text-sm font-semibold">{h.ticker}</span>
                {h.weight !== undefined ? (
                  <span className="font-mono text-xs text-muted-foreground">
                    {(h.weight * 100).toFixed(0)}%
                  </span>
                ) : null}
                <ChevronDown
                  className={cn(
                    "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                    isOpen && "rotate-180",
                  )}
                  aria-hidden="true"
                />
              </button>
              {isOpen ? (
                <div className="border-t border-border bg-muted/10 px-3 py-3">
                  {entry === undefined || entry === "loading" ? (
                    <div className="space-y-3" data-testid={`holding-loading-${h.ticker}`}>
                      <Skeleton className="h-4 w-1/3" />
                      <Skeleton className="h-28" />
                      <Skeleton className="h-28" />
                    </div>
                  ) : entry === "error" ? (
                    <div className="space-y-2">
                      <p className="text-xs text-muted-foreground">
                        Couldn&rsquo;t load {h.ticker}&rsquo;s profile.
                      </p>
                      <Link
                        href={`/stocks/${h.ticker}` as Route}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                      >
                        Open full profile <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>
                  ) : (
                    <HoldingPreview ticker={h.ticker} data={entry} />
                  )}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function PortfolioDiagnosis({
  context,
  updateContext,
  advance,
  back,
}: FlowStepProps<PortfolioModeContext>) {
  const title = useFlowCopy("portfolio_mode", "diagnose_title");
  const subtitle = useFlowCopy("portfolio_mode", "diagnose_subtitle");
  const styleLabel = useFlowCopy("portfolio_mode", "diagnose_style_label");
  const factorLabel = useFlowCopy("portfolio_mode", "diagnose_factor_label");
  const sectorLabel = useFlowCopy("portfolio_mode", "diagnose_sector_label");
  const behaviorLabel = useFlowCopy("portfolio_mode", "diagnose_behavior_label");
  const riskLabel = useFlowCopy("portfolio_mode", "diagnose_risk_label");
  const holdingsLabel = useFlowCopy("portfolio_mode", "diagnose_holdings_label");
  const continueLabel = useFlowCopy("portfolio_mode", "diagnose_continue");
  const errorMsg = useFlowCopy("portfolio_mode", "diagnose_error");
  const rateLimitMsg = useFlowCopy("portfolio_mode", "diagnose_rate_limited");

  // Pull the backend token off the next-auth session when present. The
  // POST /api/portfolio/diagnose route accepts both authenticated and
  // anonymous callers (the backend resolves a synthetic anonymous user
  // when no bearer token is sent), so this is `undefined` for signed-out
  // visitors and a string for signed-in ones — both produce a working
  // diagnose response. We wait for `sessionStatus !== "loading"` before
  // firing so a signed-in visitor never gets a one-time anonymous run on
  // the brief next-auth boot window.
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [diagnosis, setDiagnosis] = React.useState<PortfolioDiagnosisPayload | undefined>(
    context.diagnosis,
  );
  const [loading, setLoading] = React.useState(!context.diagnosis);
  const [error, setError] = React.useState<string | null>(null);

  const holdings = context.holdings;

  React.useEffect(() => {
    if (!holdings || holdings.length === 0) {
      setError("No holdings supplied — go back to the upload step.");
      setLoading(false);
      return;
    }
    // If we already have a diagnosis in context (resumed flow), skip refetch.
    if (context.diagnosis) {
      setDiagnosis(context.diagnosis);
      setLoading(false);
      return;
    }
    // Wait for next-auth to resolve before firing — otherwise a signed-in
    // visitor would briefly call the route as anonymous.
    if (sessionStatus === "loading") {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    diagnosePortfolio(holdings, backendToken)
      .then((resp) => {
        if (cancelled) return;
        setDiagnosis(resp.diagnosis);
        updateContext({ diagnosis: resp.diagnosis });
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof UpgradeRequiredError) {
          setError(rateLimitMsg);
        } else {
          setError(errorMsg);
        }
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // updateContext / errorMsg / rateLimitMsg are stable references for this render.
    // sessionStatus + backendToken are included so the effect re-fires once
    // next-auth resolves the session — signed-in visitors then make their
    // diagnose call with the bearer token, not as anonymous.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(holdings), sessionStatus, backendToken]);

  if (loading) return <DiagSkeleton />;
  if (error) {
    return (
      <section className="space-y-3" data-testid="portfolio-diagnosis-error">
        <p className="text-sm text-red-600">{error}</p>
      </section>
    );
  }
  if (!diagnosis) return <DiagSkeleton />;

  const risk = diagnosis;
  const volStr = risk.realized_vol_1y !== null && risk.realized_vol_1y !== undefined
    ? `${(risk.realized_vol_1y * 100).toFixed(1)}% annualized vol`
    : "—";
  const ddStr = risk.max_drawdown_5y !== null && risk.max_drawdown_5y !== undefined
    ? `${(risk.max_drawdown_5y * 100).toFixed(1)}% 5y max drawdown`
    : "—";

  return (
    <section className="space-y-6" data-testid="portfolio-diagnosis">
      <button
        type="button"
        onClick={back}
        className="text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        ← Back
      </button>
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <p className="text-sm text-muted-foreground">
        {diagnosis.n_holdings} {diagnosis.n_holdings === 1 ? "holding" : "holdings"} •{" "}
        <span className="font-mono">{volStr}</span> •{" "}
        <span className="font-mono">{ddStr}</span>
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-border p-4">
          <h2 className="text-sm font-semibold">{styleLabel}</h2>
          <div className="mt-3">
            <StyleMixView diag={diagnosis} />
          </div>
        </div>

        <div className="rounded-xl border border-border p-4">
          <h2 className="text-sm font-semibold">{factorLabel}</h2>
          <div className="mt-3">
            <FactorView diag={diagnosis} />
          </div>
        </div>

        <div className="rounded-xl border border-border p-4">
          <h2 className="text-sm font-semibold">{sectorLabel}</h2>
          <div className="mt-3">
            <SectorView diag={diagnosis} />
          </div>
        </div>

        <div className="rounded-xl border border-border p-4">
          <h2 className="text-sm font-semibold">{behaviorLabel}</h2>
          <div className="mt-3">
            <BehaviorView diag={diagnosis} />
          </div>
        </div>
      </div>

      <HoldingsExplorer holdings={holdings ?? []} label={holdingsLabel} />

      {diagnosis.caveats.length > 0 ? (
        <ul className="space-y-1 rounded-xl bg-muted/30 p-3 text-xs text-muted-foreground">
          {diagnosis.caveats.map((c) => (
            <li key={c}>• {c}</li>
          ))}
        </ul>
      ) : null}

      <div className="sr-only" aria-hidden="true">
        {riskLabel}: {volStr}; {ddStr}
      </div>

      <div>
        <Button onClick={advance} data-testid="portfolio-diagnosis-continue">
          {continueLabel}
        </Button>
      </div>
    </section>
  );
}
