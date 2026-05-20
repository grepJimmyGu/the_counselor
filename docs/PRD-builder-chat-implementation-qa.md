# PRD: Builder Chat Implementation and QA Plan

Status: Planned
Date: 2026-05-20

## Summary

Implement Builder Chat V1 as a shared frontend drawer that wraps the existing parser, Strategy Builder modal, and Strategy Results page. No backend schema changes are required for V1.

## Implementation Notes

- Add a reusable `BuilderChatDrawer` component.
- Reuse `parseStrategy()` from `apps/web/src/lib/api.ts`.
- Reuse `StrategyBuilderModal` as the preview/edit/run surface.
- Extend the modal only as needed to accept a prebuilt strategy draft.
- Preserve the existing handoff through `sessionStorage.pendingStrategy` and `/workspace?fromBuilder=true&autorun=true`.
- Gate drawer opening with Auth.js session state.
- Route signed-out users to `/login?callbackUrl=...`.

## Existing Code Touchpoints

- Home page opens chat without ticker context.
- Stock detail page opens chat with `current_ticker`.
- Templates page opens chat with optional `selected_template_id`.
- Strategy Results page opens chat with `current_strategy_json` and `current_backtest_result`.

## QA Scenarios

- Signed-out user clicks Builder Chat from each entry point and lands on sign-in with return intent.
- Signed-in user opens Builder Chat from Home, drafts a strategy, reviews preview, and runs a backtest.
- Signed-in user opens Builder Chat from Stock Detail and receives ticker-aware drafting.
- Signed-in user opens Builder Chat from Templates and receives template-aware drafting.
- Signed-in user opens Builder Chat on Strategy Results and gets an explanation.
- Suggested edits open preview and do not rerun the strategy.
- Unsupported prompts show safe reformulation guidance.
- Chat copy does not contain prohibited investment-advice language.

## Acceptance Criteria

- Builder Chat is available from all four V1 entry points.
- Chat parser output can open the builder preview.
- Result explanation works with the current loaded result.
- Suggested edits are preview-only.
- Signed-out users cannot use the drawer.
- No community or watchlist mutations are introduced.
