"use client";

/**
 * PRD-27 — launch a screen from smart-search-parsed rules.
 *
 * The dispatcher (`POST /api/search/parse`) returns the parsed technical
 * conditions as `StrategyRule[]`. To reuse the existing screener surface we
 * hydrate them into the `custom_build_mode` canvas (the SAME shape the
 * `?template=` preload produces) and start the flow: its template step
 * auto-advances, landing the user on the compose canvas with the conditions
 * prefilled — one click from `ScreenResults`.
 */

import { getSignalPrimitives } from "@/lib/api";
import type { StrategyRule } from "@/lib/contracts";

import { startFlow } from "./runtime";
import { toBuildRule } from "./template-preload";
import type { BuildRule } from "./custom-build-mode-context";
// Side-effect import — registers `custom_build_mode` so startFlow can find it.
import "./custom-build-mode";

/**
 * Convert parsed rules → BuildRules against the live catalog and start the
 * composer flow over `universeId`. Returns false (starting nothing) when none
 * of the parsed rules map to a known catalog primitive, so the caller can show
 * an "ask" message instead of dropping the user on an empty canvas.
 */
export async function launchScreenFromParsedRules(
  rules: StrategyRule[],
  universeId: string,
): Promise<boolean> {
  const catalog = await getSignalPrimitives();
  const byId = new Map(catalog.primitives.map((p) => [p.id, p]));

  const buildRules: BuildRule[] = [];
  for (const rule of rules) {
    const pid = rule.primitive_id;
    if (!pid) continue;
    const primitive = byId.get(pid);
    if (!primitive) continue; // parser named a primitive the catalog lacks — skip
    buildRules.push(toBuildRule(rule, primitive, buildRules.length));
  }
  if (buildRules.length === 0) return false;

  // The backend validator requires rule[0].logic_with_prior === null.
  buildRules[0] = { ...buildRules[0], logic_with_prior: null };

  startFlow("custom_build_mode", {
    initialContext: {
      fromTrigger: "home/smart_search",
      rules: buildRules,
      universe_id: universeId,
    },
  });
  return true;
}
