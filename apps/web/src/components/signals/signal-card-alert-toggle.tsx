"use client";

/**
 * <SignalCardAlertToggle> — PRD-28 "alert me on this stock".
 *
 * Watches ONE symbol under ONE saved screen. The distinction that makes this
 * worth having: the saved-screen monitor notifies on basket **entrants** only,
 * so today you cannot be told a name you care about **dropped out** of your own
 * reading. This fires in both directions.
 *
 * Requires a saved screen — that's the reading the symbol is judged against.
 * With no screens, the toggle explains that instead of rendering a dead button
 * (there is no "default template" in the system to fall back on).
 *
 * Strategist+; a 402 pops the global upgrade modal via `fetchApi`, so the
 * component only has to keep its own state honest.
 */

import { useState } from "react";
import { Bell, BellRing, Loader2 } from "lucide-react";
import { useSession } from "next-auth/react";

import { subscribeTickerAlert, unsubscribeTickerAlert } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface AlertScreenOption {
  id: string;
  title: string;
}

export function SignalCardAlertToggle({
  symbol,
  screens,
  initialScreenId = null,
  className,
}: {
  symbol: string;
  /** The user's saved screens — the readings a symbol can be judged against. */
  screens: AlertScreenOption[];
  /** Non-null when the user already has an alert on this symbol. */
  initialScreenId?: string | null;
  className?: string;
}) {
  const { data: session, status: sessionStatus } = useSession();
  const backendToken = (session as { backendToken?: string } | null)?.backendToken;

  const [subscribedTo, setSubscribedTo] = useState<string | null>(initialScreenId);
  const [screenId, setScreenId] = useState<string>(
    initialScreenId ?? screens[0]?.id ?? "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signedIn = sessionStatus === "authenticated" && Boolean(backendToken);

  if (screens.length === 0) {
    return (
      <p
        data-testid="alert-toggle-no-screens"
        className={cn("text-[11px] text-muted-foreground", className)}
      >
        Save a screen first — alerts watch {symbol} against a screen&rsquo;s reading.
      </p>
    );
  }

  const toggle = async () => {
    if (!signedIn || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (subscribedTo) {
        await unsubscribeTickerAlert(symbol, subscribedTo, backendToken as string);
        setSubscribedTo(null);
      } else {
        await subscribeTickerAlert(
          { symbol, saved_screen_id: screenId },
          backendToken as string,
        );
        setSubscribedTo(screenId);
      }
    } catch (e: unknown) {
      // A 402 already surfaced the upgrade modal; keep the inline note generic
      // so we never claim success we didn't get.
      setError(e instanceof Error ? e.message : "Couldn't update the alert.");
    } finally {
      setBusy(false);
    }
  };

  const on = Boolean(subscribedTo);
  const activeTitle = screens.find((s) => s.id === subscribedTo)?.title;

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex flex-wrap items-center gap-2">
        {!on && screens.length > 1 && (
          <select
            value={screenId}
            onChange={(e) => setScreenId(e.target.value)}
            aria-label="Screen to watch against"
            data-testid="alert-toggle-screen"
            className="rounded-md border border-border bg-white px-2 py-1 text-[11px] text-foreground"
          >
            {screens.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          onClick={() => void toggle()}
          disabled={!signedIn || busy}
          data-testid="alert-toggle"
          data-subscribed={on ? "true" : "false"}
          title={
            signedIn
              ? undefined
              : "Sign in to get alerts when this stock's state changes"
          }
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors disabled:opacity-50",
            on
              ? "border-primary bg-primary/10 text-primary"
              : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
          )}
        >
          {busy ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : on ? (
            <BellRing className="h-3 w-3" />
          ) : (
            <Bell className="h-3 w-3" />
          )}
          {on ? "Alerting" : "Alert me"}
        </button>
      </div>
      {on && activeTitle && (
        <p data-testid="alert-toggle-active" className="text-[11px] text-muted-foreground">
          We&rsquo;ll tell you when {symbol} enters or leaves &ldquo;{activeTitle}&rdquo;.
        </p>
      )}
      {error && (
        <p data-testid="alert-toggle-error" className="text-[11px] text-rose-600">
          {error}
        </p>
      )}
    </div>
  );
}
