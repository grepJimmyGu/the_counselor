"use client";

export const dynamic = "force-dynamic";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { PricingTierCard } from "@/components/PricingTierCard";
import { getPricing, startTrial, createCheckoutSession } from "@/lib/api";
import type { PricingPage } from "@/lib/contracts";
import type { Route } from "next";

// Feature lists per tier
const FEATURES: Record<string, string[]> = {
  scout: [
    "5 backtests per month",
    "Up to 5-symbol universes",
    "5 years of history",
    "Equities only",
    "Market Pulse (top 250 stocks)",
    "3 saved strategies",
    "Community access",
  ],
  strategist: [
    "Unlimited backtests",
    "Up to 25-symbol universes",
    "10 years of history",
    "Equities + Commodities",
    "Full US stock universe",
    "25 saved strategies",
    "Parameter sensitivity & benchmark tests",
    "14-day free trial — no card required",
  ],
  quant: [
    "Everything in Strategist",
    "Up to 100-symbol universes",
    "20 years of history",
    "Equities, Commodities, A-Shares",
    "Full US stock universe + alerts",
    "Unlimited saved strategies",
    "All robustness tests",
    "REST API access",
    "Verified community badge",
  ],
  creator: [
    "Everything in Quant",
    "Revenue share on strategy views",
    "Creator badge",
    "Early access to new features",
    "Dedicated support",
  ],
};

export default function PricingPage() {
  const { data: session } = useSession();
  const router = useRouter();
  const [cycle, setCycle] = useState<"monthly" | "annual">("annual");
  const [pricing, setPricing] = useState<PricingPage | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getPricing().then(setPricing).catch(() => {});
    // Restore cycle preference from localStorage
    const saved = typeof window !== "undefined" ? localStorage.getItem("pricingCycle") : null;
    if (saved === "monthly" || saved === "annual") setCycle(saved);
  }, []);

  function toggleCycle(c: "monthly" | "annual") {
    setCycle(c);
    localStorage.setItem("pricingCycle", c);
  }

  const backendToken = (session as any)?.backendToken as string | undefined;

  async function handleTrialStart(tier: "strategist" | "quant") {
    if (!session) { router.push("/signup?intent=trial&tier=" + tier + "&cycle=" + cycle as Route); return; }
    if (!backendToken) return;
    setLoading(true);
    try {
      await startTrial(tier, backendToken);
      router.push("/workspace?welcome=1" as Route);
    } catch {
      router.push("/signup?intent=trial&tier=" + tier + "&cycle=" + cycle as Route);
    } finally {
      setLoading(false);
    }
  }

  async function handleUpgrade(tier: "strategist" | "quant") {
    if (!session) { router.push("/signup?intent=trial&tier=" + tier + "&cycle=" + cycle as Route); return; }
    if (!backendToken) return;
    setLoading(true);
    try {
      const returnUrl = `${window.location.origin}/account`;
      const { url } = await createCheckoutSession({ tier, billing_cycle: cycle, return_url: returnUrl }, backendToken);
      window.location.href = url;
    } catch {
      setLoading(false);
    }
  }

  function priceFor(tier: "strategist" | "quant", cyc: "monthly" | "annual"): number | null {
    if (!pricing) return null;
    const opt = pricing.options.find(o => o.tier === tier && o.billing_cycle === cyc);
    if (!opt) return null;
    // For annual, display_price shows effective monthly: amount_cents / 12
    return cyc === "annual" ? Math.round(opt.amount_cents / 12) * 100 : opt.amount_cents;
  }

  return (
    <main className="min-h-screen bg-background px-4 py-16">
      <div className="mx-auto max-w-6xl space-y-10">

        {/* Header */}
        <div className="text-center space-y-3">
          <h1 className="font-heading text-4xl font-bold tracking-tight">
            Simple, transparent pricing
          </h1>
          <p className="text-lg text-muted-foreground">
            Start free. Upgrade when you&apos;re ready. No card required for the trial.
          </p>
        </div>

        {/* Billing cycle toggle */}
        <div className="flex justify-center">
          <div className="flex items-center gap-1 rounded-xl border border-border bg-muted/30 p-1">
            {(["monthly", "annual"] as const).map(c => (
              <button
                key={c}
                type="button"
                onClick={() => toggleCycle(c)}
                className={`cursor-pointer rounded-lg px-5 py-2 text-sm font-medium transition-all ${
                  cycle === c
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {c === "monthly" ? "Monthly" : "Annual"}
                {c === "annual" && (
                  <span className="ml-1.5 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                    Save 20%
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Tier grid */}
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {/* Scout */}
          <PricingTierCard
            tier="scout"
            name="Scout"
            tagline="For curious investors"
            monthlyPrice={null}
            annualPrice={null}
            cycle={cycle}
            features={FEATURES.scout}
            ctaLabel="Get started free"
            ctaHref="/signup"
          />

          {/* Strategist */}
          <PricingTierCard
            tier="strategist"
            name="Strategist"
            tagline="For systematic researchers"
            monthlyPrice={2400}
            annualPrice={priceFor("strategist", "annual")}
            cycle={cycle}
            features={FEATURES.strategist}
            ctaLabel={loading ? "Loading…" : "Start free trial"}
            onCta={() => handleTrialStart("strategist")}
            highlighted
            badge="Most popular"
            ctaDisabled={loading}
          />

          {/* Quant */}
          <PricingTierCard
            tier="quant"
            name="Quant"
            tagline="For professional researchers"
            monthlyPrice={7900}
            annualPrice={priceFor("quant", "annual")}
            cycle={cycle}
            features={FEATURES.quant}
            ctaLabel={loading ? "Loading…" : "Start free trial"}
            onCta={() => handleTrialStart("quant")}
            ctaDisabled={loading}
          />

          {/* Creator */}
          <PricingTierCard
            tier="quant"
            name="Creator"
            tagline="For strategy publishers"
            monthlyPrice={null}
            annualPrice={null}
            cycle={cycle}
            features={FEATURES.creator}
            ctaLabel="Apply for Creator"
            ctaHref="/community"
            badge="Coming soon"
          />
        </div>

        {/* Footer note */}
        <p className="text-center text-sm text-muted-foreground">
          All prices in USD. Cancel any time. Trial ends automatically — no charge unless you add a card.
        </p>
      </div>
    </main>
  );
}
