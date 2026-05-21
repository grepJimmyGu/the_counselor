"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { EntitlementErrorCode, EntitlementErrorDetail } from "@/lib/contracts";
import { subscribeUpgrade } from "@/lib/upgrade-modal-event-bus";
import { track } from "@/lib/analytics";

interface ModalCopy {
  title: string;
  body: string;
  primaryCta: string;
  secondaryCta?: string;
}

const COPY: Record<EntitlementErrorCode, ModalCopy> = {
  runs_exhausted: {
    title: "You've used all 5 custom backtests this week",
    body: "Strategist gives you unlimited custom runs and 10 years of history. Templates always remain unlimited. Try Strategist free for 14 days — no card required.",
    primaryCta: "Start free trial",
    secondaryCta: "See all plans",
  },
  universe_too_large: {
    title: "Custom strategies are capped at your tier limit",
    body: "Strategist lets you test up to 25 tickers per custom strategy. Templates have no cap regardless of tier.",
    primaryCta: "Upgrade to Strategist",
    secondaryCta: "Cancel",
  },
  history_too_long: {
    title: "Custom backtest history exceeds your tier limit",
    body: "Strategist gives you 10 years of history — enough to test through 2015-16 volatility and the 2020 crash. Templates use their pre-set windows regardless of tier.",
    primaryCta: "Upgrade to Strategist",
    secondaryCta: "Cancel",
  },
  robustness_test_locked: {
    title: "This robustness test is a Quant feature",
    body: "Quant unlocks all 5 robustness tests — parameter sensitivity, sub-period, transaction cost, benchmark comparison, peer ticker.",
    primaryCta: "Upgrade to Quant",
    secondaryCta: "Cancel",
  },
  market_pulse_ticker_out_of_scope: {
    title: "This ticker is outside Scout's research scope",
    body: "Scout covers the S&P 500. Strategist unlocks all US stocks and active market data alerts.",
    primaryCta: "Upgrade to Strategist",
    secondaryCta: "Back",
  },
  saved_strategies_quota_reached: {
    title: "You've reached your saved-strategy limit",
    body: "Strategist lets you save 25 strategies, with the option to keep them private. Quant is unlimited.",
    primaryCta: "Upgrade to Strategist",
    secondaryCta: "Manage saved strategies",
  },
  // Anonymous variants — same code base but signup CTA
  anonymous_runs_exhausted: {
    title: "Sign up to keep exploring",
    body: "You've used your free backtest. Scout (free) includes 5 custom backtests per week and unlimited templates — sign up in one click.",
    primaryCta: "Continue with Google",
    secondaryCta: "Use a template instead",
  },
};


export function UpgradeModal() {
  const [detail, setDetail] = useState<EntitlementErrorDetail | null>(null);

  useEffect(() => {
    return subscribeUpgrade((d) => setDetail(d));
  }, []);

  if (!detail) return null;

  const copy = COPY[detail.code];
  if (!copy) {
    // Unknown code — render a generic upgrade message rather than crashing.
    return (
      <Backdrop onClose={() => setDetail(null)}>
        <h2 className="text-lg font-semibold">Upgrade required</h2>
        <p className="mt-2 text-sm text-muted-foreground">{detail.detail}</p>
        <UpgradeActions detail={detail} primaryLabel={detail.cta_text} onClose={() => setDetail(null)} />
      </Backdrop>
    );
  }

  return (
    <Backdrop onClose={() => setDetail(null)}>
      <h2 className="text-lg font-semibold text-foreground">{copy.title}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{copy.body}</p>
      {(detail.current_value || detail.limit_value) && (
        <div className="mt-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs">
          <span className="text-muted-foreground">Current: </span>
          <span className="font-medium">{detail.current_value ?? "—"}</span>
          <span className="text-muted-foreground"> · Limit: </span>
          <span className="font-medium">{detail.limit_value ?? "—"}</span>
        </div>
      )}
      <UpgradeActions
        detail={detail}
        primaryLabel={copy.primaryCta}
        secondaryLabel={copy.secondaryCta}
        onClose={() => setDetail(null)}
      />
    </Backdrop>
  );
}

function Backdrop({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
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
        {children}
      </div>
    </div>
  );
}

function UpgradeActions({
  detail,
  primaryLabel,
  secondaryLabel,
  onClose,
}: {
  detail: EntitlementErrorDetail;
  primaryLabel: string;
  secondaryLabel?: string;
  onClose: () => void;
}) {
  // cta_action determines the destination. Anonymous codes → signup; authed → upgrade flow.
  const primaryHref: string = detail.upgrade_url ||
    (detail.is_anonymous
      ? `/signup?gate=${detail.code}`
      : `/pricing?gate=${detail.code}&from=${detail.current_tier ?? "scout"}`);

  return (
    <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
      {secondaryLabel && (
        <Button variant="outline" size="sm" onClick={onClose}>
          {secondaryLabel}
        </Button>
      )}
      <Button asChild size="sm">
        <Link
          href={primaryHref as Route}
          onClick={() => {
            track("paywall_cta_clicked", {
              code: detail.code,
              cta_action: detail.cta_action,
              required_tier: detail.required_tier ?? undefined,
            });
            onClose();
          }}
        >
          {primaryLabel}
        </Link>
      </Button>
    </div>
  );
}
