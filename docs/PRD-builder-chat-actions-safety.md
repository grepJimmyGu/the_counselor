# PRD: Builder Chat Typed Actions and Safety

Status: Planned
Date: 2026-05-20

## Summary

Builder Chat V1 uses typed frontend actions so the UI can safely distinguish text from product operations. Actions are explicit, narrow, and preview-first.

## V1 Typed Actions

```ts
type BuilderChatAction =
  | { type: "draft_strategy"; strategyJson: StrategyJson; message: string }
  | { type: "open_builder_preview"; strategyJson: StrategyJson }
  | { type: "explain_backtest_result"; explanation: string }
  | { type: "suggest_strategy_edit"; patch: Partial<StrategyJson>; rationale: string }
  | { type: "apply_strategy_edit_to_preview"; patch: Partial<StrategyJson> };
```

## Action Rules

- `draft_strategy` can be created from parser output only when a valid `strategy_json` exists.
- `open_builder_preview` opens the existing builder modal preview.
- `explain_backtest_result` is read-only.
- `suggest_strategy_edit` is read-only until the user accepts it.
- `apply_strategy_edit_to_preview` updates preview state only.
- Running a backtest always requires a user click outside chat's text response.

## Risk Levels

- L0: Explanation and navigation. No confirmation required.
- L1: Draft generation. No confirmation required.
- L2: Previewing a draft. User click required.
- L3: Backtest execution. Explicit user click required.
- L4: Save, publish, vote, watchlist, comment. Out of scope for V1.
- L5: Trading, copy trading, money movement. Never allowed.

## Safety Copy

The drawer must display a short compliance note:

> Research tooling only. Outputs are paper strategies and historical backtests, not financial advice.

## Unsupported Requests

If the parser reports an unsupported request, chat should:

- Explain why the request is unsupported in plain language.
- Offer the parser's suggested reformulation when available.
- Avoid inventing unsupported rules.
- Keep the user inside the draft flow instead of running anything.
