/**
 * Test fixture: a 3-step mock flow. Used by PRD-13a's runtime tests AND
 * by the `/flow/mock_flow` dev smoke route. The first real flow ships in
 * PRD-13b (`portfolio_mode`).
 *
 * The fixture intentionally does NOT auto-register itself. The page (or
 * each test's `beforeEach`) calls `registerFlow(MockFlow)`, so the
 * registry's "duplicate id throws" test can use a separate inline
 * definition without colliding with this fixture.
 */

import * as React from "react";
import type { FlowContextBase, FlowDefinition, FlowStepProps } from "../../types";

export interface MockContext extends FlowContextBase {
  /** Test scratch slot — bricks update this; tests assert it survives back/advance. */
  x?: number;
}

function StepShell(props: {
  title: string;
  ctxX: number | undefined;
  children?: React.ReactNode;
}) {
  return (
    <section>
      <h2 data-testid="step-title">{props.title}</h2>
      <span data-testid="ctx-x">{props.ctxX ?? "-"}</span>
      {props.children}
    </section>
  );
}

function MockStep1(props: FlowStepProps<MockContext>) {
  return (
    <StepShell title="Mock Step 1" ctxX={props.context.x}>
      <button
        type="button"
        data-testid="set-x"
        onClick={() => props.updateContext({ x: 1 })}
      >
        set x=1
      </button>
      <button type="button" data-testid="advance" onClick={props.advance}>
        advance
      </button>
      <button type="button" data-testid="abort" onClick={props.abort}>
        abort
      </button>
    </StepShell>
  );
}

function MockStep2(props: FlowStepProps<MockContext>) {
  return (
    <StepShell title="Mock Step 2" ctxX={props.context.x}>
      <button type="button" data-testid="advance" onClick={props.advance}>
        advance
      </button>
      <button type="button" data-testid="back" onClick={props.back}>
        back
      </button>
    </StepShell>
  );
}

function MockStep3(props: FlowStepProps<MockContext>) {
  return (
    <StepShell title="Mock Step 3" ctxX={props.context.x}>
      <button type="button" data-testid="advance" onClick={props.advance}>
        complete
      </button>
      <button type="button" data-testid="back" onClick={props.back}>
        back
      </button>
    </StepShell>
  );
}

const completeHolder: { fn?: (ctx: MockContext) => void } = {};

export function setOnCompleteForTests(fn: (ctx: MockContext) => void): void {
  completeHolder.fn = fn;
}

export function clearOnCompleteForTests(): void {
  completeHolder.fn = undefined;
}

export const MockFlow: FlowDefinition<MockContext> = {
  id: "mock_flow",
  name: "Mock",
  triggers: ["test/start"],
  steps: [
    { id: "step1", brick: MockStep1, next: () => "step2" },
    { id: "step2", brick: MockStep2, next: () => "step3" },
    { id: "step3", brick: MockStep3, next: () => null },
  ],
  initialStepId: "step1",
  onComplete: (ctx) => {
    completeHolder.fn?.(ctx);
  },
};
