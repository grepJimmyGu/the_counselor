"use client";

import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import { ChevronRight, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { CommodityEvaluationDashboard } from "../_commodity-evaluation-dashboard";
import { MOCK_COMMODITY_DATA } from "@/lib/evaluation/mock-data";

const COMMODITY_META: Record<string, { label: string; emoji: string; color: string }> = {
  GOLD:   { label: "Gold",           emoji: "🟡", color: "text-yellow-600" },
  WTI:    { label: "WTI Crude Oil",  emoji: "🛢", color: "text-orange-600" },
  COPPER: { label: "Copper",         emoji: "🟤", color: "text-amber-700" },
  WHEAT:  { label: "Wheat",          emoji: "🌾", color: "text-green-700" },
};

const SYMBOLS = ["GOLD", "WTI", "COPPER", "WHEAT"] as const;

export default function CommodityPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const router = useRouter();
  const sym = symbol?.toUpperCase() ?? "GOLD";
  const data = MOCK_COMMODITY_DATA[sym];

  if (!data) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-[1200px] px-4 py-12 text-center">
          <p className="text-base font-medium">Commodity not found: {sym}</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Available: {SYMBOLS.join(", ")}
          </p>
          <Link href={"/commodities/GOLD" as Route} className="mt-4 inline-block text-sm text-primary hover:underline">
            View Gold →
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-[1200px] space-y-6 px-4 py-6 md:px-6 lg:px-8">

        {/* Breadcrumb */}
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Link href={"/commodities/GOLD" as Route} className="hover:text-foreground transition-colors">
            Commodities
          </Link>
          <ChevronRight className="h-3 w-3" />
          <span className="font-mono font-medium text-foreground">{sym}</span>
        </div>

        {/* Commodity selector tabs */}
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {SYMBOLS.map((s) => {
            const meta = COMMODITY_META[s];
            const isActive = s === sym;
            return (
              <button
                key={s}
                onClick={() => router.push(`/commodities/${s}` as Route)}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg border px-3.5 py-2 text-xs font-medium whitespace-nowrap transition-all",
                  isActive
                    ? "border-primary/30 bg-primary/5 text-primary shadow-sm"
                    : "border-border bg-white text-muted-foreground hover:border-border/80 hover:text-foreground"
                )}
              >
                {meta.label}
                {isActive && <Badge variant="outline" className="ml-1 text-[9px] px-1.5 py-0">Mock data</Badge>}
              </button>
            );
          })}
        </div>

        {/* Dashboard */}
        <CommodityEvaluationDashboard m={data} />

        {/* Data source disclaimer */}
        <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
          <span className="font-medium">Note:</span> Commodity data displayed is mock/estimated for framework demonstration.
          Physical market data (inventories, CFTC positioning, futures curve) will be integrated via EIA, CFTC public feeds,
          and FMP futures endpoints in a future update.
        </div>

      </div>
    </main>
  );
}
