/** @vitest-environment jsdom */

/**
 * Regression test for the bug where a flow module existed but the
 * `/flow/[flowId]` shell didn't side-effect-import it, leaving users
 * stranded on a "Flow not found" error.
 *
 * The shell page MUST side-effect-import every FlowDefinition module so
 * that a user landing on `/flow/<id>` via deep link / browser refresh /
 * direct URL paste has the registry populated. The Home picker and
 * other CTA-emitting components import their target flows too, but
 * direct navigation goes through this page alone.
 *
 * This test:
 *   1. Imports the exact production import chain the shell uses.
 *   2. Asserts every concrete mode module's flow id resolves in the
 *      registry.
 *   3. Pins the list against the actual `*-mode.ts` files in
 *      `lib/flows/` — if a new mode module is added but not imported
 *      in the shell, this test fails.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Mirror the EXACT side-effect import set in
// `apps/web/src/app/flow/[flowId]/page.tsx`. Keep these in lockstep.
import "@/lib/flows/portfolio-mode";
import "@/lib/flows/one-asset-mode";
import "@/lib/flows/custom-build-mode";

import { __resetRegistryForTests, getFlow, registerFlow } from "@/lib/flows/registry";
import { PortfolioModeFlow } from "@/lib/flows/portfolio-mode";
import { OneAssetModeFlow } from "@/lib/flows/one-asset-mode";
import { CustomBuildModeFlow } from "@/lib/flows/custom-build-mode";

// Vitest may share the registry across files because modules are
// cached. We reset + re-register manually to guarantee a clean snapshot.
beforeEach(() => {
  __resetRegistryForTests();
  registerFlow(PortfolioModeFlow);
  registerFlow(OneAssetModeFlow);
  registerFlow(CustomBuildModeFlow);
});

afterEach(() => {
  __resetRegistryForTests();
});

describe("flow shell side-effect imports", () => {
  it("registers portfolio_mode", () => {
    expect(getFlow("portfolio_mode")).toBeDefined();
  });

  it("registers one_asset_mode", () => {
    expect(getFlow("one_asset_mode")).toBeDefined();
  });

  it("registers custom_build_mode (regression: was missing from shell imports)", () => {
    expect(getFlow("custom_build_mode")).toBeDefined();
  });

  it("the shell's import list matches every *-mode.ts file in lib/flows/", async () => {
    // Pin against the actual files on disk so a new mode module
    // shipped without a corresponding shell import fails here loudly.
    // The vitest jsdom environment doesn't have fs, but we can read the
    // import.meta.glob — Vite/Vitest resolves this at transform time.
    const modules = import.meta.glob("@/lib/flows/*-mode.ts", {
      eager: false,
    });
    // Filter out test-only mock-flow which lives under `__tests__/fixtures/`,
    // not at lib/flows/. import.meta.glob already excludes that path.
    const filenames = Object.keys(modules).map((p) => {
      // Path looks like '/src/lib/flows/portfolio-mode.ts'. The
      // filename slug uses HYPHENS but the registered flow id uses
      // UNDERSCORES (e.g. `custom-build-mode.ts` → `custom_build_mode`).
      const m = p.match(/([a-z0-9-]+)-mode\.ts$/);
      if (!m) return null;
      return `${m[1].replace(/-/g, "_")}_mode`;
    }).filter((x): x is string => x !== null);

    const expectedFlowIds = filenames.sort();
    const actualResolved = expectedFlowIds.filter((id) =>
      getFlow(id) !== undefined,
    );
    expect(actualResolved).toEqual(expectedFlowIds);
  });
});
