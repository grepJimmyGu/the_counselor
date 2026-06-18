"use client";

/**
 * PRD-24a §5 — recommended-template pre-load for `custom_build_mode`.
 *
 * When the composer is reached via a deep link carrying `?template=<id>`
 * (the Home "Best Momentum Pick" card, the template gallery), this hook
 * hydrates the registry's composer rules into the canvas:
 *
 *   1. Look up `<id>` in RECOMMENDED_TEMPLATES (composer kind only).
 *   2. Fetch the signal catalog (localStorage-cached) and index it by id.
 *   3. Map each registry `StrategyRule` → a `BuildRule` (the canvas's
 *      editable shape — it needs the full `SignalPrimitive` snapshot that
 *      the registry, being data-only, doesn't carry).
 *   4. Seed `context.rules` + `context.universe_id`, then strip the query
 *      param so a refresh resumes the now-persisted draft instead of
 *      re-clobbering it.
 *
 * No-ops unless `?template=` is present, so the normal blank-composer
 * entry is untouched. Sentiment-kind templates never reach here (they
 * route to /sentiment), so a non-composer id is treated as not-found.
 *
 * Run-once: guarded by a ref, no effect deps. `updateContext` with the
 * same hydrated rules is idempotent, so even a StrictMode double-invoke
 * (same instance → ref preserved → second invoke early-returns) can't
 * double-apply.
 */

import { useEffect, useRef, useState } from "react";
import { getSignalPrimitives } from "@/lib/api";
import {
  getRecommendedTemplate,
  type ComposerTemplate,
} from "@/lib/recommended-templates";
import type { SignalPrimitive, StrategyRule } from "@/lib/contracts";
import type {
  BuildRule,
  CustomBuildModeContext,
} from "./custom-build-mode-context";

export type TemplatePreloadStatus =
  | "idle" // no ?template= param — nothing to do
  | "loading" // resolving the catalog
  | "done" // rules hydrated onto the canvas
  | "not_found" // ?template= present but not a composer template
  | "error"; // catalog fetch failed

export interface TemplatePreloadState {
  status: TemplatePreloadStatus;
  /** Display name of the template being loaded (for the canvas banner). */
  templateName: string | null;
}

function readParam(name: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return new URLSearchParams(window.location.search).get(name);
  } catch {
    return null;
  }
}

/** Drop the consumed params so a refresh resumes the persisted draft
 *  rather than re-running the (potentially destructive) pre-load. */
function stripParams(...names: string[]): void {
  if (typeof window === "undefined") return;
  try {
    const url = new URL(window.location.href);
    let changed = false;
    for (const n of names) {
      if (url.searchParams.has(n)) {
        url.searchParams.delete(n);
        changed = true;
      }
    }
    if (changed) {
      window.history.replaceState(
        null,
        "",
        url.pathname + url.search + url.hash,
      );
    }
  } catch {
    // ignore — leaving the param is harmless (the ref still guards re-run)
  }
}

function toBuildRule(
  rule: StrategyRule,
  primitive: SignalPrimitive,
  index: number,
): BuildRule {
  return {
    uid: `preload-${index}-${primitive.id}`,
    primitive_id: rule.primitive_id ?? primitive.id,
    primitive,
    primitive_params: { ...(rule.primitive_params ?? {}) },
    operator: rule.operator,
    threshold: rule.threshold,
    // The backend validator requires the FIRST rule's fold to be null and
    // every later rule's to be set; the registry already follows this, but
    // re-derive from position so a skipped rule can't leave a dangling fold.
    logic_with_prior: index === 0 ? null : rule.logic_with_prior ?? "AND",
  };
}

/**
 * Hydrate a recommended composer template onto the custom-build canvas
 * from a `?template=` deep link. Returns the load status + template name
 * so the canvas can show a one-line "Loaded …" confirmation.
 *
 * Overwrite semantics: a `?template=` deep link is explicit user intent
 * ("show me Best Momentum"), so it replaces any resumed draft. The param
 * is stripped after applying, so a refresh resumes the new draft instead.
 */
export function useTemplatePreload(
  updateContext: (patch: Partial<CustomBuildModeContext>) => void,
): TemplatePreloadState {
  const [state, setState] = useState<TemplatePreloadState>({
    status: "idle",
    templateName: null,
  });
  const didRun = useRef(false);
  // Keep the latest updateContext without making it an effect dep (the
  // effect must run exactly once, not on every parent re-render).
  const updateRef = useRef(updateContext);
  updateRef.current = updateContext;

  useEffect(() => {
    if (didRun.current) return;
    didRun.current = true;

    const templateId = readParam("template");
    if (!templateId) return; // stays "idle" — blank composer, untouched

    const template = getRecommendedTemplate(templateId);
    if (!template || template.kind !== "composer") {
      setState({ status: "not_found", templateName: null });
      stripParams("template", "universe");
      return;
    }
    const composer = template as ComposerTemplate;
    setState({ status: "loading", templateName: composer.name });

    getSignalPrimitives()
      .then((catalog) => {
        const byId = new Map(catalog.primitives.map((p) => [p.id, p]));
        const rules: BuildRule[] = [];
        for (const rule of composer.rules) {
          const pid = rule.primitive_id;
          if (!pid) continue;
          const primitive = byId.get(pid);
          if (!primitive) continue; // missing from catalog — skip defensively
          rules.push(toBuildRule(rule, primitive, rules.length));
        }
        if (rules.length > 0) {
          // Guarantee the surviving rules[0] has a null fold.
          rules[0] = { ...rules[0], logic_with_prior: null };
        }
        updateRef.current({ rules, universe_id: composer.universe_id });
        setState({ status: "done", templateName: composer.name });
        stripParams("template", "universe");
      })
      .catch(() => {
        // Leave the param so a manual refresh can retry the fetch.
        setState({ status: "error", templateName: composer.name });
      });
    // Run-once: deps intentionally omitted (guarded by didRun).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}
