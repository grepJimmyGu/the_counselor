/** @vitest-environment jsdom */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

const getSignalPrimitivesMock = vi.fn();
vi.mock("@/lib/api", () => ({
  getSignalPrimitives: () => getSignalPrimitivesMock(),
}));

import { useTemplatePreload } from "../template-preload";
import type { SignalPrimitive } from "@/lib/contracts";

function prim(id: string): SignalPrimitive {
  // The hook only reads `.id` (map key) and stores the whole object as the
  // BuildRule snapshot — a minimal stub is enough for the unit test.
  return { id, family: id } as unknown as SignalPrimitive;
}

// Every primitive best_momentum references must be present in the catalog.
const CATALOG = {
  primitives: [
    "rank_return_6m",
    "time_series_momentum",
    "adx",
    "price_above_ma",
    "sector_rotation_rank",
  ].map(prim),
  categories: [],
  version_hash: "test",
};

function setUrl(search: string) {
  window.history.replaceState({}, "", `/flow/custom_build_mode${search}`);
}

describe("useTemplatePreload", () => {
  beforeEach(() => {
    getSignalPrimitivesMock.mockReset();
    getSignalPrimitivesMock.mockResolvedValue(CATALOG);
    setUrl("");
  });

  it("stays idle and never touches context without a ?template= param", async () => {
    const updateContext = vi.fn();
    const { result } = renderHook(() => useTemplatePreload(updateContext));
    await waitFor(() => expect(result.current.status).toBe("idle"));
    expect(updateContext).not.toHaveBeenCalled();
    expect(getSignalPrimitivesMock).not.toHaveBeenCalled();
  });

  it("hydrates best_momentum's rules + sp500 universe, then strips the param", async () => {
    setUrl("?template=best_momentum&universe=sp500");
    const updateContext = vi.fn();
    const { result } = renderHook(() => useTemplatePreload(updateContext));

    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.templateName).toBe("Best Momentum Pick");
    expect(updateContext).toHaveBeenCalledTimes(1);

    const patch = updateContext.mock.calls[0][0];
    expect(patch.universe_id).toBe("sp500");
    // All 6 registry rules hydrate (every primitive is in the catalog).
    expect(patch.rules).toHaveLength(6);
    // First fold must be null; the rest AND (backend validator contract).
    expect(patch.rules[0].logic_with_prior).toBeNull();
    expect(
      patch.rules.slice(1).every((r: { logic_with_prior: string }) => r.logic_with_prior === "AND"),
    ).toBe(true);
    // Each BuildRule carries the hydrated SignalPrimitive snapshot.
    expect(patch.rules[0].primitive.id).toBe(patch.rules[0].primitive_id);
    expect(window.location.search).toBe("");
  });

  it("drops a rule whose primitive is missing from the catalog (defensive) and re-nulls rule[0]", async () => {
    // Catalog without rank_return_6m (the registry's first rule).
    getSignalPrimitivesMock.mockResolvedValue({
      ...CATALOG,
      primitives: CATALOG.primitives.filter((p) => p.id !== "rank_return_6m"),
    });
    setUrl("?template=best_momentum");
    const updateContext = vi.fn();
    const { result } = renderHook(() => useTemplatePreload(updateContext));

    await waitFor(() => expect(result.current.status).toBe("done"));
    const patch = updateContext.mock.calls[0][0];
    expect(patch.rules).toHaveLength(5); // the dropped one is gone
    // The new surviving first rule must still carry a null fold.
    expect(patch.rules[0].logic_with_prior).toBeNull();
  });

  it("marks not_found for an unknown id and leaves context untouched", async () => {
    setUrl("?template=does_not_exist");
    const updateContext = vi.fn();
    const { result } = renderHook(() => useTemplatePreload(updateContext));
    await waitFor(() => expect(result.current.status).toBe("not_found"));
    expect(updateContext).not.toHaveBeenCalled();
    expect(window.location.search).toBe("");
  });

  it("marks not_found for a sentiment-kind template (routes to /sentiment, not the composer)", async () => {
    setUrl("?template=rising_attention");
    const updateContext = vi.fn();
    const { result } = renderHook(() => useTemplatePreload(updateContext));
    await waitFor(() => expect(result.current.status).toBe("not_found"));
    expect(updateContext).not.toHaveBeenCalled();
  });

  it("surfaces an error if the catalog fetch fails and leaves the param for retry", async () => {
    getSignalPrimitivesMock.mockRejectedValue(new Error("network"));
    setUrl("?template=best_momentum");
    const updateContext = vi.fn();
    const { result } = renderHook(() => useTemplatePreload(updateContext));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(updateContext).not.toHaveBeenCalled();
    expect(window.location.search).toBe("?template=best_momentum");
  });
});
