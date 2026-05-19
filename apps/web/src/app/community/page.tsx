"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { signIn, useSession } from "next-auth/react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart2,
  CheckCircle2,
  Clock,
  FileText,
  Flame,
  MessageSquare,
  Newspaper,
  Scale,
  Send,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";
import {
  addStockThesis,
  getCommunityBoard,
  getStockTheses,
} from "@/lib/community-api";
import { getPublicStrategies, getStrategyLivePerformance } from "@/lib/api";
import type { LivePerformance, PublicStrategyItem, SignalScore, StockThesis } from "@/lib/contracts";
import { UpvoteButton } from "@/components/community/upvote-button";
import { VoteBar } from "@/components/community/vote-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type BoardWindow = "today" | "7d" | "30d" | "all";
type BoardFilter = "all" | "bullish" | "bearish" | "controversial" | "rising";
type MobileTab = "stocks" | "strategies" | "debates";

const BOARD_WINDOWS: Array<{ id: BoardWindow; label: string }> = [
  { id: "today", label: "Today" },
  { id: "7d", label: "7D" },
  { id: "30d", label: "30D" },
  { id: "all", label: "All" },
];

const BOARD_FILTERS: Array<{ id: BoardFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "bullish", label: "Bullish" },
  { id: "bearish", label: "Bearish" },
  { id: "controversial", label: "Contested" },
  { id: "rising", label: "Rising" },
];

function RankBadge({ rank }: { rank: number }) {
  const topClass =
    rank === 1 ? "bg-amber-100 text-amber-700 ring-amber-300"
    : rank === 2 ? "bg-slate-100 text-slate-600 ring-slate-300"
    : rank === 3 ? "bg-orange-100 text-orange-700 ring-orange-300"
    : "bg-transparent text-muted-foreground ring-transparent";

  return (
    <div className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ring-1", topClass)}>
      {rank}
    </div>
  );
}

function SignalBar({ score }: { score: number }) {
  const color = score >= 65 ? "bg-emerald-500" : score >= 52 ? "bg-amber-500" : "bg-slate-300";
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
      <div className={cn("h-full rounded-full transition-all duration-300", color)} style={{ width: `${Math.min(100, score)}%` }} />
    </div>
  );
}

function stanceClass(stance: "bull" | "bear" | "hold") {
  if (stance === "bull") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (stance === "bear") return "border-red-200 bg-red-50 text-red-700";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function getBullPct(item: SignalScore) {
  if (item.total_votes <= 0) return 0;
  return Math.round((item.bull_votes / item.total_votes) * 100);
}

function formatDate(value?: string | null) {
  if (!value) return "No discussion yet";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ReturnSparkline({ curve }: { curve: Array<{ date: string; value: number }> }) {
  if (!curve || curve.length < 3) return null;
  const isPositive = curve[curve.length - 1].value >= curve[0].value;

  return (
    <div className="h-8 w-16 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={curve}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={isPositive ? "#16a34a" : "#dc2626"}
            strokeWidth={1.5}
            dot={false}
          />
          <Tooltip contentStyle={{ display: "none" }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function computeStrategyTrust(s: PublicStrategyItem, live: LivePerformance | null) {
  let score = s.trust_score ?? 50;
  if (live?.days_tracked) score += Math.min(10, live.days_tracked);
  if (live?.total_return != null) score += Math.max(-8, Math.min(8, live.total_return * 100));
  score += Math.min(8, s.upvote_count * 1.5);
  return Math.max(0, Math.min(100, Math.round(score)));
}

function BoardRow({
  item,
  rank,
  selected,
  onSelect,
}: {
  item: SignalScore;
  rank: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const bullPct = getBullPct(item);
  const isContested = item.total_votes >= 2 && item.bull_votes > 0 && item.bear_votes > 0;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full cursor-pointer items-center gap-3 rounded-lg border bg-white px-4 py-3 text-left shadow-sm transition-all hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
        selected ? "border-primary/50 ring-1 ring-primary/20" : "border-border/70"
      )}
    >
      <RankBadge rank={rank} />

      <div className="w-16 shrink-0">
        <div className="font-mono text-sm font-bold text-foreground">{item.symbol}</div>
        <div className="text-[10px] text-muted-foreground">{formatDate(item.latest_thesis_at)}</div>
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <SignalBar score={item.signal_score} />
          <span className="w-8 font-mono text-[10px] font-semibold tabular-nums text-muted-foreground">
            {item.signal_score.toFixed(0)}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] text-muted-foreground">{item.signal_label}</span>
          {item.thesis_count > 0 && (
            <Badge variant="outline" className="h-5 rounded-md px-1.5 text-[10px]">
              {item.thesis_count} theses
            </Badge>
          )}
          {isContested && (
            <Badge variant="outline" className="h-5 rounded-md border-amber-200 bg-amber-50 px-1.5 text-[10px] text-amber-700">
              contested
            </Badge>
          )}
        </div>
      </div>

      <div className="hidden shrink-0 items-center gap-4 text-xs text-muted-foreground sm:flex">
        <span className="flex items-center gap-1"><Users className="h-3 w-3" />{item.watchlist_count}</span>
        <span className="flex items-center gap-1 text-emerald-600"><TrendingUp className="h-3 w-3" />{bullPct}%</span>
        <span className="flex items-center gap-1"><BarChart2 className="h-3 w-3" />{item.strategy_run_count}</span>
        <span className="flex items-center gap-1"><MessageSquare className="h-3 w-3" />{item.thesis_count}</span>
      </div>

      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
    </button>
  );
}

function StrategyRow({
  s,
  rank,
  live,
}: {
  s: PublicStrategyItem;
  rank: number;
  live: LivePerformance | null;
}) {
  const ret = live?.total_return_pct;
  const hasReturn = ret != null;
  const isPositive = hasReturn && ret >= 0;
  const isToday = live?.error?.includes("Published today");
  const trust = computeStrategyTrust(s, live);

  return (
    <div className={cn(
      "flex items-center gap-3 rounded-lg border bg-white px-4 py-3 shadow-sm transition-all hover:border-primary/40 hover:shadow-md",
      rank <= 3 ? "border-border" : "border-border/60"
    )}>
      <RankBadge rank={rank} />

      <div className="w-20 shrink-0 text-right">
        {isToday ? (
          <div className="text-[10px] leading-tight text-muted-foreground">Tracking<br />next session</div>
        ) : (
          <>
            <div className={cn("font-mono text-base font-bold tabular-nums",
              hasReturn ? (isPositive ? "text-emerald-600" : "text-red-600") : "text-muted-foreground"
            )}>
              {hasReturn ? `${isPositive ? "+" : ""}${ret.toFixed(2)}%` : "--"}
            </div>
            <div className="text-[9px] text-muted-foreground">{live?.days_tracked ? `${live.days_tracked}d live` : "paper"}</div>
          </>
        )}
      </div>

      {live?.equity_curve && live.equity_curve.length >= 3 && (
        <ReturnSparkline curve={live.equity_curve as Array<{ date: string; value: number }>} />
      )}

      <div className="min-w-0 flex-1">
        <Link
          href={`/strategies/${s.slug}` as Route}
          className="block truncate text-sm font-semibold transition-colors hover:text-primary"
        >
          {s.name}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="h-5 rounded-md border-blue-200 bg-blue-50 px-1.5 text-[10px] text-blue-700">
            {s.verification_status ?? "Backtested"}
          </Badge>
          <Badge variant="outline" className="h-5 rounded-md px-1.5 text-[10px]">
            Trust {trust}/100
          </Badge>
          {live?.current_signal && live.current_signal !== "unknown" && (
            <Badge variant="outline" className="h-5 rounded-md px-1.5 text-[10px] capitalize">
              {live.current_signal}
            </Badge>
          )}
          <span className="text-[10px] text-muted-foreground">Not financial advice</span>
        </div>
      </div>

      <UpvoteButton slug={s.slug} />
    </div>
  );
}

function ThesisCard({ thesis }: { thesis: StockThesis }) {
  return (
    <div className="rounded-lg border border-border bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant="outline" className={cn("h-6 rounded-md px-2 text-[10px] uppercase", stanceClass(thesis.stance))}>
          {thesis.stance}
        </Badge>
        <Link href={`/stocks/${thesis.symbol}` as Route} className="font-mono text-xs font-bold hover:text-primary">
          {thesis.symbol}
        </Link>
        <span className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground">
          <Clock className="h-3 w-3" />
          {formatDate(thesis.created_at)}
        </span>
      </div>
      <p className="line-clamp-3 text-sm leading-6 text-foreground">{thesis.thesis}</p>
      <div className="mt-3 rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Risk:</span> {thesis.risks}
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 text-[10px] text-muted-foreground">
        <span>{thesis.display_name ?? "Community member"} · {thesis.timeframe}</span>
        {thesis.evidence_url && (
          <a href={thesis.evidence_url} target="_blank" rel="noreferrer" className="font-medium text-primary hover:underline">
            Evidence
          </a>
        )}
      </div>
    </div>
  );
}

function EvidencePanel({
  selected,
  theses,
}: {
  selected: SignalScore | null;
  theses: StockThesis[];
}) {
  if (!selected) {
    return (
      <div className="rounded-lg border border-border bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-blue-600" />
          <h3 className="text-sm font-semibold">Evidence Panel</h3>
        </div>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          Select a stock to see why retail attention is showing up: watchlists, votes, tested strategies, and structured theses.
        </p>
      </div>
    );
  }

  const bullPct = getBullPct(selected);

  return (
    <div className="rounded-lg border border-border bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-blue-600" />
            <h3 className="text-sm font-semibold">Why {selected.symbol} is trending</h3>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Community attention, not a buy signal.</p>
        </div>
        <Link href={`/stocks/${selected.symbol}` as Route} className="text-xs font-medium text-primary hover:underline">
          Stock page
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {[
          { label: "Attention", value: selected.signal_score.toFixed(0), icon: Activity },
          { label: "Bull split", value: `${bullPct}%`, icon: TrendingUp },
          { label: "Tested strategies", value: selected.strategy_run_count, icon: BarChart2 },
          { label: "Theses", value: selected.thesis_count, icon: FileText },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-md border border-border/70 bg-muted/20 px-3 py-2">
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <Icon className="h-3 w-3" />
              {label}
            </div>
            <div className="mt-1 font-mono text-lg font-bold tabular-nums text-foreground">{value}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold">
          <MessageSquare className="h-3.5 w-3.5 text-primary" />
          Latest theses
        </div>
        {theses.length === 0 ? (
          <p className="rounded-md bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            No structured thesis yet. Be first to add the evidence and the risk.
          </p>
        ) : (
          theses.slice(0, 2).map((thesis) => <ThesisCard key={thesis.id} thesis={thesis} />)
        )}
      </div>
    </div>
  );
}

function ThesisForm({
  defaultSymbol,
  onCreated,
}: {
  defaultSymbol?: string;
  onCreated: (thesis: StockThesis) => void;
}) {
  const { data: session } = useSession();
  const [symbol, setSymbol] = useState(defaultSymbol ?? "AAPL");
  const [stance, setStance] = useState<"bull" | "bear" | "hold">("bull");
  const [timeframe, setTimeframe] = useState("1-3 months");
  const [thesis, setThesis] = useState("");
  const [risks, setRisks] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session?.user) {
      signIn("google");
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const created = await addStockThesis({
        symbol,
        stance,
        timeframe,
        thesis,
        risks,
        evidence_url: evidenceUrl.trim() || null,
      });
      onCreated(created);
      setThesis("");
      setRisks("");
      setEvidenceUrl("");
      setMessage("Thesis published with risk context.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to publish thesis.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-border bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Send className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Share Stock Thesis</h3>
      </div>

      <div className="grid gap-3">
        <label className="grid gap-1 text-xs font-medium text-foreground">
          Ticker
          <input
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
            className="h-9 rounded-md border border-border bg-white px-3 font-mono text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            maxLength={12}
          />
        </label>

        <div className="grid grid-cols-3 gap-1 rounded-md border border-border bg-muted/30 p-1">
          {(["bull", "bear", "hold"] as const).map((next) => (
            <button
              key={next}
              type="button"
              onClick={() => setStance(next)}
              className={cn(
                "h-8 cursor-pointer rounded px-2 text-xs font-semibold capitalize transition-colors",
                stance === next ? "bg-white shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {next}
            </button>
          ))}
        </div>

        <label className="grid gap-1 text-xs font-medium text-foreground">
          Timeframe
          <input
            value={timeframe}
            onChange={(event) => setTimeframe(event.target.value)}
            className="h-9 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          />
        </label>

        <label className="grid gap-1 text-xs font-medium text-foreground">
          Thesis
          <textarea
            value={thesis}
            onChange={(event) => setThesis(event.target.value)}
            rows={4}
            className="resize-none rounded-md border border-border bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            placeholder="What evidence makes this worth watching?"
          />
        </label>

        <label className="grid gap-1 text-xs font-medium text-foreground">
          Risk
          <textarea
            value={risks}
            onChange={(event) => setRisks(event.target.value)}
            rows={3}
            className="resize-none rounded-md border border-border bg-white px-3 py-2 text-sm leading-6 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            placeholder="What would make this thesis wrong?"
          />
        </label>

        <label className="grid gap-1 text-xs font-medium text-foreground">
          Evidence link
          <input
            value={evidenceUrl}
            onChange={(event) => setEvidenceUrl(event.target.value)}
            className="h-9 rounded-md border border-border bg-white px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            placeholder="Optional URL"
          />
        </label>
      </div>

      {message && <p className="mt-3 text-xs text-muted-foreground">{message}</p>}

      <Button type="submit" disabled={submitting} className="mt-4 w-full gap-2">
        <Send className="h-3.5 w-3.5" />
        {submitting ? "Publishing..." : session?.user ? "Publish Thesis" : "Sign in to publish"}
      </Button>
    </form>
  );
}

export default function CommunityPage() {
  const [items, setItems] = useState<SignalScore[]>([]);
  const [strategies, setStrategies] = useState<PublicStrategyItem[]>([]);
  const [latestTheses, setLatestTheses] = useState<StockThesis[]>([]);
  const [selectedTheses, setSelectedTheses] = useState<StockThesis[]>([]);
  const [boardWindow, setBoardWindow] = useState<BoardWindow>("7d");
  const [boardFilter, setBoardFilter] = useState<BoardFilter>("all");
  const [loadingBoard, setLoadingBoard] = useState(true);
  const [loadingStrategies, setLoadingStrategies] = useState(true);
  const [livePerfs, setLivePerfs] = useState<Record<string, LivePerformance>>({});
  const [activeTab, setActiveTab] = useState<MobileTab>("stocks");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  useEffect(() => {
    getCommunityBoard(30, 0, boardWindow, boardFilter)
      .then((response) => {
        setItems(response.items);
        setSelectedSymbol((current) => current ?? response.items[0]?.symbol ?? null);
      })
      .catch(() => setItems([]))
      .finally(() => setLoadingBoard(false));
  }, [boardWindow, boardFilter]);

  useEffect(() => {
    getStockTheses(undefined, 8)
      .then((response) => setLatestTheses(response.theses))
      .catch(() => setLatestTheses([]));
  }, []);

  useEffect(() => {
    if (!selectedSymbol) return;
    getStockTheses(selectedSymbol, 4)
      .then((response) => setSelectedTheses(response.theses))
      .catch(() => setSelectedTheses([]));
  }, [selectedSymbol]);

  useEffect(() => {
    getPublicStrategies(30)
      .then((list) => {
        setStrategies(list);
        list.forEach((strategy) => {
          if (!strategy.live) {
            getStrategyLivePerformance(strategy.slug)
              .then((live) => setLivePerfs((prev) => ({ ...prev, [strategy.slug]: live })))
              .catch(() => {});
          }
        });
      })
      .catch(() => setStrategies([]))
      .finally(() => setLoadingStrategies(false));
  }, []);

  const selectedItem = useMemo(
    () => items.find((item) => item.symbol === selectedSymbol) ?? items[0] ?? null,
    [items, selectedSymbol],
  );

  const sortedStrategies = useMemo(() => {
    return [...strategies].sort((a, b) => {
      const aLive = a.live ?? livePerfs[a.slug] ?? null;
      const bLive = b.live ?? livePerfs[b.slug] ?? null;
      return computeStrategyTrust(b, bLive) - computeStrategyTrust(a, aLive);
    });
  }, [strategies, livePerfs]);

  const totalWatchlists = items.reduce((sum, item) => sum + item.watchlist_count, 0);
  const totalVotes = items.reduce((sum, item) => sum + item.total_votes, 0);
  const totalRuns = items.reduce((sum, item) => sum + item.strategy_run_count, 0);
  const totalTheses = items.reduce((sum, item) => sum + item.thesis_count, 0);
  const liveTracked = strategies.filter((strategy) => {
    const live = strategy.live ?? livePerfs[strategy.slug];
    return live?.days_tracked && live.days_tracked > 0;
  }).length;

  function handleCreatedThesis(thesis: StockThesis) {
    setLatestTheses((prev) => [thesis, ...prev].slice(0, 8));
    if (thesis.symbol === selectedSymbol) {
      setSelectedTheses((prev) => [thesis, ...prev].slice(0, 4));
    }
    getCommunityBoard(30, 0, boardWindow, boardFilter)
      .then((response) => setItems(response.items))
      .catch(() => {});
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1200px] space-y-6 px-4 py-8 md:px-6 lg:px-8">
        <section className="space-y-5">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Link href={"/" as Route} className="hover:text-foreground">Home</Link>
            <span>/</span>
            <span className="text-foreground">Community</span>
          </div>

          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="max-w-2xl">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">
                  Trust-first retail hub
                </Badge>
                <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                  Paper strategies only
                </Badge>
              </div>
              <h1 className="font-heading text-2xl font-bold md:text-3xl">Community</h1>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                See what retail investors are watching, voting on, and testing with evidence attached. Activity is informational, not a recommendation.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <a
                href="#share-thesis"
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
              >
                <FileText className="h-3.5 w-3.5" />
                Share Stock Thesis
              </a>
              <Link
                href={"/workspace" as Route}
                className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
              >
                <Target className="h-3.5 w-3.5" />
                Publish Strategy
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[
              { icon: Users, label: "Watchlist adds", value: totalWatchlists, color: "text-blue-600", bg: "bg-blue-50" },
              { icon: Scale, label: "Total votes", value: totalVotes, color: "text-emerald-600", bg: "bg-emerald-50" },
              { icon: BarChart2, label: "Strategy runs", value: totalRuns, color: "text-purple-600", bg: "bg-purple-50" },
              { icon: MessageSquare, label: "Stock theses", value: totalTheses, color: "text-amber-600", bg: "bg-amber-50" },
              { icon: ShieldCheck, label: "Live paper", value: liveTracked, color: "text-cyan-600", bg: "bg-cyan-50" },
            ].map(({ icon: Icon, label, value, color, bg }) => (
              <div key={label} className="flex items-center gap-3 rounded-lg border border-border bg-white px-4 py-3 shadow-sm">
                <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-lg", bg)}>
                  <Icon className={cn("h-4 w-4", color)} />
                </div>
                <div>
                  <div className={cn("font-mono text-lg font-bold tabular-nums", color)}>{value}</div>
                  <div className="text-[10px] text-muted-foreground">{label}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <div className="grid grid-cols-3 gap-1 rounded-lg border border-border bg-muted/30 p-1 lg:hidden">
          {(["stocks", "strategies", "debates"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={cn(
                "h-9 cursor-pointer rounded-md px-3 text-sm font-medium capitalize transition-colors",
                activeTab === tab ? "bg-white shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="grid gap-8 lg:grid-cols-3">
          <div className="space-y-8 lg:col-span-2">
            <section className={cn("space-y-3", activeTab !== "stocks" && "hidden lg:block")}>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <Flame className="h-4 w-4 text-orange-500" />
                  <h2 className="text-base font-semibold">Most Active Stocks</h2>
                  {!loadingBoard && <Badge variant="outline" className="font-mono text-[10px]">{items.length}</Badge>}
                </div>
                <div className="flex flex-wrap gap-2">
                  <div className="flex gap-1 rounded-md border border-border bg-white p-1">
                    {BOARD_WINDOWS.map((window) => (
                      <button
                        key={window.id}
                        type="button"
                        onClick={() => {
                          if (window.id !== boardWindow) setLoadingBoard(true);
                          setBoardWindow(window.id);
                        }}
                        className={cn(
                          "h-7 cursor-pointer rounded px-2 text-[11px] font-semibold transition-colors",
                          boardWindow === window.id ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                        )}
                      >
                        {window.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="flex gap-1 overflow-x-auto pb-1">
                {BOARD_FILTERS.map((filter) => (
                  <button
                    key={filter.id}
                    type="button"
                    onClick={() => {
                      if (filter.id !== boardFilter) setLoadingBoard(true);
                      setBoardFilter(filter.id);
                    }}
                    className={cn(
                      "h-8 shrink-0 cursor-pointer rounded-full border px-3 text-xs font-semibold transition-colors",
                      boardFilter === filter.id
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-white text-muted-foreground hover:border-primary/30 hover:text-foreground"
                    )}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>

              {loadingBoard ? (
                <div className="space-y-2">
                  {Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-16 w-full rounded-lg" />)}
                </div>
              ) : items.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border bg-white p-8 text-center">
                  <Users className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="mt-2 text-sm text-muted-foreground">No community activity for this filter yet.</p>
                  <Link href={"/stocks" as Route} className="mt-2 inline-block text-xs font-medium text-primary hover:underline">
                    Browse stocks
                  </Link>
                </div>
              ) : (
                <div className="space-y-2">
                  {items.map((item, index) => (
                    <BoardRow
                      key={item.symbol}
                      item={item}
                      rank={index + 1}
                      selected={selectedItem?.symbol === item.symbol}
                      onSelect={() => setSelectedSymbol(item.symbol)}
                    />
                  ))}
                </div>
              )}
            </section>

            <section className={cn("space-y-3", activeTab !== "strategies" && "hidden lg:block")}>
              <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <Target className="h-4 w-4 text-purple-500" />
                  <h2 className="text-base font-semibold">Public Strategies</h2>
                  {!loadingStrategies && <Badge variant="outline" className="font-mono text-[10px]">{sortedStrategies.length}</Badge>}
                </div>
                <span className="text-[10px] text-muted-foreground">Trust-weighted by paper tracking, drawdown, upvotes, and recency.</span>
              </div>

              {loadingStrategies ? (
                <div className="space-y-2">
                  {Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-20 w-full rounded-lg" />)}
                </div>
              ) : sortedStrategies.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border bg-white p-8 text-center">
                  <BarChart2 className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="mt-2 text-sm text-muted-foreground">No public strategies yet.</p>
                  <Link href={"/workspace" as Route} className="mt-2 inline-block text-xs font-medium text-primary hover:underline">
                    Build and publish a paper strategy
                  </Link>
                </div>
              ) : (
                <div className="space-y-2">
                  {sortedStrategies.map((strategy, index) => (
                    <StrategyRow
                      key={strategy.slug}
                      s={strategy}
                      rank={index + 1}
                      live={strategy.live ?? livePerfs[strategy.slug] ?? null}
                    />
                  ))}
                </div>
              )}
            </section>

            <section className={cn("space-y-3", activeTab !== "debates" && "hidden lg:block")}>
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-amber-500" />
                <h2 className="text-base font-semibold">Active Theses</h2>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {latestTheses.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-border bg-white p-8 text-center md:col-span-2">
                    <FileText className="mx-auto h-8 w-8 text-muted-foreground/40" />
                    <p className="mt-2 text-sm text-muted-foreground">No structured theses yet.</p>
                  </div>
                ) : (
                  latestTheses.map((thesis) => <ThesisCard key={thesis.id} thesis={thesis} />)
                )}
              </div>
            </section>
          </div>

          <aside className="space-y-5">
            <EvidencePanel selected={selectedItem} theses={selectedTheses} />

            <div className="rounded-lg border border-border bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center gap-2">
                <Scale className="h-4 w-4 text-emerald-500" />
                <h3 className="text-sm font-semibold">Vote on {selectedItem?.symbol ?? "AAPL"}</h3>
              </div>
              <VoteBar symbol={selectedItem?.symbol ?? "AAPL"} />
              <p className="mt-3 text-center text-[10px] text-muted-foreground">
                Votes express community stance and are not recommendations.
              </p>
            </div>

            <div id="share-thesis">
              <ThesisForm
                key={selectedItem?.symbol ?? "empty"}
                defaultSymbol={selectedItem?.symbol}
                onCreated={handleCreatedThesis}
              />
            </div>

            <div className="rounded-lg border border-border bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-blue-600" />
                <h3 className="text-sm font-semibold">Community Rules</h3>
              </div>
              <div className="space-y-3 text-xs leading-5 text-muted-foreground">
                <p className="flex gap-2"><ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-600" />Attach evidence and risk context.</p>
                <p className="flex gap-2"><Newspaper className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />Label theses as community research, not advice.</p>
                <p className="flex gap-2"><TrendingDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />No pump language, guaranteed returns, or auto-copy claims.</p>
              </div>
            </div>

            <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-[10px] leading-5 text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500/80" />
              Community activity, theses, comments, and paper strategy tracking are informational only and do not constitute investment advice or a recommendation to buy or sell.
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
