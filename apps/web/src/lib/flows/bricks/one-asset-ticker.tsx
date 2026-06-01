"use client";

/**
 * <OneAssetTicker> — Mode 1's first step.
 *
 * Two entry shapes:
 *   1. Stock-page CTA passes `ticker` in `initialContext` → this brick
 *      auto-advances on mount. The user never sees the step.
 *   2. Home picker's "Pick an asset" CTA passes no ticker → this brick
 *      renders a thin ticker input that delegates to /api/symbols/search
 *      so the user can type any S&P 500 ticker and continue.
 *
 * Matches the portfolio-upload pattern: the brick owns its loading +
 * empty + valid states, and only `advance()`s once `context.ticker` is
 * known. Labels go through `useFlowCopy('one_asset_mode', key)`; the
 * keys are registered in `one-asset-mode.ts`.
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { searchSymbols } from "@/lib/api";
import type { SymbolSearchItem } from "@/lib/contracts";
import type { FlowStepProps } from "../types";
import { useFlowCopy } from "../copy";
import type { OneAssetModeContext } from "../one-asset-mode-context";

const VALID_TICKER = /^[A-Z][A-Z0-9.\-]{0,9}$/;

export function OneAssetTicker({
  context,
  updateContext,
  advance,
}: FlowStepProps<OneAssetModeContext>) {
  const title = useFlowCopy("one_asset_mode", "ticker_title");
  const subtitle = useFlowCopy("one_asset_mode", "ticker_subtitle");
  const placeholder = useFlowCopy("one_asset_mode", "ticker_placeholder");
  const continueLabel = useFlowCopy("one_asset_mode", "ticker_continue");
  const invalidMsg = useFlowCopy("one_asset_mode", "ticker_invalid");

  // Auto-advance when the trigger already provided a ticker (stock page).
  // We use a ref so the effect runs exactly once even under React strict
  // mode's double-invoke pattern.
  const autoAdvancedRef = React.useRef(false);
  React.useEffect(() => {
    if (autoAdvancedRef.current) return;
    if (context.ticker && context.ticker.trim()) {
      autoAdvancedRef.current = true;
      advance();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [context.ticker]);

  // Local input state for the home-picker entry path. Updates context
  // only on submit so the flow runtime doesn't persist half-typed
  // tickers to sessionStorage.
  const [input, setInput] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [suggestions, setSuggestions] = React.useState<SymbolSearchItem[]>([]);
  const [searching, setSearching] = React.useState(false);

  // Lightweight typeahead. /api/symbols/search is paid-cached and
  // already powers other surfaces (Stage 3 search). Debounce 200ms so
  // the network isn't pummelled on every keystroke.
  React.useEffect(() => {
    if (!input.trim()) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const t = window.setTimeout(() => {
      searchSymbols(input.trim())
        .then((results) => {
          if (cancelled) return;
          setSuggestions(results.slice(0, 5));
        })
        .catch(() => {
          if (cancelled) return;
          setSuggestions([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
      setSearching(false);
    };
  }, [input]);

  function submit(rawTicker?: string) {
    const raw = (rawTicker ?? input).trim().toUpperCase();
    if (!raw || !VALID_TICKER.test(raw)) {
      setError(invalidMsg);
      return;
    }
    setError(null);
    updateContext({ ticker: raw });
    autoAdvancedRef.current = true; // prevent the effect from re-firing
    advance();
  }

  // If the trigger seeded a ticker, the auto-advance effect handles
  // navigation — render nothing so we don't flash the empty form.
  if (context.ticker && context.ticker.trim()) {
    return null;
  }

  return (
    <section className="space-y-5" data-testid="one-asset-ticker">
      <header>
        <h1 className="font-heading text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
      </header>

      <div className="space-y-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={placeholder}
          autoFocus
          autoComplete="off"
          spellCheck={false}
          className="font-mono"
          data-testid="one-asset-ticker-input"
        />
        {error ? (
          <p className="text-sm text-red-600" data-testid="one-asset-ticker-error">
            {error}
          </p>
        ) : null}

        {searching && suggestions.length === 0 ? (
          <p className="text-xs text-muted-foreground">Searching…</p>
        ) : null}

        {suggestions.length > 0 ? (
          <ul
            className="rounded-xl border border-border bg-card"
            data-testid="one-asset-ticker-suggestions"
          >
            {suggestions.map((s) => (
              <li key={s.symbol} className="border-b border-border last:border-b-0">
                <button
                  type="button"
                  onClick={() => submit(s.symbol)}
                  className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-muted/30"
                  data-testid={`one-asset-ticker-suggestion-${s.symbol}`}
                >
                  <span className="font-mono text-sm font-semibold">{s.symbol}</span>
                  <span className="truncate text-xs text-muted-foreground">{s.name}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <Button
        onClick={() => submit()}
        disabled={!input.trim()}
        data-testid="one-asset-ticker-continue"
      >
        {continueLabel}
      </Button>
    </section>
  );
}
