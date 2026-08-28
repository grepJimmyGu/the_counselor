"use client";

/**
 * "Save as a rule" — PRD-43e §3.2, the step that closes the loop.
 *
 * Without this, a finding is a sentence you read once. The Rules object
 * exists so it survives the tab closing, and this button is the only thing
 * that puts one there from a lens.
 *
 * ⚠ EVERYTHING SAVED FROM A 43b P0 FINDING IS `behavioural`, and the copy
 * says which claim is being made. §3.2 is explicit that the scope follows the
 * finding's SHAPE, not its sample size:
 *
 *   - a finding about what the user DID — a setup that loses, a holding
 *     pattern — is `behavioural`, and its CTA is "save as a rule about how I
 *     trade";
 *   - a finding proposing a MARKET CONDITION is `mechanical`, and its CTA
 *     carries the second claim: "save as a rule to test".
 *
 * 43b P0 is measurement only. Everything it produces is the first kind. The
 * counterfactual rules that could honestly be `mechanical` arrive with P1,
 * and labelling P0's output that way now would claim a market edge from a
 * description of one person's record.
 *
 * NO SAMPLE FLOOR HERE, deliberately. §3.1.1 and the §7 DoD both say a
 * behavioural rule has none — a fact about one's own trades needs no
 * significance test, and the floor is a `mechanical` concept. The N is
 * always rendered beside the finding, so the user is the one deciding
 * whether four trades is enough to change how they trade.
 */

import { useState } from "react";
import { Check, Plus } from "lucide-react";

import { createRule } from "@/lib/api";
import type { CreateRuleRequest } from "@/lib/contracts";

export function SaveRuleButton({
  backendToken,
  rule,
  label = "Save as a rule about how I trade",
  testid,
}: {
  backendToken: string;
  rule: CreateRuleRequest;
  label?: string;
  testid?: string;
}) {
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");

  if (state === "saved") {
    return (
      <span
        className="inline-flex items-center gap-1 text-[11px] text-muted-foreground"
        data-testid={testid ? `${testid}-saved` : undefined}
      >
        <Check className="h-3 w-3" />
        In your rules
      </span>
    );
  }

  return (
    <button
      type="button"
      disabled={state === "saving"}
      data-testid={testid}
      onClick={() => {
        setState("saving");
        createRule(backendToken, rule)
          .then(() => setState("saved"))
          // A failed save must not look like a successful one. The finding is
          // still on screen; the user can try again.
          .catch(() => setState("failed"));
      }}
      className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
    >
      <Plus className="h-3 w-3" />
      {state === "failed" ? "Didn't save — try again" : label}
    </button>
  );
}
