"use client";

/**
 * My Rules — PRD-43e §3.3.
 *
 * The user's first visible systematic framework, and for many people it is
 * the DESTINATION rather than a waypoint. Constraint 6 is explicit: every
 * surface is complete at its level, and the next level is offered, never
 * required. So there is no "now build a Playbook" nag here, and nothing on
 * this page implies a rule is unfinished for not having climbed.
 *
 * THE ONE THING THIS SCREEN MUST NEVER DO is render a behavioural rule as
 * though it were missing something. "Stop entering oversold" — 0 winners in
 * 8 — will never pass a walk-forward, and it is still the most actionable
 * thing the product has said to this user. An empty `validated` chip on that
 * card would turn the packet's best output into a deficiency notice. The
 * backend derives `is_terminal` for exactly this reason, so the decision is
 * made once, server-side, rather than re-implemented in every surface that
 * shows a rule.
 *
 * The second is subtler. A rule that appears in a Playbook which later
 * validated may SAY SO — it is a true statement about where the rule has
 * been — but that is provenance, never a checkmark on the rule itself. A
 * Playbook is a conjunction; when it passes, the evidence belongs to the
 * combination. Any member might be inert, doing all the work, or actively
 * harmful and outvoted.
 */

import { useCallback, useEffect, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";

import { deleteRule, listRules, promoteRule } from "@/lib/api";
import type { Rule } from "@/lib/contracts";

/** The sequence of a decision — what to trade, when in, how much, when out,
 *  and the standing constraints over all of it. Not alphabetical. */
const GROUPS: Array<{ type: Rule["rule_type"]; label: string; blurb: string }> = [
  { type: "selection", label: "What I trade", blurb: "Which names are even eligible." },
  { type: "entry", label: "When I buy", blurb: "What has to be true before you open." },
  { type: "sizing", label: "How much", blurb: "How the money is split across positions." },
  { type: "exit", label: "When I sell", blurb: "Decided in advance, not in the moment." },
  { type: "portfolio", label: "Standing limits", blurb: "Constraints over the whole book." },
];

const SOURCE_LABEL: Record<string, string> = {
  user: "You wrote this",
  trade_analysis: "From your trade timing",
  stock_analysis: "From your stock picking",
  allocation_analysis: "From your allocation",
};

function Chip({ tone, children }: { tone: "done" | "tested" | "open"; children: React.ReactNode }) {
  const cls =
    tone === "done"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
      : tone === "tested"
        ? "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-200"
        : "border-border bg-muted/40 text-muted-foreground";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${cls}`}>
      {children}
    </span>
  );
}

function RuleCard({
  rule,
  onDelete,
  onPromote,
}: {
  rule: Rule;
  onDelete: (id: string) => void;
  onPromote: (id: string) => void;
}) {
  const provenance =
    rule.sample_size !== null && rule.sample_size !== undefined
      ? `${SOURCE_LABEL[rule.source] ?? rule.source} · ${rule.sample_size} ${rule.sample_size === 1 ? "trade" : "trades"}`
      : (SOURCE_LABEL[rule.source] ?? rule.source);

  return (
    <li
      className="rounded-lg border border-border bg-card px-4 py-3"
      data-testid={`rule-${rule.id}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[14px] font-medium text-foreground">{rule.name}</div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">{provenance}</div>
        </div>
        <div className="flex flex-none items-center gap-1.5">
          {/* A behavioural rule is FINISHED. It gets a completion chip, never
              an empty one, and never a prompt to go validate itself. */}
          {rule.is_terminal ? (
            <Chip tone="done">Finished</Chip>
          ) : rule.status === "tested" ? (
            <Chip tone="tested">Tested on your record</Chip>
          ) : (
            <Chip tone="open">Saved</Chip>
          )}
          <button
            type="button"
            onClick={() => onDelete(rule.id)}
            aria-label={`Delete ${rule.name}`}
            data-testid={`rule-delete-${rule.id}`}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {rule.historical_effect && (
        <p className="mt-1.5 text-[12px] text-muted-foreground" data-testid={`rule-effect-${rule.id}`}>
          {rule.historical_effect}
        </p>
      )}

      {/* Provenance, and pointedly not a status. */}
      {rule.included_in_validated_playbook.length > 0 && (
        <p className="mt-1.5 text-[11px] text-muted-foreground" data-testid={`rule-playbooks-${rule.id}`}>
          Used in {rule.included_in_validated_playbook.length}{" "}
          {rule.included_in_validated_playbook.length === 1 ? "playbook" : "playbooks"} that
          validated. That says where this rule has been, not that this rule is proven.
        </p>
      )}

      {/* Offered, never required — and only for a rule that is a claim about
          the user rather than about markets. */}
      {rule.is_terminal && (
        <button
          type="button"
          onClick={() => onPromote(rule.id)}
          data-testid={`rule-promote-${rule.id}`}
          className="mt-2 text-[12px] text-muted-foreground underline underline-offset-2 hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
        >
          Think this works as a market rule too? Test it →
        </button>
      )}
    </li>
  );
}

export function MyRules({ backendToken }: { backendToken: string }) {
  const [rules, setRules] = useState<Rule[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    listRules(backendToken)
      .then(setRules)
      .catch(() => setFailed(true));
  }, [backendToken]);

  useEffect(load, [load]);

  const handleDelete = useCallback(
    (id: string) => {
      setRules((prev) => (prev ?? []).filter((r) => r.id !== id));
      deleteRule(backendToken, id).catch(load);
    },
    [backendToken, load],
  );

  const handlePromote = useCallback(
    (id: string) => {
      promoteRule(backendToken, id)
        .then((updated) =>
          setRules((prev) => (prev ?? []).map((r) => (r.id === id ? updated : r))),
        )
        .catch(load);
    },
    [backendToken, load],
  );

  if (failed) {
    return (
      <p className="text-[13px] text-muted-foreground" data-testid="rules-failed">
        Couldn&rsquo;t load your rules just now.
      </p>
    );
  }

  if (!rules) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (rules.length === 0) {
    return (
      <p className="text-[13px] text-muted-foreground" data-testid="rules-empty">
        No rules yet. When something in your trading record turns out to be
        worth repeating &mdash; or worth stopping &mdash; you can save it here
        and it stays.
      </p>
    );
  }

  return (
    <div className="space-y-6" data-testid="my-rules">
      {GROUPS.map(({ type, label, blurb }) => {
        const group = rules.filter((r) => r.rule_type === type);
        // A group with nothing in it is not a gap to fill. Rendering an empty
        // slot for every category would turn a complete set of two rules into
        // a checklist someone feels behind on.
        if (group.length === 0) return null;
        return (
          <section key={type} data-testid={`rules-group-${type}`}>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {label}
            </h3>
            <p className="mt-0.5 text-[12px] text-muted-foreground">{blurb}</p>
            <ul className="mt-2 space-y-2">
              {group.map((rule) => (
                <RuleCard
                  key={rule.id}
                  rule={rule}
                  onDelete={handleDelete}
                  onPromote={handlePromote}
                />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
