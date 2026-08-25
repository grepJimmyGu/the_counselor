"use client";

/**
 * <FlowTrack> — PRD-28 §4. The shared terminal step.
 *
 * ONE step, used by BOTH `custom_build_mode` and `one_asset_mode`. Not two
 * implementations: a second copy would drift exactly the way the exit-ladder
 * logic drifted before #325, and that divergence cost a week to find.
 *
 * WHAT IT IS FOR. Everything up to `save` produces a backtest — a claim about
 * the past. This step is where a user decides whether the strategy becomes
 * something that watches the market for them. Before it existed, saving was
 * the end of the road: the strategy sat in a list, `declare_position` refused
 * it for want of an exit ladder, and the daily monitor skipped it.
 *
 * THREE DOORS, and the third is not a booby prize:
 *
 *   - Watch it            — alerts on, nothing tracked
 *   - I already hold this — declare the real position, tracked against exits
 *   - Just save it        — today's behaviour, no nag
 *
 * Most users take the third. A backtest is a legitimate end in itself, and a
 * step that punishes people for stopping there would make the other two feel
 * like a trap rather than an offer.
 *
 * THE SIGN-OFF (§2.2). Attaching an exit ladder MUTATES a strategy the user
 * already saved, so it is confirmed explicitly and the screen names what is
 * changing. This is not merely a convention here — the server has no path
 * that applies a default ladder, so what lands is always what this component
 * rendered. See `test_exit_ladder_signoff_guard.py`.
 *
 * NOT AN ORDER STEP. At save time the strategy holds no position and may name
 * no symbol, so `<PlaceOrder>` would render nothing. Offering to trade here
 * would be an empty gesture. Orders happen where there is something to sell:
 * on a fired exit, via `<ExitTicket>`.
 */

import * as React from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";

import { attachExitLadder, declarePosition, subscribeSignalAlert } from "@/lib/api";
import type { ExitTier, StrategyJson } from "@/lib/contracts";
import { ExitLadderEditor, validateExitLadder, SPACEX_DEFAULT_LADDER } from "./exit-ladder-editor";
import { fetchNatrPct, ladderFromNatr, FALLBACK_LADDER_DEFAULTS } from "../promote-to-strategy";
import type { FlowContextBase, FlowStepProps } from "../types";
import { useFlowCopy } from "../copy";
import { useFlowState } from "../runtime";

export interface FlowTrackContext extends FlowContextBase {
  strategyJson?: StrategyJson;
  savedSlug?: string;
  /** SavedStrategy row id — null when the link failed at save time. */
  savedStrategyId?: string | null;
  /** The two modes name this differently, and each field is typed EXACTLY as
   *  its own mode declares it — `custom_build_mode` has `symbol: string |
   *  null` (null before the picker runs), `one_asset_mode` has `ticker?:
   *  string`.
   *
   *  Not cosmetic. `FlowStepProps` carries `updateContext`, which puts the
   *  context type in contravariant position, so widening either field beyond
   *  its mode's own declaration makes this component unassignable to that
   *  mode's step. Matching both shapes exactly is what lets ONE component
   *  serve both flows without casts at the call sites. */
  symbol?: string | null;
  ticker?: string;
}

type Door = "watch" | "hold" | "skip";
type Stage = "doors" | "ladder" | "declare" | "done";

/** Where the seeded ladder came from. The user is told which — "scaled to
 *  NVDA's volatility" and "generic starting points" are different claims and
 *  only one of them is true at a time. */
type LadderSource = "calculated" | "generic";

export function existingLadder(sj: StrategyJson | undefined): ExitTier[] | null {
  const tiers = sj?.risk_management?.exit_ladder;
  return tiers && tiers.length > 0 ? tiers : null;
}

/** The symbol the ladder is scaled to. The two modes name it differently and
 *  either may be absent on a multi-symbol strategy, in which case there is no
 *  single volatility to scale to and we fall back to generic tiers. */
export function ladderSymbol(ctx: FlowTrackContext): string | null {
  const universe = ctx.strategyJson?.universe;
  const single = universe && universe.length === 1 ? universe[0] : null;
  return (ctx.symbol || ctx.ticker || single || null)?.toUpperCase() ?? null;
}

export function FlowTrack({
  context,
  advance,
}: FlowStepProps<FlowTrackContext>) {
  const { flow } = useFlowState();
  const modeId = flow.id;

  // Resolved up-front and unconditionally. `useFlowCopy` is a plain lookup
  // despite the name, but calling it inside a branch would still trip
  // rules-of-hooks — and this component renders four different stages.
  const copy = {
    title: useFlowCopy(modeId, "track_title"),
    doorWatch: useFlowCopy(modeId, "track_door_watch"),
    doorWatchSub: useFlowCopy(modeId, "track_door_watch_sub"),
    doorHold: useFlowCopy(modeId, "track_door_hold"),
    doorHoldSub: useFlowCopy(modeId, "track_door_hold_sub"),
    doorSkip: useFlowCopy(modeId, "track_door_skip"),
    doorSkipSub: useFlowCopy(modeId, "track_door_skip_sub"),
    ladderTitle: useFlowCopy(modeId, "track_ladder_title"),
    ladderConfirm: useFlowCopy(modeId, "track_ladder_confirm"),
    ladderDecline: useFlowCopy(modeId, "track_ladder_decline"),
    declareTitle: useFlowCopy(modeId, "track_declare_title"),
    declareConfirm: useFlowCopy(modeId, "track_declare_confirm"),
    done: useFlowCopy(modeId, "track_done"),
  };

  const { data: session } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const strategyId = context.savedStrategyId ?? null;
  const title = context.strategyJson?.strategy_name ?? "this strategy";
  const symbol = ladderSymbol(context);
  const saved = existingLadder(context.strategyJson);

  const [stage, setStage] = React.useState<Stage>("doors");
  const [door, setDoor] = React.useState<Door | null>(null);
  const [tiers, setTiers] = React.useState<ExitTier[]>(saved ?? []);
  const [source, setSource] = React.useState<LadderSource>("generic");
  const [natr, setNatr] = React.useState<number | null>(null);
  const [seeding, setSeeding] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [ladderSaved, setLadderSaved] = React.useState<boolean>(!!saved);
  const [watching, setWatching] = React.useState(false);

  // Declare-position form.
  const [shares, setShares] = React.useState("");
  const [cost, setCost] = React.useState("");

  /** Seed the editor from recent volatility. Only ever runs after the user
   *  picked a door — a user heading for "Just save it" should not trigger a
   *  network call to price an exit rule they never asked about. */
  const seed = React.useCallback(async () => {
    if (saved) return; // already has one; nothing to seed
    setSeeding(true);
    try {
      const pct = symbol
        ? await fetchNatrPct(symbol, FALLBACK_LADDER_DEFAULTS.atr_period)
        : null;
      const calculated = pct === null ? null : ladderFromNatr(pct);
      if (calculated) {
        setTiers(calculated);
        setNatr(pct);
        setSource("calculated");
      } else {
        // Never claim a volatility scaling we could not compute. Generic
        // tiers are a starting point the user edits and signs off on — the
        // copy says so.
        setTiers(SPACEX_DEFAULT_LADDER);
        setSource("generic");
      }
    } finally {
      setSeeding(false);
    }
  }, [saved, symbol]);

  const pickDoor = async (choice: Door) => {
    setDoor(choice);
    setError(null);

    if (choice === "skip") {
      setStage("done");
      return;
    }

    if (choice === "watch" && strategyId && backendToken) {
      // Fire-and-report: subscribing is reversible and low-stakes, so it is
      // not one of the two sign-off points — pressing "Watch it" IS the
      // consent. A failure here must not block the ladder step.
      try {
        await subscribeSignalAlert(strategyId, backendToken);
        setWatching(true);
      } catch {
        /* signal alerts may be switched off backend-side; not fatal */
      }
    }

    if (saved) {
      // Already has an exit rule — nothing to sign off on.
      setStage(choice === "hold" ? "declare" : "done");
      return;
    }
    setStage("ladder");
    void seed();
  };

  const confirmLadder = async () => {
    if (!strategyId || !backendToken) return;
    const check = validateExitLadder(tiers);
    if (!check.ok) {
      setError(check.reasons.join(" "));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await attachExitLadder(strategyId, tiers, backendToken);
      setLadderSaved(true);
      setStage(door === "hold" ? "declare" : "done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the exits.");
    } finally {
      setBusy(false);
    }
  };

  const submitPosition = async () => {
    if (!strategyId || !backendToken) return;
    const s = Number(shares);
    const p = Number(cost);
    if (!Number.isFinite(s) || s <= 0) {
      setError("How many shares do you hold?");
      return;
    }
    if (!Number.isFinite(p) || p <= 0) {
      setError("What price did you pay? Exits are measured from it.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await declarePosition(
        strategyId,
        { symbol: symbol ?? "", shares: s, entry_price: p },
        backendToken,
      );
      setStage("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't track that position.");
    } finally {
      setBusy(false);
    }
  };

  // ── the strategy saved but never got a row ────────────────────────────
  //
  // `saved_strategy_id` is null when the link failed — best-effort by
  // design, because losing the backtest would be worse. Offer the honest
  // confirmation rather than three doors that would all 404.
  if (!strategyId) {
    return (
      <section className="space-y-4" data-testid="flow-track-unlinked">
        <h1 className="font-heading text-2xl font-bold">Saved</h1>
        <p className="text-sm text-muted-foreground">
          &ldquo;{title}&rdquo; is saved. Setting up tracking isn&rsquo;t
          available for it right now — you can still open it any time.
        </p>
        <DoneLinks slug={context.savedSlug} advance={advance} label={copy.done} />
      </section>
    );
  }

  // ── done ──────────────────────────────────────────────────────────────
  if (stage === "done") {
    return (
      <section className="space-y-4" data-testid="flow-track-done">
        <h1 className="font-heading text-2xl font-bold">
          {door === "skip" ? "Saved" : "You're set"}
        </h1>
        <ul className="space-y-1.5 text-sm text-foreground">
          <li>
            &ldquo;{title}&rdquo; is in{" "}
            <Link
              href={"/account/strategies" as Route}
              className="font-medium text-primary underline-offset-2 hover:underline"
            >
              My strategies
            </Link>
            .
          </li>
          {watching && <li data-testid="track-watching">We&rsquo;ll email you when it triggers.</li>}
          {ladderSaved && (
            <li data-testid="track-ladder-on">
              Exits are attached — {describeLadder(tiers)}.
            </li>
          )}
          {door === "hold" && (
            <li data-testid="track-position-on">
              Your {symbol} position is tracked. We check it after each close
              and tell you when a tier is hit — Livermore never sells.
            </li>
          )}
        </ul>
        <DoneLinks slug={context.savedSlug} advance={advance} label={copy.done} />
      </section>
    );
  }

  // ── declare the position ──────────────────────────────────────────────
  if (stage === "declare") {
    return (
      <section className="space-y-5" data-testid="flow-track-declare">
        <header>
          <h1 className="font-heading text-2xl font-bold">{copy.declareTitle}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your real numbers, not a simulation. The exit rules are measured
            from what you actually paid, so a wrong price moves every stop and
            target.
          </p>
        </header>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">
              Shares of {symbol ?? "the stock"}
            </span>
            <input
              value={shares}
              onChange={(e) => setShares(e.target.value)}
              inputMode="decimal"
              placeholder="120"
              data-testid="track-shares"
              className="rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-muted-foreground">
              Average price paid
            </span>
            <input
              value={cost}
              onChange={(e) => setCost(e.target.value)}
              inputMode="decimal"
              placeholder="118.40"
              data-testid="track-cost"
              className="rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
          </label>
        </div>

        {error && (
          <p className="text-sm text-destructive" data-testid="track-error">{error}</p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={submitPosition}
            disabled={busy}
            data-testid="track-declare-submit"
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
          >
            {busy ? "Saving…" : copy.declareConfirm}
          </button>
          <button
            type="button"
            onClick={() => setStage("done")}
            data-testid="track-declare-skip"
            className="text-[13px] font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline"
          >
            Skip for now
          </button>
        </div>
      </section>
    );
  }

  // ── the exit ladder, and its sign-off ─────────────────────────────────
  if (stage === "ladder") {
    return (
      <section className="space-y-5" data-testid="flow-track-ladder">
        <header>
          <h1 className="font-heading text-2xl font-bold">{copy.ladderTitle}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {seeding
              ? "Reading recent volatility…"
              : source === "calculated" && natr !== null
                ? `Scaled to ${symbol}'s recent volatility — its average daily range is about ${natr.toFixed(1)}%. Derived from price history, not optimised, and yours to change.`
                : `Starting points, not a recommendation${symbol ? ` — we couldn't read ${symbol}'s recent volatility` : ""}. Set them to what you would actually do.`}
          </p>
        </header>

        {!seeding && (
          <ExitLadderEditor value={tiers} onChange={setTiers} disabled={busy} />
        )}

        {/* §2.2 — name what is changing. This mutates a strategy the user
            already saved, and it must never read as a side effect of having
            clicked "Watch it". */}
        <div
          data-testid="track-ladder-signoff"
          className="rounded-lg border border-amber-200 bg-amber-50 p-3"
        >
          <p className="text-[13px] leading-relaxed text-amber-900">
            This updates <strong>&ldquo;{title}&rdquo;</strong>. The exits
            become part of the strategy and apply to any position you track
            against it.
          </p>
        </div>

        {error && (
          <p className="text-sm text-destructive" data-testid="track-error">{error}</p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={confirmLadder}
            disabled={busy || seeding || tiers.length === 0}
            data-testid="track-ladder-confirm"
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
          >
            {busy ? "Saving…" : copy.ladderConfirm}
          </button>
          <button
            type="button"
            onClick={() => setStage("done")}
            data-testid="track-ladder-decline"
            className="text-[13px] font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline"
          >
            {copy.ladderDecline}
          </button>
        </div>

        {door === "hold" && (
          <p className="text-[12px] text-muted-foreground">
            Tracking a position needs an exit rule — there would be nothing to
            monitor it against otherwise.
          </p>
        )}
      </section>
    );
  }

  // ── the three doors ───────────────────────────────────────────────────
  return (
    <section className="space-y-5" data-testid="flow-track-doors">
      <header>
        <h1 className="font-heading text-2xl font-bold">{copy.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          &ldquo;{title}&rdquo; is saved. A backtest is a claim about the past
          — this is where you decide whether it watches the market for you.
        </p>
      </header>

      <div className="grid gap-2.5">
        <DoorButton
          testId="track-door-watch"
          label={copy.doorWatch}
          sub={copy.doorWatchSub}
          onClick={() => pickDoor("watch")}
        />
        <DoorButton
          testId="track-door-hold"
          label={copy.doorHold}
          sub={copy.doorHoldSub}
          onClick={() => pickDoor("hold")}
        />
        <DoorButton
          testId="track-door-skip"
          label={copy.doorSkip}
          sub={copy.doorSkipSub}
          muted
          onClick={() => pickDoor("skip")}
        />
      </div>
    </section>
  );
}

function DoorButton({
  label, sub, onClick, testId, muted,
}: {
  label: string;
  sub: string;
  onClick: () => void;
  testId: string;
  muted?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={
        "rounded-lg border p-3.5 text-left transition " +
        (muted
          ? "border-border bg-card hover:bg-accent"
          : "border-primary/40 bg-card hover:border-primary/70 hover:bg-accent")
      }
    >
      <span className="block text-sm font-semibold text-foreground">{label}</span>
      <span className="mt-0.5 block text-[12px] text-muted-foreground">{sub}</span>
    </button>
  );
}

function DoneLinks({
  slug, advance, label,
}: {
  slug?: string;
  advance: () => void;
  label: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={advance}
        data-testid="track-finish"
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
      >
        {label}
      </button>
      {slug && (
        <Link
          href={`/strategies/${slug}` as Route}
          data-testid="track-open-strategy"
          className="text-[13px] font-medium text-primary underline-offset-2 hover:underline"
        >
          Open the strategy →
        </Link>
      )}
    </div>
  );
}

/** One clause describing the ladder, for the confirmation. Reads the tiers
 *  rather than restating what we intended to save. */
export function describeLadder(tiers: ExitTier[]): string {
  const stop = tiers.find((t) => t.trigger_pct < 0 && t.action === "sell_all");
  const targets = tiers.filter((t) => t.trigger_pct > 0);
  const pct = (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
  const parts: string[] = [];
  if (stop) parts.push(`stop at ${pct(stop.trigger_pct)}`);
  if (targets.length === 1) parts.push(`target at ${pct(targets[0].trigger_pct)}`);
  else if (targets.length > 1) {
    parts.push(`targets at ${targets.map((t) => pct(t.trigger_pct)).join(" and ")}`);
  }
  return parts.join(", ") || "no tiers";
}
