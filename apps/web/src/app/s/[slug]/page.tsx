"use client";

export const dynamic = "force-dynamic";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { ArrowRight, CopyPlus, Loader2, TrendingDown, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ShareButton } from "@/components/ShareButton";
import { VerifiedBadge } from "@/components/VerifiedBadge";
import {
  createSavedStrategy,
  getPublishedStrategy,
  trackAttributionVisit,
  UpgradeRequiredError,
} from "@/lib/api";
import type { PublishedStrategyDetail, StrategyJson } from "@/lib/contracts";

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v == null || isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

function fmtNumber(v: number | null | undefined, digits = 2): string {
  if (v == null || isNaN(v)) return "—";
  return v.toFixed(digits);
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PublishedStrategyPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Inner />
    </Suspense>
  );
}

function Inner() {
  const { slug } = useParams<{ slug: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { data: session, status } = useSession();
  const via = searchParams.get("via");
  const backendToken = (session as unknown as { backendToken?: string } | null)?.backendToken;

  const [data, setData] = useState<PublishedStrategyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [cloneError, setCloneError] = useState<string | null>(null);

  // Fetch the strategy
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    getPublishedStrategy(slug)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  // Fire attribution track on mount when ?via=<handle> is present.
  useEffect(() => {
    if (!via || typeof window === "undefined") return;
    trackAttributionVisit({
      url: window.location.href,
      via,
    }).catch(() => {
      /* attribution failures must not block page render */
    });
  }, [via]);

  async function handleClone() {
    if (!data || !backendToken) return;
    setCloneError(null);
    setCloning(true);
    try {
      await createSavedStrategy(
        {
          title: data.title,
          strategy_json: data.strategy_json,
          is_public: false,
          backtest_record_id: undefined, // we don't have a fresh BacktestRecord; user will re-run in workspace
        },
        backendToken,
      );
      router.push("/workspace");
    } catch (err) {
      if (err instanceof UpgradeRequiredError) {
        // UpgradeModal already dispatched by fetchApi interceptor
        setCloneError(null);
      } else {
        setCloneError((err as Error).message || "Couldn't clone right now.");
      }
    } finally {
      setCloning(false);
    }
  }

  if (loading) return <PageSkeleton />;
  if (notFound || !data) return <NotFound />;

  const isAnonymous = status !== "authenticated";
  const signupHref = via
    ? `/signup?via=${encodeURIComponent(via)}&from=share`
    : "/signup?from=share";
  const m = data.metrics;
  const isPositive = (m.total_return ?? 0) >= 0;

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-4 py-8 md:px-6 md:py-12">

        {/* Persistent CTA (anonymous viewers) */}
        {isAnonymous && (
          <div className="mb-6 rounded-xl border border-primary/30 bg-primary/5 p-4 sm:flex sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium">Try this strategy yourself — free</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Sign up with Google. Get 5 custom backtests per week, unlimited templates.
              </p>
            </div>
            <Button asChild size="sm" className="mt-3 sm:mt-0">
              <Link href={signupHref as Route}>
                Continue with Google
                <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        )}

        {/* Title + author + share */}
        <header className="space-y-2">
          <div className="flex items-start justify-between gap-3">
            <h1 className="font-heading text-2xl font-bold leading-tight sm:text-3xl">
              {data.title}
            </h1>
            <div className="flex shrink-0 items-center gap-2">
              {!isAnonymous && (
                <Button
                  size="sm"
                  onClick={handleClone}
                  disabled={cloning}
                  className="gap-1.5"
                >
                  {cloning ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <>
                      <CopyPlus className="h-3.5 w-3.5" />
                      Clone
                    </>
                  )}
                </Button>
              )}
              <ShareButton path={`/s/${data.slug}`} />
            </div>
          </div>
          {cloneError && (
            <p className="text-xs text-destructive">{cloneError}</p>
          )}

          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-foreground">
                {data.author.display_name ?? data.author.handle ?? "Anonymous"}
              </span>
              <VerifiedBadge badge={data.author.badge} />
              {data.author.handle && (
                <span className="text-muted-foreground">@{data.author.handle}</span>
              )}
            </div>
            <span aria-hidden>·</span>
            <Badge variant="outline" className="font-normal text-xs">
              {data.strategy_type.replace(/_/g, " ")}
            </Badge>
          </div>

          {data.description && (
            <p className="mt-2 max-w-prose text-sm text-muted-foreground">
              {data.description}
            </p>
          )}
        </header>

        {/* Headline metric — return */}
        <section className="mt-6 rounded-xl border border-border bg-card p-6">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            Total return
          </p>
          <div className="mt-1 flex items-baseline gap-3">
            <span
              className={`text-4xl font-bold ${
                isPositive ? "text-emerald-600" : "text-rose-600"
              }`}
            >
              {fmtPct(m.total_return, 1)}
            </span>
            {m.buy_and_hold_return != null && (
              <span className="text-sm text-muted-foreground">
                vs buy &amp; hold {fmtPct(m.buy_and_hold_return, 1)}
              </span>
            )}
            {isPositive ? (
              <TrendingUp className="h-5 w-5 text-emerald-600" />
            ) : (
              <TrendingDown className="h-5 w-5 text-rose-600" />
            )}
          </div>
        </section>

        {/* Metric grid */}
        <section className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard label="Annualized" value={fmtPct(m.annualized_return, 1)} />
          <MetricCard label="Sharpe" value={fmtNumber(m.sharpe_ratio, 2)} />
          <MetricCard label="Max drawdown" value={fmtPct(m.max_drawdown, 1)} negative />
          <MetricCard label="Win rate" value={fmtPct(m.win_rate, 0)} />
        </section>

        {/* Universe + benchmark */}
        <section className="mt-4 rounded-xl border border-border bg-card p-4">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            Universe
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {data.universe.map((sym) => (
              <Badge key={sym} variant="outline" className="font-mono text-xs">
                {sym}
              </Badge>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Benchmark: <span className="font-mono">{data.benchmark}</span> ·{" "}
            {data.universe.length} tickers
          </p>
        </section>

        {/* Equity curve preview (text-only for v1; chart library wiring deferred) */}
        {data.equity_curve.length > 0 && (
          <section className="mt-4 rounded-xl border border-border bg-card p-4">
            <p className="text-xs uppercase tracking-widest text-muted-foreground">
              Backtest period
            </p>
            <p className="mt-1 text-sm">
              {data.equity_curve[0]?.date ?? "—"} →{" "}
              {data.equity_curve[data.equity_curve.length - 1]?.date ?? "—"} (
              {data.equity_curve.length} sample points)
            </p>
          </section>
        )}

        {/* Bottom CTA — anonymous */}
        {isAnonymous && (
          <div className="mt-8 rounded-xl border border-primary/30 bg-primary/5 p-5 text-center">
            <p className="text-sm font-medium">Want to try this yourself?</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Scout is free — 5 custom backtests per week, unlimited templates.
            </p>
            <Button asChild size="sm" className="mt-4">
              <Link href={signupHref as Route}>
                Continue with Google
                <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        )}

      </div>
    </main>
  );
}

function MetricCard({
  label,
  value,
  negative,
}: {
  label: string;
  value: string;
  negative?: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={`mt-1 text-base font-semibold ${
          negative ? "text-rose-600" : "text-foreground"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function PageSkeleton() {
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-3xl px-4 py-12 text-center">
        <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    </main>
  );
}

function NotFound() {
  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <h1 className="text-lg font-semibold">Strategy not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The link may have expired or the strategy was unpublished.
        </p>
        <Button asChild variant="outline" size="sm" className="mt-5">
          <Link href={"/community" as Route}>Browse community</Link>
        </Button>
      </div>
    </main>
  );
}
