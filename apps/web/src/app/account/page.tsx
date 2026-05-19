"use client";

export const dynamic = "force-dynamic";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, Loader2 } from "lucide-react";
import { createPortalSession } from "@/lib/api";
import type { UserMe, Entitlements } from "@/lib/contracts";
import type { Route } from "next";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

const TIER_LABELS: Record<string, string> = {
  scout: "Scout",
  strategist: "Strategist",
  quant: "Quant",
};

const TIER_COLORS: Record<string, string> = {
  scout:      "border-sky-500/50 bg-sky-500/10 text-sky-700",
  strategist: "border-indigo-500/50 bg-indigo-500/10 text-indigo-700",
  quant:      "border-amber-500/50 bg-amber-500/10 text-amber-700",
};

export default function AccountPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [me, setMe] = useState<UserMe | null>(null);
  const [ents, setEnts] = useState<Entitlements | null>(null);
  const [handle, setHandle] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    if (status === "unauthenticated") router.push("/login" as Route);
  }, [status, router]);

  const backendToken = (session as any)?.backendToken as string | undefined;

  useEffect(() => {
    if (!backendToken) return;
    const headers = { Authorization: `Bearer ${backendToken}` };
    Promise.all([
      fetch(`${API_BASE}/api/me`, { headers }).then(r => r.json()),
      fetch(`${API_BASE}/api/me/entitlements`, { headers }).then(r => r.json()),
    ]).then(([meData, entsData]) => {
      setMe(meData);
      setEnts(entsData);
      setHandle(meData.handle ?? "");
      setDisplayName(meData.display_name ?? "");
    }).catch(() => {});
  }, [backendToken]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!backendToken) return;
    setSaving(true);
    setSaveMsg(null);
    const res = await fetch(`${API_BASE}/api/me`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${backendToken}`,
      },
      body: JSON.stringify({
        handle: handle.trim() || null,
        display_name: displayName.trim() || null,
      }),
    });
    setSaving(false);
    if (res.ok) {
      setSaveMsg("Saved.");
    } else {
      const d = await res.json().catch(() => ({}));
      setSaveMsg(d.detail ?? "Save failed.");
    }
  }

  if (status === "loading" || !me) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const tier = me.plan.tier;

  return (
    <main className="mx-auto max-w-2xl space-y-8 px-4 py-10">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">My Account</h1>
        <Badge variant="outline" className={TIER_COLORS[tier]}>
          {TIER_LABELS[tier]} plan
        </Badge>
      </div>

      {/* Profile */}
      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">Profile</h2>
        <p className="text-sm text-muted-foreground">{me.email}</p>
        <form onSubmit={handleSave} className="space-y-3">
          <div className="space-y-1">
            <label htmlFor="display_name" className="text-sm font-medium">Display name</label>
            <Input
              id="display_name"
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
              placeholder="Your name"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="handle" className="text-sm font-medium">Handle</label>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">@</span>
              <Input
                id="handle"
                value={handle}
                onChange={e => setHandle(e.target.value)}
                placeholder="yourhandle"
                className="font-mono"
              />
            </div>
            <p className="text-xs text-muted-foreground">3–32 chars, lowercase letters, digits, underscores only.</p>
          </div>
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" disabled={saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
            </Button>
            {saveMsg && (
              <span className={`text-xs ${saveMsg === "Saved." ? "text-emerald-600" : "text-destructive"}`}>
                {saveMsg}
              </span>
            )}
          </div>
        </form>
      </section>

      {/* Plan + Usage */}
      {ents && (
        <section className="space-y-4 rounded-xl border border-border bg-card p-6">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">Plan &amp; Usage</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              {
                label: "Backtests this month",
                value: ents.backtest_runs_remaining === null
                  ? `${me.usage.backtest_runs} run${me.usage.backtest_runs !== 1 ? "s" : ""} (unlimited)`
                  : `${me.usage.backtest_runs} / ${(me.usage.backtest_runs + (ents.backtest_runs_remaining ?? 0))}`,
              },
              { label: "Universe size max", value: `${ents.universe_size_max} symbols` },
              { label: "History window",    value: `${ents.history_window_years} years` },
              { label: "Asset classes",     value: ents.asset_classes.join(", ") },
              { label: "Commodity signals", value: ents.commodity_framework ? "Included" : "Upgrade to unlock" },
              { label: "API access",        value: ents.api_access ? "Enabled" : "Quant only" },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg border border-border bg-background px-4 py-3">
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className="mt-1 text-sm font-semibold">{value}</div>
              </div>
            ))}
          </div>
          {tier === "scout" && (
            <p className="text-xs text-muted-foreground">
              Upgrade to Strategist for unlimited backtests, 25-symbol universes, and commodity signals.{" "}
              <a href="/pricing" className="text-primary hover:underline">See plans →</a>
            </p>
          )}
        </section>
      )}

      {/* Billing management */}
      {me && (
        <BillingSection me={me} backendToken={backendToken} />
      )}
    </main>
  );
}

function BillingSection({ me, backendToken }: { me: UserMe; backendToken?: string }) {
  const [loading, setLoading] = useState(false);
  const { plan } = me;

  async function handlePortal() {
    if (!backendToken) return;
    setLoading(true);
    try {
      const { url } = await createPortalSession(backendToken);
      window.open(url, "_blank", "noopener");
    } catch { /* no-op */ } finally {
      setLoading(false);
    }
  }

  const trialDays = plan.trial_end
    ? Math.max(0, Math.ceil((new Date(plan.trial_end).getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : null;

  return (
    <section className="space-y-4 rounded-xl border border-border bg-card p-6">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">Billing</h2>
      <div className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Status</span>
          <span className="font-medium capitalize">{plan.status}</span>
        </div>
        {plan.billing_cycle && (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Billing cycle</span>
            <span className="font-medium capitalize">{plan.billing_cycle}</span>
          </div>
        )}
        {trialDays !== null && plan.status === "trialing" && (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Trial ends</span>
            <span className={`font-medium ${trialDays <= 3 ? "text-rose-600" : "text-amber-600"}`}>
              {trialDays} day{trialDays !== 1 ? "s" : ""} remaining
            </span>
          </div>
        )}
        {plan.current_period_end && plan.status === "active" && (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Next billing date</span>
            <span className="font-medium">{new Date(plan.current_period_end).toLocaleDateString()}</span>
          </div>
        )}
      </div>
      {plan.status === "trialing" ? (
        <div className="flex gap-2">
          <Button size="sm" asChild>
            <a href="/pricing">Add a card to keep access</a>
          </Button>
        </div>
      ) : plan.tier === "scout" || !plan.billing_cycle ? (
        <Button size="sm" variant="outline" asChild>
          <a href="/pricing">Upgrade plan</a>
        </Button>
      ) : (
        <Button size="sm" variant="outline" onClick={handlePortal} disabled={loading} className="gap-1.5">
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ExternalLink className="h-3.5 w-3.5" />}
          Manage billing
        </Button>
      )}
    </section>
  );
}
