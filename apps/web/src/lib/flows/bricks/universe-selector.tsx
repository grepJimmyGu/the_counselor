/**
 * PRD-23b — UniverseSelector.
 *
 * The unified-mode entry: pick the universe a reading runs over. A single
 * symbol is just a universe of size 1, so this REPLACES the old bare
 * "backtest symbol" input — the symbol box lives inside the entered-symbols
 * tier.
 *
 * Tiers: Enter your own symbol(s) (the Build-from-Scratch tier) · S&P 500 ·
 * Sector · My watchlist · My portfolio. Emits `{ universe_id, entered_symbols }`
 * matching the backend `universe_resolver` tiers — `sp500` / `sector_<key>` are
 * standing (snapshot scan→rank); the rest carry a client-supplied membership.
 *
 * Controlled. `lockedTiers` (driven by the caller's entitlements) renders a
 * tier as gated; selecting it fires `onLockedSelect` instead of switching.
 */
"use client";

import { useId } from "react";

import type { ScreenUniverseId } from "@/lib/contracts";
import { cn } from "@/lib/utils";

/** Mirror backend `is_standing_universe` (universe_resolver.py): sp500 /
 *  sector_* ride the daily snapshot; the rest backtest their members directly. */
export function isStandingUniverse(universeId: string | null | undefined): boolean {
  return (
    universeId === "sp500" ||
    (typeof universeId === "string" && universeId.startsWith("sector_"))
  );
}

type TierKey = "symbols" | "sp500" | "sector" | "watchlist" | "portfolio";

interface TierDef {
  key: TierKey;
  label: string;
  hint: string;
  /** "entry" tiers take a client symbol list; "standing"/"sector" don't. */
  kind: "entry" | "standing" | "sector";
}

const TIERS: TierDef[] = [
  { key: "symbols", label: "Enter your own symbol(s)", hint: "Backtest one name or a handful", kind: "entry" },
  { key: "sp500", label: "S&P 500", hint: "Screen the whole index", kind: "standing" },
  { key: "sector", label: "Sector", hint: "Screen one S&P sector", kind: "sector" },
  { key: "watchlist", label: "My watchlist", hint: "Screen your saved names", kind: "entry" },
  { key: "portfolio", label: "My portfolio", hint: "Screen your holdings", kind: "entry" },
];

// US sector labels for the sub-picker. `sector_<label>` matches
// SymbolCache.sector on the backend (label normalization is a v1 follow-up).
const SECTORS = [
  "Technology",
  "Financial Services",
  "Healthcare",
  "Consumer Cyclical",
  "Communication Services",
  "Industrials",
  "Consumer Defensive",
  "Energy",
  "Basic Materials",
  "Real Estate",
  "Utilities",
];

function activeTier(universeId: string | null | undefined): TierKey {
  // Null-safe: a context resumed from a pre-PRD-23b sessionStorage entry has
  // no universe_id — fall back to the entered-symbols tier rather than crash.
  if (universeId === "sp500") return "sp500";
  if (typeof universeId === "string" && universeId.startsWith("sector_")) return "sector";
  if (universeId === "watchlist") return "watchlist";
  if (universeId === "portfolio") return "portfolio";
  return "symbols";
}

// Tiers with no real v1 backend membership yet — shown locked ("soon") rather
// than as a misleading empty manual-entry box. They light up when the backend
// watchlist/portfolio universes land (PRD-23c+).
const COMING_SOON: TierKey[] = ["watchlist", "portfolio"];

interface Props {
  universeId: ScreenUniverseId;
  enteredSymbols: string[];
  onChange: (next: { universe_id: ScreenUniverseId; entered_symbols: string[] }) => void;
  /** Tier keys the current tier can't access (entitlement-gated). */
  lockedTiers?: TierKey[];
  onLockedSelect?: (tier: TierKey) => void;
  className?: string;
}

export function UniverseSelector({
  universeId,
  enteredSymbols,
  onChange,
  lockedTiers = [],
  onLockedSelect,
  className,
}: Props) {
  const selectId = useId();
  const tier = activeTier(universeId);
  const locked = new Set<TierKey>([...lockedTiers, ...COMING_SOON]);

  const selectTier = (t: TierDef) => {
    if (locked.has(t.key)) {
      onLockedSelect?.(t.key);
      return;
    }
    if (t.kind === "standing") {
      onChange({ universe_id: "sp500", entered_symbols: [] });
    } else if (t.kind === "sector") {
      onChange({ universe_id: `sector_${SECTORS[0]}`, entered_symbols: [] });
    } else {
      // entry tiers keep the existing membership so switching among them
      // doesn't lose what the user typed.
      onChange({ universe_id: t.key, entered_symbols: enteredSymbols });
    }
  };

  const selectedSector = tier === "sector" ? universeId.slice("sector_".length) : SECTORS[0];

  return (
    <div data-testid="universe-selector" className={cn("flex flex-col gap-3", className)}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {TIERS.map((t) => {
          const isLocked = locked.has(t.key);
          const isActive = tier === t.key;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => selectTier(t)}
              data-testid={`universe-tier-${t.key}`}
              aria-pressed={isActive}
              className={cn(
                "flex flex-col items-start rounded-lg border px-3 py-2 text-left transition",
                isActive
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
                isLocked && "opacity-60",
              )}
            >
              <span className="flex items-center gap-1 text-[13px] font-semibold">
                {t.label}
                {isLocked && <span aria-hidden className="text-[11px]">🔒</span>}
              </span>
              <span
                className={cn(
                  "text-[11px]",
                  isActive ? "text-slate-200" : "text-slate-400",
                )}
              >
                {COMING_SOON.includes(t.key) ? "Coming soon" : t.hint}
              </span>
            </button>
          );
        })}
      </div>

      {/* Entered-symbols tier — a SINGLE symbol (a universe of size 1). The
          direct backtest is single-asset; screening a basket is what the
          standing universes (S&P 500 / sector) are for. Keeping this single
          avoids silently dropping extra names the old multi-input invited. */}
      {tier === "symbols" && (
        <label data-testid="universe-entry" className="flex flex-col gap-1">
          <input
            type="text"
            value={enteredSymbols[0] ?? ""}
            placeholder="e.g. NVDA"
            onChange={(e) => {
              const sym = e.target.value.trim().toUpperCase();
              onChange({ universe_id: "symbols", entered_symbols: sym ? [sym] : [] });
            }}
            data-testid="universe-symbol-input"
            className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium uppercase tracking-wider placeholder:font-normal placeholder:tracking-normal placeholder:lowercase focus:border-slate-400 focus:outline-none"
          />
          <span className="text-[11px] text-slate-500">
            Backtest one symbol. Pick S&amp;P 500 or a sector to screen a basket.
          </span>
        </label>
      )}

      {tier === "sector" && (
        <label className="flex flex-col gap-1 text-[12px] text-slate-600">
          <span className="font-medium">Sector</span>
          <select
            id={selectId}
            data-testid="universe-sector-select"
            value={selectedSector}
            onChange={(e) => onChange({ universe_id: `sector_${e.target.value}`, entered_symbols: [] })}
            className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-[13px] focus:border-slate-400 focus:outline-none"
          >
            {SECTORS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      )}

      {tier === "sp500" && (
        <p className="rounded-md bg-slate-50 px-3 py-2 text-[12px] text-slate-500">
          Screening the full S&amp;P 500 — compose a reading and watch it narrow the
          index to a matched basket.
        </p>
      )}
    </div>
  );
}
