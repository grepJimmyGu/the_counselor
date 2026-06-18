/** @vitest-environment jsdom */

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { OverlayDemo } from "../overlay-demo";
import type { OverlayKind } from "@/lib/contracts";

const KINDS: OverlayKind[] = [
  "defensive",
  "rotation",
  "rebalance",
  "dual_momentum",
  "defense_first",
  "stability_tilt",
];

describe("OverlayDemo", () => {
  it.each(KINDS)("renders a schematic + caption for %s without throwing", (kind) => {
    const { getByTestId, container } = render(<OverlayDemo kind={kind} />);
    expect(getByTestId(`overlay-demo-${kind}`)).toBeTruthy();
    // The schematic SVG renders.
    expect(container.querySelector("svg")).toBeTruthy();
    // A non-empty caption is present.
    expect(getByTestId(`overlay-demo-${kind}`).textContent?.trim().length).toBeGreaterThan(0);
  });
});
