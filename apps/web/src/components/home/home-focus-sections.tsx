"use client";

/**
 * <HomeFocusSections> — PRD-24a §3.5–3.7 the 3-focus Home reorganization.
 *
 * Replaces the flat <EntryModePicker> + marketing pillars with three
 * intent-grouped sections:
 *   1. Discover Stocks  — the Themes Firing Today cards + "Screen the market"
 *   2. Build a Strategy — Try a template · Upload portfolio · Build from scratch
 *   3. Your Livermore   — Your Strategies (auth-aware) · Community · Account
 *
 * Reuses: <HomeThemesFiringToday> (Focus 1), the flow launchers (Focus 2),
 * and <SavedStrategiesTile> which already renders the anonymous/authed/
 * has-strategies states (Focus 3, §3.7).
 */

import * as React from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, Filter, Library, Settings, Upload, Users, Wand2 } from "lucide-react";
import { startFlow } from "@/lib/flows/runtime";
import { INITIAL_CUSTOM_BUILD_CONTEXT } from "@/lib/flows/custom-build-mode-context";
// Side-effect imports — register the flows so startFlow can find them.
import "@/lib/flows/portfolio-mode";
import "@/lib/flows/custom-build-mode";
import { HomeThemesFiringToday } from "@/components/home/home-themes-firing-today";
import { SavedStrategiesTile } from "@/components/home/saved-strategies-tile";

function FocusHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="mb-4">
      <h2 className="font-heading text-xl font-bold">{title}</h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
    </div>
  );
}

interface FocusCardProps {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  desc: string;
  meta?: string;
  href?: Route;
  onClick?: () => void;
  testId?: string;
}

function FocusCard({ icon: Icon, title, desc, meta, href, onClick, testId }: FocusCardProps) {
  const cls =
    "group flex h-full flex-col rounded-2xl border border-border/60 bg-white p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  const inner = (
    <>
      <span className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-primary/20 bg-primary/5">
        <Icon className="h-5 w-5 text-primary" />
      </span>
      <h3 className="font-heading text-base font-semibold">{title}</h3>
      <p className="mt-1 flex-1 text-sm leading-relaxed text-muted-foreground">{desc}</p>
      {meta ? (
        <span className="mt-3 text-xs font-medium text-muted-foreground">{meta}</span>
      ) : null}
      <span className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-primary">
        Open
        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </>
  );
  return href ? (
    <Link href={href} data-testid={testId} className={cls}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} data-testid={testId} className={cls}>
      {inner}
    </button>
  );
}

export function HomeFocusSections() {
  const launchScreenMarket = () =>
    startFlow("custom_build_mode", {
      initialContext: {
        ...INITIAL_CUSTOM_BUILD_CONTEXT,
        universe_id: "sp500",
        fromTrigger: "home/screen_market",
      },
    });
  const launchPortfolio = () =>
    startFlow("portfolio_mode", {
      initialContext: { fromTrigger: "home/upload_portfolio" },
    });
  const launchCustomBuild = () =>
    startFlow("custom_build_mode", {
      initialContext: {
        ...INITIAL_CUSTOM_BUILD_CONTEXT,
        fromTrigger: "home/custom_build",
      },
    });

  return (
    <div className="space-y-14" data-testid="home-focus-sections">
      {/* ── Focus 1 — Discover Stocks ──────────────────────────────────── */}
      <section data-testid="focus-discover">
        <FocusHeader title="Discover stocks" subtitle="Find what's worth your attention today." />
        <HomeThemesFiringToday />
        <div className="mt-4">
          <button
            type="button"
            onClick={launchScreenMarket}
            data-testid="focus-screen-market"
            className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
          >
            <Filter className="h-4 w-4" /> Want more setups? Screen the market
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </section>

      {/* ── Focus 2 — Build a Strategy ─────────────────────────────────── */}
      <section data-testid="focus-build">
        <FocusHeader
          title="Build a strategy"
          subtitle="Compose, test, and run a quantitative strategy."
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <FocusCard
            icon={Library}
            title="Try a template"
            desc="Start from a ready-made quant strategy and backtest it on any asset."
            meta="19 quant templates"
            href={"/templates" as Route}
            testId="focus-try-template"
          />
          <FocusCard
            icon={Upload}
            title="Upload portfolio"
            desc="Bring your holdings — we diagnose style + factor exposure and recommend an overlay."
            meta="Diagnose + overlay"
            onClick={launchPortfolio}
            testId="focus-upload-portfolio"
          />
          <FocusCard
            icon={Wand2}
            title="Build from scratch"
            desc="Compose signal primitives with AND / OR rules into a custom reading."
            meta="110 signal primitives"
            onClick={launchCustomBuild}
            testId="focus-build-scratch"
          />
        </div>
      </section>

      {/* ── Focus 3 — Your Livermore ───────────────────────────────────── */}
      <section data-testid="focus-continuity">
        <FocusHeader
          title="Your Livermore"
          subtitle="Manage your strategies, follow the community."
        />
        {/* Your Strategies — the tile already handles anonymous / authed /
            has-strategies (§3.7). */}
        <SavedStrategiesTile />
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <FocusCard
            icon={Users}
            title="Community feed"
            desc="Discover strategies and theses from other researchers; fork what fits."
            href={"/community" as Route}
            testId="focus-community"
          />
          <FocusCard
            icon={Settings}
            title="Account & alerts"
            desc="Your plan, tier, and notification preferences."
            href={"/account" as Route}
            testId="focus-account"
          />
        </div>
      </section>
    </div>
  );
}
