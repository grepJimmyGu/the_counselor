import { afterEach, describe, expect, it } from "vitest";
import {
  FLOW_REGISTRY,
  __resetRegistryForTests,
  getFlow,
  listFlows,
  registerFlow,
} from "../registry";
import type { FlowDefinition } from "../types";

function makeFlow(id: string): FlowDefinition {
  return {
    id,
    name: id,
    triggers: ["test/start"],
    steps: [
      {
        id: "only",
        brick: () => null,
        next: () => null,
      },
    ],
    initialStepId: "only",
    onComplete: () => {},
  };
}

afterEach(() => {
  __resetRegistryForTests();
});

describe("flow registry", () => {
  it("registerFlow adds to the registry", () => {
    const flow = makeFlow("alpha");
    registerFlow(flow);
    expect(getFlow("alpha")).toBe(flow);
  });

  it("re-registering the same id throws", () => {
    registerFlow(makeFlow("alpha"));
    expect(() => registerFlow(makeFlow("alpha"))).toThrow(/already registered/i);
  });

  it("getFlow returns undefined for unknown ids", () => {
    expect(getFlow("does_not_exist")).toBeUndefined();
  });

  it("listFlows enumerates registered flows", () => {
    registerFlow(makeFlow("alpha"));
    registerFlow(makeFlow("beta"));
    const ids = listFlows().map((f) => f.id);
    expect(ids).toContain("alpha");
    expect(ids).toContain("beta");
    expect(ids).toHaveLength(2);
  });

  it("FLOW_REGISTRY exposes the same surface", () => {
    FLOW_REGISTRY.register(makeFlow("gamma"));
    expect(FLOW_REGISTRY.get("gamma")?.id).toBe("gamma");
    expect(FLOW_REGISTRY.list().map((f) => f.id)).toEqual(["gamma"]);
  });
});
