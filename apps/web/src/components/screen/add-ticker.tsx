"use client";

/**
 * "Add ticker" — hand-add a name to a result set (Jimmy's spec item 3).
 *
 * The screen answers "which names match". This answers "…and also show me
 * NVDA", which is what people actually do with a screen: run it, then check
 * the two or three names they already had in mind against the same columns.
 *
 * An added name is NOT a match and is never counted as one. It sorts with
 * everything else — a ranking that quietly floated pinned rows to the top
 * would be a lie about the ordering — but it carries a badge, and metric
 * filters skip it, because the user asked for it by name.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, Search, X } from "lucide-react";

import { searchSymbols } from "@/lib/api";
import type { SymbolSearchItem } from "@/lib/contracts";

/** Cap on hand-added names. Past a handful this stops being "compare these
 *  against my screen" and becomes a different feature (a watchlist). */
export const MAX_ADDED_TICKERS = 10;

export function AddTicker({
  added,
  onAdd,
  onRemove,
  /** Symbols already matched by the screen — adding one is a no-op. */
  matched,
}: {
  added: string[];
  onAdd: (symbol: string) => void;
  onRemove: (symbol: string) => void;
  matched: Set<string>;
}) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<SymbolSearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: globalThis.MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Debounced lookup. `/api/symbols/search` hits Alpha Vantage on a local
  // cache miss, so per-keystroke would be both slow and a quota burn.
  useEffect(() => {
    const q = term.trim();
    if (q.length < 1) {
      setResults([]);
      return;
    }
    let live = true;
    setSearching(true);
    const t = setTimeout(() => {
      searchSymbols(q)
        .then((r) => live && setResults(r.slice(0, 8)))
        .catch(() => live && setResults([]))
        .finally(() => live && setSearching(false));
    }, 250);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [term]);

  const add = useCallback(
    (symbol: string) => {
      const sym = symbol.trim().toUpperCase();
      if (!sym) return;
      // Both refusals are stated. A control that silently does nothing reads
      // as broken, and "it's already in your results" is the answer the user
      // needs — not an error.
      if (matched.has(sym)) {
        setNote(`${sym} already matches this screen.`);
        return;
      }
      if (added.includes(sym)) {
        setNote(`${sym} is already added.`);
        return;
      }
      if (added.length >= MAX_ADDED_TICKERS) {
        setNote(`${MAX_ADDED_TICKERS} added tickers max.`);
        return;
      }
      onAdd(sym);
      setTerm("");
      setResults([]);
      setNote(null);
      setOpen(false);
    },
    [added, matched, onAdd],
  );

  return (
    <div className="flex flex-wrap items-center gap-2">
      {added.map((sym) => (
        <span
          key={sym}
          data-testid={`added-ticker-${sym}`}
          className="inline-flex items-center gap-1.5 rounded-full border border-sky-300 bg-sky-50 px-3 py-1 font-mono text-sm"
        >
          {sym}
          <button
            type="button"
            onClick={() => onRemove(sym)}
            aria-label={`Remove ${sym}`}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </span>
      ))}

      <div className="relative" ref={ref}>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          data-testid="add-ticker-toggle"
          aria-expanded={open}
          className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          Add ticker
        </button>

        {open && (
          <div
            data-testid="add-ticker-panel"
            className="absolute left-0 z-30 mt-2 w-72 rounded-lg border border-border bg-white p-3 shadow-lg"
          >
            <div className="flex items-center gap-2 rounded border border-border px-2 py-1">
              <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <input
                autoFocus
                value={term}
                onChange={(e) => {
                  setTerm(e.target.value);
                  setNote(null);
                }}
                onKeyDown={(e) => {
                  // Enter takes the first suggestion, or the raw text if the
                  // lookup found nothing — a valid ticker the symbol cache
                  // doesn't happen to know still deserves to be addable.
                  if (e.key === "Enter") add(results[0]?.symbol ?? term);
                }}
                placeholder="Ticker or company…"
                aria-label="Ticker or company"
                data-testid="add-ticker-input"
                className="w-full text-sm outline-none"
              />
            </div>

            {note && (
              <p className="mt-2 text-xs text-amber-700" data-testid="add-ticker-note">
                {note}
              </p>
            )}

            {searching && term.trim() && results.length === 0 && (
              <p className="mt-2 text-xs text-muted-foreground">Searching…</p>
            )}

            {results.length > 0 && (
              <ul className="mt-2 max-h-56 overflow-y-auto" data-testid="add-ticker-results">
                {results.map((r) => {
                  const already = matched.has(r.symbol) || added.includes(r.symbol);
                  return (
                    <li key={r.symbol}>
                      <button
                        type="button"
                        onClick={() => add(r.symbol)}
                        data-testid={`add-ticker-option-${r.symbol}`}
                        className="flex w-full items-baseline gap-2 rounded px-2 py-1 text-left text-sm transition-colors hover:bg-muted"
                      >
                        <span className="font-mono font-semibold">{r.symbol}</span>
                        <span className="truncate text-xs text-muted-foreground">{r.name}</span>
                        {already && (
                          <span className="ml-auto shrink-0 text-[10px] uppercase tracking-wider text-muted-foreground">
                            on list
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
