"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { AlertTriangle, ChevronRight } from "lucide-react";
import { getCompanyOverview, UpgradeRequiredError } from "@/lib/api";
import type { CompanyOverviewResponse, EntitlementErrorDetail } from "@/lib/contracts";
import { SoftPaywall } from "@/components/SoftPaywall";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BusinessModelSection } from "./_business-model-section";
import { MarketPositionSectionUI } from "./_market-position-section";
import type { Route } from "next";
import { SentimentTab } from "./_sentiment-tab";
import { ChatWidget } from "@/components/ChatWidget";
import { EvaluationDashboard } from "./_evaluation-dashboard";
import { WatchlistButton } from "@/components/community/watchlist-button";
import { VoteBar } from "@/components/community/vote-bar";
import { AssetBehaviorFingerprintCard } from "@/components/strategy-picker/AssetBehaviorFingerprintCard";
import { ApplyStrategyCTA } from "@/lib/flows/bricks/apply-strategy-cta";
import { startFlow } from "@/lib/flows/runtime";
// Side-effect import — registers `one_asset_mode` in the flow registry
// so startFlow below can find it. Idempotent via the getFlow() guard
// inside one-asset-mode.ts.
import "@/lib/flows/one-asset-mode";
import { useLiveQuotes } from "@/lib/useLiveQuotes";
import { dispatchChatSeed } from "@/lib/chat-widget-event-bus";
import { track } from "@/lib/analytics";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

// ── Main page ─────────────────────────────────────────────────────────────────

type Tab = "overview" | "sentiment";

function CompanyPageInner() {
  const { ticker } = useParams<{ ticker: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const activeTab = (searchParams.get("tab") as Tab) || "overview";

  const [data, setData] = useState<CompanyOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gateDetail, setGateDetail] = useState<EntitlementErrorDetail | null>(null);
  // Sprint 2 Mode 1 refactor: the in-page <StrategyBuilderModal> +
  // builderOpen / builderIdea state is gone — the Apply CTA now calls
  // startFlow('one_asset_mode') and the universal /flow shell renders
  // the steps. State that used to live here is now in the flow runtime
  // and persists via sessionStorage so closing the tab resumes.

  // Live price for this ticker. Falls back to data.price (loaded server-side
  // via FMP) until the first poll resolves; from then on overrides it.
  const liveSymbols = ticker ? [ticker.toUpperCase()] : [];
  const { quotes: liveQuotes } = useLiveQuotes(liveSymbols);
  const liveQuote = ticker ? liveQuotes[ticker.toUpperCase()] : undefined;

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    const loadTimer = setTimeout(() => {
      setLoading(true);
      setError(null);
      setGateDetail(null);
      getCompanyOverview(ticker.toUpperCase())
        .then((overview) => { if (!cancelled) setData(overview); })
        .catch((e) => {
          if (cancelled) return;
          if (e instanceof UpgradeRequiredError) {
            setGateDetail(e.entitlement);
          } else {
            setError(e.message || "Failed to load company data");
          }
        })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 0);
    return () => {
      cancelled = true;
      clearTimeout(loadTimer);
    };
  }, [ticker]);

  const setTab = (tab: Tab) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.push(`/stocks/${ticker}?${params.toString()}` as Route);
  };

  if (loading) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-6 md:px-6">
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      </main>
    );
  }

  if (gateDetail) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-12">
          <SoftPaywall detail={gateDetail} />
        </div>
      </main>
    );
  }

  if (error || !data) {
    const isNotConfigured = error?.includes("403") || error?.includes("not configured");
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-12 text-center">
          <p className="text-base font-medium text-foreground">
            {isNotConfigured ? "Fundamental data unavailable" : "Unable to load company data"}
          </p>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {isNotConfigured
              ? "The FMP API key may not be configured or may need a Starter plan."
              : error || "The company may not exist or the backend is unreachable. Try again."}
          </p>
          <div className="mt-5 flex items-center justify-center gap-3">
            <button
              onClick={() => { setError(null); setLoading(true); getCompanyOverview(ticker.toUpperCase()).then(setData).catch((e) => setError(e.message)).finally(() => setLoading(false)); }}
              className="text-sm font-medium text-primary hover:underline"
            >
              Retry
            </button>
            <span className="text-muted-foreground">·</span>
            <Link href={"/stocks" as Route} className="text-sm text-muted-foreground hover:text-foreground hover:underline">← Back to Screener</Link>
          </div>
        </div>
      </main>
    );
  }

  const bm = data.business_map;
  const mp = data.market_position;

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1200px] space-y-6 px-4 py-6 md:px-6 lg:px-8">

        {/* Breadcrumb */}
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Link href={"/stocks" as Route} className="hover:text-foreground transition-colors">Stocks</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="font-mono font-medium text-foreground">{data.symbol}</span>
        </div>

        {/* Company header */}
        <div className="flex flex-col gap-4 rounded-xl border border-border bg-white p-5 shadow-sm sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-2xl font-bold">{data.symbol}</span>
              {(liveQuote?.price ?? data.price) != null && (
                <span className="font-mono text-xl font-semibold">
                  ${(liveQuote?.price ?? data.price!).toFixed(2)}
                </span>
              )}
              {liveQuote && (
                <span
                  className={`font-mono text-sm font-medium ${
                    liveQuote.change_percent >= 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-rose-600 dark:text-rose-400"
                  }`}
                >
                  {liveQuote.change_percent >= 0 ? "+" : ""}
                  {liveQuote.change_percent.toFixed(2)}%
                </span>
              )}
            </div>
            <div className="mt-1 text-base text-muted-foreground">{data.name}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {data.sector && <Badge variant="outline" className="text-xs">{data.sector}</Badge>}
              {data.industry && <Badge variant="outline" className="text-xs">{data.industry}</Badge>}
              {data.exchange && <Badge variant="outline" className="font-mono text-xs">{data.exchange}</Badge>}
              {data.market_cap && <Badge variant="outline" className="font-mono text-xs">{fmtMoney(data.market_cap)} mkt cap</Badge>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* PRD-14 + Sprint 2 Mode 1 refactor: secondary trigger for
                Mode 1. The brick's prop surface (onClick) is unchanged
                from PRD-14; the implementation now launches the
                `one_asset_mode` flow instead of opening the legacy
                in-page <StrategyBuilderModal>. The ticker rides in via
                initialContext so the flow's first step auto-advances. */}
            <ApplyStrategyCTA
              ticker={data.symbol}
              from="stock_page"
              variant="secondary"
              compact
              onClick={() => {
                track("stock_page_apply_strategy_clicked", { ticker: data.symbol });
                // Open the chat widget alongside the flow so the user
                // has an active research-partner. See
                // chat-widget-event-bus.ts.
                dispatchChatSeed({
                  greeting:
                    `Got it — I'll help you build a strategy on ${data.symbol}. ` +
                    `Pick a template from the wizard, or tell me what you're trying to capture and I'll suggest one.`,
                  contextHint: data.symbol,
                });
                startFlow("one_asset_mode", {
                  initialContext: {
                    fromTrigger: "stock_page/apply_strategy",
                    ticker: data.symbol,
                  },
                });
              }}
            />
            <WatchlistButton symbol={data.symbol} />
          </div>
        </div>

        {/* Tab nav */}
        <div className="flex gap-1 rounded-lg border border-border bg-muted/30 p-1">
          {(["overview", "sentiment"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setTab(tab)}
              className={cn(
                "flex-1 rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-all",
                activeTab === tab
                  ? "bg-white shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {tab === "overview" ? "Overview" : "News & Sentiment"}
            </button>
          ))}
        </div>

        {/* Sentiment tab */}
        {activeTab === "sentiment" && <SentimentTab symbol={ticker.toUpperCase()} />}

        {/* Overview tab content */}
        {activeTab === "overview" && <>

        {/* ── TIER 2: Asset Evaluation ─────────────────────────────────────── */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
            <div className="h-2 w-2 rounded-full bg-primary" />
            <h2 className="font-heading text-sm font-semibold">Fundamental Analysis</h2>
            <Badge variant="outline" className="ml-auto text-[10px] font-mono">Health · Valuation · Trend</Badge>
          </div>
          <div className="p-5">
            <EvaluationDashboard data={data} />
          </div>
        </section>

        {/* ── TIER 3: Business Model ────────────────────────────────────── */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
            <div className="h-2 w-2 rounded-full bg-primary" />
            <h2 className="font-heading text-sm font-semibold">Business Model</h2>
            <Badge variant="outline" className="ml-auto text-[10px] font-mono">
              {bm.confidence} · {data.revenue_segments.segment_names.length > 0 ? `${data.revenue_segments.segment_names.length} segments` : "FMP data"}
            </Badge>
          </div>
          <div className="p-5">
            <BusinessModelSection seg={data.revenue_segments} bm={bm} />
          </div>
        </section>

        {/* ── TIER 4: Market Position ───────────────────────────────────── */}
        <section className="rounded-xl border border-border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
            <div className="h-2 w-2 rounded-full bg-[var(--warning-amber)]" />
            <h2 className="font-heading text-sm font-semibold">Market Position</h2>
            <Badge variant="outline" className="ml-auto text-[10px] font-mono">
              {mp.confidence} · {mp.competitor_segments.length > 0 ? `${mp.competitor_segments.length} segments` : "10-K data"}
            </Badge>
          </div>
          <div className="p-5">
            <MarketPositionSectionUI
              mp={mp}
              symbol={data.symbol}
              competitorSegments={mp.competitor_segments}
            />
          </div>
        </section>

        {/* Community sentiment */}
        <section className="rounded-xl border border-border bg-white p-5 shadow-sm">
          <h2 className="mb-4 font-heading text-sm font-semibold">Community Sentiment</h2>
          <VoteBar symbol={data.symbol} />
        </section>

        {/* PRD-14: Asset Behavior Fingerprint (Module 2 component, used
            as-is). Self-fetching mode — the page is a Client Component
            so we let the card own its loading state rather than
            threading SSR data through. */}
        <AssetBehaviorFingerprintCard symbol={data.symbol} />

        {/* Disclaimer */}
        <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500/70" />
          {data.disclaimer}
        </div>

        </> /* end overview tab */}

      </div>
    </main>
  );
}

export default function CompanyPage() {
  return (
    <Suspense fallback={
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-6 md:px-6">
          <div className="space-y-4">
            <Skeleton className="h-8 w-48" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </div>
      </main>
    }>
      <CompanyPageInner />
      {/* Stage 7 ticket #7: chat widget on stock-detail surface */}
      <ChatWidget />
    </Suspense>
  );
}
