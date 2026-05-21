"use client";

import { useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Loader2, Share2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { publishStrategy } from "@/lib/api";
import type { BacktestResult, StrategyJson } from "@/lib/contracts";

interface Props {
  open: boolean;
  onClose: () => void;
  strategy: StrategyJson;
  result: BacktestResult;
  backendToken?: string;
}

/**
 * Stage 4a — publish-to-community modal.
 *
 * Pre-fills title from strategy.strategy_name. User can edit + add optional
 * description. On publish, calls POST /api/community/strategies and shows
 * the resulting /s/[slug] URL with a "Copy link" + "View" CTA.
 *
 * Scout-tier saves auto-publish via the saved-strategy service, so this
 * modal is the explicit Strategist+ publish path.
 */
export function PublishModal({ open, onClose, strategy, result, backendToken }: Props) {
  const [title, setTitle] = useState(strategy.strategy_name ?? "My strategy");
  const [description, setDescription] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publishedSlug, setPublishedSlug] = useState<string | null>(null);

  if (!open) return null;

  async function handlePublish() {
    if (!backendToken) {
      setError("Sign in required to publish.");
      return;
    }
    setError(null);
    setPublishing(true);
    try {
      const detail = await publishStrategy(
        {
          title: title.trim(),
          description: description.trim() || undefined,
          strategy_json: strategy as unknown as Record<string, unknown>,
          backtest_record_id: result.backtest_id,
          equity_curve_snapshot: result.equity_curve.map((e, i) => ({
            date: e.date,
            equity: e.value,
            benchmark: result.benchmark_curve[i]?.value ?? null,
          })),
        },
        backendToken,
      );
      setPublishedSlug(detail.slug);
    } catch (e) {
      setError((e as Error).message || "Failed to publish.");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        {publishedSlug ? (
          <PublishedSuccess slug={publishedSlug} onClose={onClose} />
        ) : (
          <>
            <h2 className="text-lg font-semibold text-foreground">
              Publish to community
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              A frozen snapshot of this strategy + backtest result will be public.
              Edits to your saved version don&apos;t leak.
            </p>

            <div className="mt-5 space-y-3">
              <div className="space-y-1">
                <label htmlFor="pub-title" className="text-sm font-medium">
                  Title
                </label>
                <Input
                  id="pub-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={120}
                  placeholder="Mag-7 momentum rotation"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="pub-description" className="text-sm font-medium">
                  Description{" "}
                  <span className="text-xs font-normal text-muted-foreground">
                    (optional)
                  </span>
                </label>
                <textarea
                  id="pub-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={2000}
                  rows={3}
                  placeholder="What does this strategy capture?"
                  className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>

              {error && (
                <p className="text-xs text-destructive">{error}</p>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" size="sm" onClick={onClose} disabled={publishing}>
                  Cancel
                </Button>
                <Button size="sm" onClick={handlePublish} disabled={publishing || title.trim().length < 3}>
                  {publishing ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <>
                      <Share2 className="mr-1.5 h-3.5 w-3.5" />
                      Publish
                    </>
                  )}
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function PublishedSuccess({ slug, onClose }: { slug: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const url = typeof window !== "undefined" ? `${window.location.origin}/s/${slug}` : `/s/${slug}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      window.prompt("Copy this link:", url);
    }
  }

  return (
    <>
      <h2 className="text-lg font-semibold text-foreground">Published!</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Your strategy is live at:
      </p>
      <div className="mt-3 rounded-md border border-border bg-muted/30 px-3 py-2 font-mono text-xs break-all">
        {url}
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? "Copied!" : "Copy link"}
        </Button>
        <Button asChild size="sm">
          <Link href={`/s/${slug}` as Route} onClick={onClose}>
            View
          </Link>
        </Button>
      </div>
    </>
  );
}
