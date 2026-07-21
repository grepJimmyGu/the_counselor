/** @vitest-environment jsdom */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ProvenanceFooter } from "../provenance-footer";

describe("ProvenanceFooter", () => {
  it("surfaces confidence and grades each source note by tier", () => {
    render(
      <ProvenanceFooter
        confidence="high"
        sourceNotes={["10-K Item 1 Business", "Partner page listing"]}
      />
    );
    // Confidence is surfaced (was previously discarded at the view layer).
    expect(screen.getByText(/high confidence/i)).toBeTruthy();
    // Both source notes render as evidence rows.
    expect(screen.getByText("10-K Item 1 Business")).toBeTruthy();
    expect(screen.getByText("Partner page listing")).toBeTruthy();
    // The filing is graded A; the partner page falls to D (never laundered up).
    expect(screen.getAllByLabelText("Evidence tier A").length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText("Evidence tier D").length).toBeGreaterThan(0);
  });

  it("renders nothing when there is no confidence and no sources", () => {
    const { container } = render(<ProvenanceFooter confidence="" sourceNotes={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
