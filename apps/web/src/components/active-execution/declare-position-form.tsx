/**
 * active-execution-v2 PR2 — DeclarePositionForm.
 *
 * Lets the user declare a position they ACTUALLY hold (symbol + shares +
 * average cost), to be tracked against the strategy's exit ladder.
 * Livermore never simulates a fill — these are the user's real numbers.
 *
 * On submit → POST /api/saved-strategies/{id}/positions. On success,
 * calls `onDeclared` so the parent dashboard can refresh its positions
 * grid. Surfaces the backend's `detail` text on error (e.g. "strategy
 * isn't set up for active execution", "an open position already exists").
 *
 * Trap #19: reads `backendToken` off `useSession()`; the submit is
 * gated on `sessionStatus !== "loading"`.
 */
"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";

import { declarePosition } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  strategyId: string;
  onDeclared?: () => void;
  className?: string;
}

export function DeclarePositionForm({
  strategyId,
  onDeclared,
  className,
}: Props) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string })
    ?.backendToken;

  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState("");
  const [shares, setShares] = useState("");
  const [entryPrice, setEntryPrice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setSymbol("");
    setShares("");
    setEntryPrice("");
    setError(null);
  };

  const canSubmit =
    sessionStatus !== "loading" &&
    !!backendToken &&
    symbol.trim().length > 0 &&
    Number(shares) > 0 &&
    Number(entryPrice) > 0 &&
    !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await declarePosition(
        strategyId,
        {
          symbol: symbol.trim().toUpperCase(),
          shares: Number(shares),
          entry_price: Number(entryPrice),
        },
        backendToken ?? "",
      );
      reset();
      setOpen(false);
      onDeclared?.();
    } catch (e) {
      setError((e as Error).message || "Couldn't declare the position.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        data-testid="declare-position-open"
        onClick={() => setOpen(true)}
        className={cn(
          "rounded-md border border-dashed border-slate-300 bg-white px-3 py-1.5 text-[12px] font-semibold text-slate-700 hover:border-slate-400 hover:bg-slate-50",
          className,
        )}
      >
        + Declare a position you hold
      </button>
    );
  }

  return (
    <div
      data-testid="declare-position-form"
      className={cn(
        "rounded-lg border border-slate-200 bg-white p-4",
        className,
      )}
    >
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Declare a position
      </p>
      <p className="mb-3 text-[12px] leading-snug text-slate-500">
        Enter the position you actually hold. Livermore tracks it against
        this strategy&rsquo;s exit ladder and notifies you when a tier
        triggers — you execute in your own brokerage.
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-slate-500">Symbol</span>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="NVDA"
            data-testid="declare-symbol"
            className="rounded border border-slate-200 px-2 py-1.5 text-sm uppercase"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-slate-500">Shares</span>
          <input
            type="number"
            min="0"
            step="any"
            value={shares}
            onChange={(e) => setShares(e.target.value)}
            placeholder="100"
            data-testid="declare-shares"
            className="rounded border border-slate-200 px-2 py-1.5 text-sm"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-slate-500">Avg cost ($)</span>
          <input
            type="number"
            min="0"
            step="any"
            value={entryPrice}
            onChange={(e) => setEntryPrice(e.target.value)}
            placeholder="145.00"
            data-testid="declare-entry-price"
            className="rounded border border-slate-200 px-2 py-1.5 text-sm"
          />
        </label>
      </div>

      {error && (
        <p
          data-testid="declare-error"
          className="mt-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-1.5 text-[12px] text-rose-700"
        >
          {error}
        </p>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          disabled={!canSubmit}
          onClick={handleSubmit}
          data-testid="declare-submit"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Track this position"}
        </button>
        <button
          type="button"
          onClick={() => {
            reset();
            setOpen(false);
          }}
          data-testid="declare-cancel"
          className="text-[12px] font-medium text-slate-500 hover:text-slate-700"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
