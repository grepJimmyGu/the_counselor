/**
 * PRD-16a-4 — Standalone signal library page.
 *
 * Lets users browse the catalog without committing to a strategy.
 * Useful for marketing / SEO and for users learning what's available
 * before they open the composer.
 *
 * The composer (PRD-16b) will wrap `<SignalCatalogBrowser>` with its
 * own onPick callback; this page renders it standalone (clicks no-op).
 */
"use client";

export const dynamic = "force-dynamic";

import { SignalCatalogBrowser } from "@/components/signal-library/signal-catalog-browser";
import { NotInvestmentAdviceFooter } from "@/components/notifications/not-investment-advice-footer";

export default function SignalLibraryPage() {
  return (
    <main className="mx-auto max-w-6xl px-4 py-10 md:py-14">
      <header className="mb-8">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Signal Library
        </p>
        <h1 className="mt-1 font-heading text-2xl font-bold">
          The building blocks of every Livermore strategy
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Browse 55 signal primitives across eight categories. Each card
          explains what the signal measures in plain English — descriptions
          are deliberately not prescriptive. The Composer (coming soon)
          lets you combine these into custom strategies.
        </p>
      </header>

      <SignalCatalogBrowser />

      <div className="mt-10">
        <NotInvestmentAdviceFooter />
      </div>
    </main>
  );
}
