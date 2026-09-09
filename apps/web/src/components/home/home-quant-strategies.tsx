"use client";

/**
 * Home block 3 — **Quant Rules**.
 *
 * Two rows, and the split is by who you are, not by what the feature is:
 *
 *   Start a strategy   — guided (entry) | composer (expert)
 *   Start from your    — connect a brokerage, and the product reads the
 *   own book             record you already have
 *
 * WHY THE EXAMPLE TEMPLATES ARE GONE. This block used to show "Try a Template"
 * beside three named templates (Trend Following, Cross-Sectional, ETF
 * Rotation) at four columns. Three examples of a thing are not a third entry
 * point — they competed for the eye with the two paths that actually differ,
 * and a reader who clicked one still landed in the same wizard. The templates
 * are unchanged and still back the wizard; they simply stop advertising.
 *
 * TIER BADGES ARE SIGNPOSTS, NOT GATES. Nothing stops an expert taking the
 * guided path or a beginner opening the composer, so the badges read "Entry
 * level" and "Expert" rather than "only" — a restriction the product does not
 * enforce should not be claimed on the surface.
 *
 * EVERY NUMBER HERE IS CHECKED. Five questions is `WIZARD_QUESTIONS.length`;
 * twelve is `researchTemplates` minus the unavailable ones; 110 is the live
 * primitive catalog. They are asserted in the tests against their real
 * sources, so a number cannot rot into a claim nobody re-checked.
 *
 * NO PERFORMANCE NUMBERS. Templates carry a `perfContext` field that reads
 * like backtested returns but is hand-written prose, and there is no store of
 * real per-template performance. Showing a return here would be inventing one.
 *
 * THE OVERLAY OVERVIEW MOVED. It described rules for a portfolio you have not
 * uploaded yet; it now lives on the upload step, beside the holdings it
 * applies to. Same for the Mirror.
 */

import { Link2, ShieldCheck, SlidersHorizontal, Sparkles } from "lucide-react";
import { startFlow } from "@/lib/flows/runtime";
import { INITIAL_CUSTOM_BUILD_CONTEXT } from "@/lib/flows/custom-build-mode-context";
import { researchTemplates } from "@/lib/contracts";
import {
  WIZARD_QUESTIONS,
  WIZARD_STRATEGIES,
} from "@/components/strategy-builder/wizard/strategy-wizard-data";

/** Derived, not typed in — a hand-written number is a claim that rots the
 *  first time the wizard or the template list changes underneath it. */
export const QUESTION_COUNT = WIZARD_QUESTIONS.length;

/** ⚠ THE INTERSECTION, and it is smaller than either side.
 *
 *  This said `researchTemplates.filter(t => t.availability !== "unavailable")`
 *  and rendered 12. That counted the wrong set twice over:
 *
 *    - The wizard's gate is `availability === "ready"`, not "not unavailable".
 *      A `proxy` template is LOCKED in the picker (strategy-wizard.tsx:139,
 *      :324), so it is not something the wizard can fit anyone to. 11 ready.
 *    - Five templates the wizard maps to are not ready, and three ready ones
 *      have no wizard mapping at all — reachable and runnable are different
 *      sets, and the card claims the overlap.
 *
 *  Ready ∧ reachable is 9. The number a card promises has to be the number of
 *  outcomes actually reachable from the button under it. */
const READY_TEMPLATE_IDS = new Set(
  researchTemplates.filter((t) => t.availability === "ready").map((t) => t.id),
);
export const TEMPLATE_COUNT = new Set(
  WIZARD_STRATEGIES.map((s) => s.templateId).filter(
    (id): id is string => Boolean(id) && READY_TEMPLATE_IDS.has(id as string),
  ),
).size;

/** The one number that CANNOT be derived here: the primitive catalog is
 *  served by `GET /api/signal-primitives`, not bundled. 110 as of 2026-09-09
 *  (8 categories, trend 30 / mean_reversion 23 / momentum 18 / …). If the
 *  catalog grows, this is the line to update — re-check with:
 *    curl -s <api>/api/signal-primitives | python3 -c "import json,sys;print(len(json.load(sys.stdin)))"
 */
export const PRIMITIVE_COUNT = 110;

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 mt-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground first:mt-0">
      {children}
    </div>
  );
}

function TierBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10.5px] font-medium uppercase tracking-wide text-muted-foreground">
      {children}
    </span>
  );
}

/** The two row-1 entry points. One component so they cannot drift in style —
 *  they are a pair, and a pair that looks mismatched reads as a hierarchy. */
function EntryCard({
  icon: Icon,
  tier,
  title,
  children,
  onClick,
  testid,
}: {
  icon: typeof Sparkles;
  tier: string;
  title: string;
  children: React.ReactNode;
  onClick: () => void;
  testid: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className="flex cursor-pointer flex-col items-start rounded-lg border border-border p-3.5 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
    >
      <div className="flex w-full items-center justify-between gap-2">
        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
        <TierBadge>{tier}</TierBadge>
      </div>
      <span className="mt-2 text-sm font-semibold">{title}</span>
      <span className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">
        {children}
      </span>
    </button>
  );
}

export function HomeQuantStrategies() {
  // These launch flows directly rather than arriving as props — a flow is
  // self-contained (`startFlow` navigates), so routing them through the page
  // would add a prop that only forwards.
  const onGuided = () =>
    startFlow("one_asset_mode", { initialContext: { fromTrigger: "home/pick_asset" } });
  const onBuild = () =>
    startFlow("custom_build_mode", {
      initialContext: { ...INITIAL_CUSTOM_BUILD_CONTEXT, fromTrigger: "home/custom_build" },
    });
  const onPortfolio = () =>
    startFlow("portfolio_mode", { initialContext: { fromTrigger: "home/upload_portfolio" } });

  return (
    <section
      className="rounded-xl border border-border bg-white p-4"
      data-testid="home-quant-strategies"
    >
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="font-heading text-base font-semibold">Quant Rules</h2>
        <span className="text-xs text-muted-foreground">Backtest before you commit</span>
      </div>

      {/* ── Row 1 — the two ways in ───────────────────────────────────────── */}
      <GroupLabel>Start a strategy</GroupLabel>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        <EntryCard
          icon={Sparkles}
          tier="Entry level"
          title="Start with a Proven Strategy"
          onClick={onGuided}
          testid="quant-guided-start"
        >
          {QUESTION_COUNT} plain questions, and we fit one of {TEMPLATE_COUNT}{" "}
          published strategies to your stock — ruling out the ones your answers
          disqualify.
        </EntryCard>

        <EntryCard
          icon={SlidersHorizontal}
          tier="Expert"
          title="Write Your Own Rules"
          onClick={onBuild}
          testid="quant-build-from-scratch"
        >
          Compose from {PRIMITIVE_COUNT} primitives — your own entry rules and
          exit ladder, over the S&P 500, the Russell 3000, a sector, or your
          own list.
        </EntryCard>
      </div>

      {/* ── Row 2 — the book they already have ────────────────────────────── */}
      <GroupLabel>Or start from your own book</GroupLabel>
      <button
        type="button"
        onClick={onPortfolio}
        data-testid="quant-connect-brokerage"
        className="flex w-full cursor-pointer flex-col items-start rounded-lg border border-primary/30 bg-primary/[0.03] p-3.5 text-left transition-colors hover:border-primary/50 hover:bg-primary/[0.06]"
      >
        <span className="flex items-center gap-1.5 text-sm font-semibold">
          <Link2 className="h-4 w-4 text-primary" aria-hidden="true" />
          Connect your brokerage
        </span>
        <span className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">
          We read the record you already have: what your trading habits cost
          you, and which rules are worth putting over the positions you hold.
          Or add holdings by hand on the next screen.
        </span>
        {/* The honest version of the reassurance. "Read-only" is no longer
            true — order placement exists — but the guarantee that replaced it
            is stronger, so say that one. See test_snaptrade_readonly_guard. */}
        <span className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          No order is ever placed without you approving a priced preview.
        </span>
      </button>
    </section>
  );
}
