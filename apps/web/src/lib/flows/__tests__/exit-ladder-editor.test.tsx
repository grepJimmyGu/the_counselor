/**
 * PRD-16c-5 — ExitLadderEditor + BarResolutionPicker tests.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  ExitLadderEditor,
  SPACEX_DEFAULT_LADDER,
  validateExitLadder,
} from "../bricks/exit-ladder-editor";
import { BarResolutionPicker } from "../bricks/bar-resolution-picker";
import type { ExitTier } from "../custom-build-mode-context";

// ── validateExitLadder ──────────────────────────────────────────────────────

describe("validateExitLadder", () => {
  it("accepts empty ladder", () => {
    expect(validateExitLadder([]).ok).toBe(true);
  });

  it("accepts canonical SpaceX ladder", () => {
    expect(validateExitLadder(SPACEX_DEFAULT_LADDER).ok).toBe(true);
  });

  it("rejects ladder without stop tier", () => {
    const tiers: ExitTier[] = [
      { trigger_pct: 0.15, action: "sell_fraction", fraction: 0.33, label: "TP1" },
      { trigger_pct: 0.3, action: "sell_all", label: "TP2" },
    ];
    const result = validateExitLadder(tiers);
    expect(result.ok).toBe(false);
    expect(result.reasons.some((r) => r.includes("stop"))).toBe(true);
  });

  it("rejects non-ascending tiers", () => {
    const tiers: ExitTier[] = [
      { trigger_pct: 0.3, action: "sell_all", label: "TP2" },
      { trigger_pct: -0.1, action: "sell_all", label: "Stop" },
    ];
    const result = validateExitLadder(tiers);
    expect(result.ok).toBe(false);
    expect(result.reasons.some((r) => r.includes("ascending"))).toBe(true);
  });

  it("rejects sell_fraction with fraction <= 0", () => {
    const tiers: ExitTier[] = [
      { trigger_pct: -0.1, action: "sell_all", label: "Stop" },
      { trigger_pct: 0.15, action: "sell_fraction", fraction: 0, label: "TP1" },
    ];
    expect(validateExitLadder(tiers).ok).toBe(false);
  });

  it("rejects sell_fraction with fraction >= 1", () => {
    const tiers: ExitTier[] = [
      { trigger_pct: -0.1, action: "sell_all", label: "Stop" },
      { trigger_pct: 0.15, action: "sell_fraction", fraction: 1, label: "TP1" },
    ];
    expect(validateExitLadder(tiers).ok).toBe(false);
  });

  it("rejects sell_fraction missing fraction", () => {
    const tiers: ExitTier[] = [
      { trigger_pct: -0.1, action: "sell_all", label: "Stop" },
      { trigger_pct: 0.15, action: "sell_fraction", label: "TP1" },
    ];
    expect(validateExitLadder(tiers).ok).toBe(false);
  });
});

// ── ExitLadderEditor rendering ──────────────────────────────────────────────

describe("ExitLadderEditor", () => {
  it("shows 'Use SpaceX defaults' button when empty", () => {
    const onChange = vi.fn();
    render(<ExitLadderEditor value={[]} onChange={onChange} />);
    expect(screen.getByTestId("ladder-use-spacex-defaults")).toBeTruthy();
  });

  it("populates the canonical SpaceX ladder when defaults clicked", () => {
    const onChange = vi.fn();
    render(<ExitLadderEditor value={[]} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("ladder-use-spacex-defaults"));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toEqual(SPACEX_DEFAULT_LADDER);
  });

  it("renders tier rows with editable label/trigger/action", () => {
    const onChange = vi.fn();
    render(
      <ExitLadderEditor value={SPACEX_DEFAULT_LADDER} onChange={onChange} />,
    );
    expect(screen.getByTestId("ladder-tier-0")).toBeTruthy();
    expect(screen.getByTestId("ladder-tier-1")).toBeTruthy();
    expect(screen.getByTestId("ladder-tier-2")).toBeTruthy();
  });

  it("shows fraction input only when action is sell_fraction", () => {
    const onChange = vi.fn();
    render(
      <ExitLadderEditor value={SPACEX_DEFAULT_LADDER} onChange={onChange} />,
    );
    // TP1 is sell_fraction — fraction visible.
    expect(screen.getByTestId("ladder-tier-1-fraction")).toBeTruthy();
    // Stop is sell_all — no fraction input.
    expect(screen.queryByTestId("ladder-tier-0-fraction")).toBeNull();
  });

  it("calls onChange when adding a tier", () => {
    const onChange = vi.fn();
    render(<ExitLadderEditor value={[]} onChange={onChange} />);
    fireEvent.click(screen.getByTestId("ladder-add-tier"));
    expect(onChange).toHaveBeenCalled();
    // First-tier default is a stop.
    const first = onChange.mock.calls[0][0][0];
    expect(first.action).toBe("sell_all");
    expect(first.trigger_pct).toBeLessThan(0);
  });

  it("calls onChange when removing a tier", () => {
    const onChange = vi.fn();
    render(
      <ExitLadderEditor value={SPACEX_DEFAULT_LADDER} onChange={onChange} />,
    );
    fireEvent.click(screen.getByTestId("ladder-tier-1-remove"));
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0][0];
    expect(next.length).toBe(2);
    expect(next.find((t: ExitTier) => t.label === "TP1")).toBeUndefined();
  });

  it("surfaces validation reasons inline", () => {
    const onChange = vi.fn();
    const tiers: ExitTier[] = [
      { trigger_pct: 0.15, action: "sell_fraction", fraction: 0.33, label: "TP1" },
    ];
    render(<ExitLadderEditor value={tiers} onChange={onChange} />);
    expect(screen.getByTestId("ladder-validation-reasons")).toBeTruthy();
  });

  it("respects disabled state — buttons unclickable", () => {
    const onChange = vi.fn();
    render(<ExitLadderEditor value={[]} onChange={onChange} disabled />);
    const addBtn = screen.getByTestId("ladder-add-tier") as HTMLButtonElement;
    expect(addBtn.disabled).toBe(true);
  });
});

// ── BarResolutionPicker ─────────────────────────────────────────────────────

describe("BarResolutionPicker", () => {
  it("renders all 5 resolution options", () => {
    const onChange = vi.fn();
    render(<BarResolutionPicker value="daily" onChange={onChange} />);
    expect(screen.getByTestId("bar-resolution-daily")).toBeTruthy();
    expect(screen.getByTestId("bar-resolution-5min")).toBeTruthy();
    expect(screen.getByTestId("bar-resolution-15min")).toBeTruthy();
    expect(screen.getByTestId("bar-resolution-30min")).toBeTruthy();
    expect(screen.getByTestId("bar-resolution-60min")).toBeTruthy();
  });

  it("marks the active selection with aria-checked", () => {
    const onChange = vi.fn();
    render(<BarResolutionPicker value="15min" onChange={onChange} />);
    expect(
      screen.getByTestId("bar-resolution-15min").getAttribute("aria-checked"),
    ).toBe("true");
    expect(
      screen.getByTestId("bar-resolution-daily").getAttribute("aria-checked"),
    ).toBe("false");
  });

  it("calls onChange when a different option is clicked", () => {
    const onChange = vi.fn();
    render(<BarResolutionPicker value="daily" onChange={onChange} />);
    fireEvent.click(screen.getByTestId("bar-resolution-15min"));
    expect(onChange).toHaveBeenCalledWith("15min");
  });

  it("disables interaction when disabled prop is true", () => {
    const onChange = vi.fn();
    render(
      <BarResolutionPicker value="daily" onChange={onChange} disabled />,
    );
    const btn = screen.getByTestId(
      "bar-resolution-15min",
    ) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
