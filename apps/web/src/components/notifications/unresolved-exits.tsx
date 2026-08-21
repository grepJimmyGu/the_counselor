"use client";

/**
 * Exits that fired and the user has not resolved.
 *
 * THE POINT OF THIS SURFACE. An exit alert used to arrive as an email and a
 * `NotificationBannerEntry` — both of which can be missed, and the banner
 * dismissed. Dismissing is how you clear a notice, not how you decide about
 * a position, but until now it was the same gesture: tidy the banner away
 * and the fact that a stop had fired went with it.
 *
 * This list is DERIVED server-side from each position's `trade_log`, so
 * there is nothing here to dismiss. It clears only when the exit is
 * genuinely resolved — the user confirms a sale, or records that they are
 * holding. Missing the email makes an exit LATE rather than LOST, which is
 * the difference between a monitor you can rely on and one you cannot.
 *
 * DELIBERATELY NOT DISMISSIBLE. No X. The two buttons are the two real
 * answers, and both of them are legitimate.
 *
 * WHY "I SOLD" NAVIGATES INSTEAD OF POSTING. Confirming needs the user's
 * ACTUAL fill — how many shares, at what price. Inventing those numbers
 * would write a trade that never happened into the position's P&L, so this
 * hands off to the position card, where the existing confirm affordance
 * collects them. "I'm holding" sells nothing, so it can post directly.
 *
 * COPY. §11 register throughout: report what the rule did, hand the
 * decision back. Never "you should", never "advice", never imply Livermore
 * sold anything.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useSession } from "next-auth/react";

import { holdThroughExit, listUnresolvedExits } from "@/lib/api";
import { ExitTicket } from "@/components/notifications/exit-ticket";
import { Disclaimer } from "@/components/legal/disclaimer";
import type { UnresolvedExit } from "@/lib/contracts";

function pct(v?: number | null) {
  if (v === null || v === undefined) return null;
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
}

export function UnresolvedExits() {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as unknown as { backendToken?: string } | null)
    ?.backendToken;

  const [items, setItems] = useState<UnresolvedExit[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  // Tickets are collapsed by default: the list must stay scannable when
  // several exits are open, and the ticket is what you reach for once
  // you have decided to act on a particular one.
  const [openTicket, setOpenTicket] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!backendToken) return;
    listUnresolvedExits(backendToken)
      .then(setItems)
      .catch(() => setItems([]));
  }, [backendToken]);

  useEffect(() => {
    // Wait for NextAuth to resolve, or a signed-in user fires this
    // anonymously during the loading window and gets nothing back.
    if (sessionStatus === "loading") return;
    load();
  }, [sessionStatus, load]);

  async function hold(item: UnresolvedExit) {
    if (!backendToken) return;
    const key = `${item.position_id}:${item.trigger_type}`;
    setBusy(key);
    try {
      await holdThroughExit(
        item.strategy_id,
        item.position_id,
        { trigger_type: item.trigger_type },
        backendToken,
      );
      setItems((prev) =>
        prev.filter(
          (i) =>
            !(
              i.position_id === item.position_id &&
              i.trigger_type === item.trigger_type
            ),
        ),
      );
    } catch {
      setBusy(null);
      return;
    }
    setBusy(null);
  }

  if (items.length === 0) return null;

  return (
    <section
      data-testid="unresolved-exits"
      className="mb-6 rounded-xl border border-amber-300 bg-amber-50/70 p-4"
    >
      <h2 className="text-sm font-semibold text-slate-900">
        {items.length === 1
          ? "A strategy signalled an exit"
          : `${items.length} strategies signalled exits`}
      </h2>
      <p className="mt-0.5 text-[13px] text-slate-600">
        Nothing has been sold — Livermore does not place trades. These stay
        here until you tell us what you did.
      </p>

      <ul className="mt-3 space-y-2">
        {items.map((item) => {
          const key = `${item.position_id}:${item.trigger_type}`;
          const change = pct(item.pct_change);
          return (
            <li
              key={key}
              data-testid={`unresolved-exit-${item.symbol}`}
              className="rounded-lg border border-amber-200 bg-white px-3 py-2.5"
            >
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="font-mono text-sm font-semibold text-slate-900">
                  {item.symbol}
                </span>
                <span className="text-[13px] text-slate-700">
                  {item.tier_label ? `${item.tier_label} tier` : "Exit tier"}
                  {change ? ` reached at ${change}` : " reached"}
                </span>
                <span className="text-[12px] text-slate-500">
                  · {item.strategy_title}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() =>
                    setOpenTicket((cur) => (cur === key ? null : key))
                  }
                  data-testid={`toggle-ticket-${item.symbol}`}
                  className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-[12px] font-medium text-slate-800 transition hover:bg-slate-50"
                >
                  {openTicket === key ? "Hide ticket" : "Show order ticket"}
                </button>
                <Link
                  href={
                    `/strategies/${encodeURIComponent(item.strategy_id)}?action=executed` as Route
                  }
                  className="text-[12px] font-medium text-slate-600 underline-offset-2 transition hover:text-slate-800 hover:underline"
                >
                  I sold — record it
                </Link>
                <button
                  type="button"
                  disabled={busy === key}
                  onClick={() => hold(item)}
                  className="text-[12px] font-medium text-slate-500 underline-offset-2 transition hover:text-slate-700 hover:underline disabled:opacity-40"
                >
                  {busy === key ? "Saving…" : "I'm holding"}
                </button>
              </div>
              {openTicket === key && (
                <div className="mt-3">
                  <ExitTicket item={item} />
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {/* §11: short form visible, full text one click away. This is
          the surface where a user is being asked to act, which is
          where the disclosure has to be. */}
      <Disclaimer className="mt-3 border-t border-amber-200 pt-2.5" />
    </section>
  );
}
