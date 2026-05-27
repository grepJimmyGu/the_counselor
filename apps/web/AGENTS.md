<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

> The docs ship inside the hoisted Next.js install. In this workspaces
> monorepo that lives at `node_modules/next/dist/docs/` at the repo
> root, not under `apps/web/node_modules/`. Look at the repo root if the
> path inside `apps/web/` is missing.

<!-- END:nextjs-agent-rules -->

## Flow runtime (`src/lib/flows/`)

PRD-13a infrastructure. Every Sprint 1+ entry mode (Portfolio, Thesis,
Custom Build, …) plugs into this runtime via a declarative
`FlowDefinition`. Triggers from any UI surface call:

```ts
import { startFlow } from "@/lib/flows/runtime";
startFlow("portfolio_mode", {
  initialContext: { fromTrigger: "home/upload_portfolio" },
});
```

Four files own the contract — don't fork their patterns:

- **`types.ts`** — `FlowDefinition`, `FlowStep`, `FlowStepProps`,
  `FlowContextBase`, `FlowEvent`. Generic over `TCtx` so per-mode
  context is type-safe.
- **`runtime.ts`** — `<FlowProvider>`, `<FlowShell />`, `useFlowState()`,
  `startFlow()`. Persists state to `sessionStorage`
  (`livermore_flow_<flowId>`) with a 250 ms debounce; emits `step_idle`
  300 ms after a step mounts when no user interaction.
- **`registry.ts`** — `registerFlow(flow)` / `getFlow(id)`. Modes
  self-register via a side-effect import. Re-registering the same id
  throws.
- **`copy.ts`** — `useFlowCopy(modeId, key)`. **No hardcoded user-facing
  labels in bricks.** Mode-specific override beats `FRAMEWORK_COPY`
  default beats raw-key fallback (dev warning).

The `/flow/[flowId]` route is the universal shell. Adding a mode is
"write a `FlowDefinition`, register it, add a trigger that calls
`startFlow`" — not "fork another wizard."

Tests run via `npm run test` (vitest + jsdom). The test fixture at
`src/lib/flows/__tests__/fixtures/mock-flow.tsx` doubles as the dev
smoke target at `/flow/mock_flow`.
