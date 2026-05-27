import { afterEach, describe, expect, it, vi } from "vitest";
import {
  __resetCopyForTests,
  registerModeCopy,
  useFlowCopy,
} from "../copy";

afterEach(() => {
  __resetCopyForTests();
  vi.restoreAllMocks();
});

describe("useFlowCopy lookup chain", () => {
  it("returns mode-specific value when registered", () => {
    registerModeCopy("mode_a", { foo: "bar" });
    expect(useFlowCopy("mode_a", "foo")).toBe("bar");
  });

  it("falls back to FRAMEWORK_COPY when mode-specific is absent", () => {
    expect(useFlowCopy("mode_a", "backtest_button")).toBe("Run backtest →");
  });

  it("falls back to the raw key when both are absent", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(useFlowCopy("mode_a", "totally_unknown_key")).toBe(
      "totally_unknown_key"
    );
    expect(warn).toHaveBeenCalledOnce();
  });

  it("mode override beats framework default for the same key", () => {
    registerModeCopy("mode_a", { backtest_button: "Run it" });
    expect(useFlowCopy("mode_a", "backtest_button")).toBe("Run it");
    // Other modes still get the framework default.
    expect(useFlowCopy("mode_b", "backtest_button")).toBe("Run backtest →");
  });

  it("registerModeCopy is idempotent — later registrations merge", () => {
    registerModeCopy("mode_a", { foo: "1" });
    registerModeCopy("mode_a", { bar: "2" });
    expect(useFlowCopy("mode_a", "foo")).toBe("1");
    expect(useFlowCopy("mode_a", "bar")).toBe("2");

    registerModeCopy("mode_a", { foo: "1-overridden" });
    expect(useFlowCopy("mode_a", "foo")).toBe("1-overridden");
  });
});
