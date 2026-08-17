"use client";

/**
 * Home — **Your Livermore**.
 *
 * Restored on 2026-08-14. This was Focus 3 of `home-focus-sections.tsx`, which
 * was deleted wholesale in #323 to remove Focus 1 (Discover stocks) and Focus 2
 * (Build a strategy) — both by then duplicated by the 2x2 above. Focus 3 was
 * not duplicated and was not asked to go; it went with the file.
 *
 * The piece that actually mattered is `<SavedStrategiesTile>`. After #323 it
 * rendered NOWHERE: a signed-in user's saved strategies lost their only
 * home-page surface, reachable afterwards solely by navigating to
 * `/account/strategies` and knowing it was there.
 *
 * The two cards beneath it (Community feed, Account & alerts) both duplicate
 * top-nav destinations. They are kept because they were here before and their
 * removal was never requested — not because the duplication is defensible.
 */

import * as React from "react";
import Link from "next/link";
import type { Route } from "next";
import { ArrowRight, Settings, Users } from "lucide-react";

import { SavedStrategiesTile } from "@/components/home/saved-strategies-tile";

function FocusCard({
  icon: Icon,
  title,
  desc,
  href,
  testId,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  desc: string;
  href: Route;
  testId?: string;
}) {
  return (
    <Link
      href={href}
      data-testid={testId}
      className="group flex h-full cursor-pointer flex-col rounded-2xl border border-border/60 bg-white p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-primary/20 bg-primary/5">
        <Icon className="h-5 w-5 text-primary" />
      </span>
      <h3 className="font-heading text-base font-semibold">{title}</h3>
      <p className="mt-1 flex-1 text-sm leading-relaxed text-muted-foreground">{desc}</p>
      <span className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-primary">
        Open
        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

export function HomeYourLivermore() {
  return (
    <section data-testid="focus-continuity">
      <div className="mb-4">
        <h2 className="font-heading text-xl font-bold">Your Livermore</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Manage your strategies, follow the community.
        </p>
      </div>

      {/* Handles anonymous / signed-in / has-strategies itself. */}
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
  );
}
