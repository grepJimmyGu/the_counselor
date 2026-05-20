# PRD: Builder Chat V1

Status: Planned
Date: 2026-05-20

## Summary

Builder Chat V1 is a guest-accessible contextual drawer on Home, Stock Detail, Templates, and Strategy Results. It helps users draft a strategy, review it in the existing builder preview, run a backtest after explicit confirmation, and iterate after seeing results.

## Entry Points

- Home: start from a standalone Chat Builder section or a plain-language strategy idea.
- Stock Detail: start with the current ticker as default context.
- Templates: start from a selected template or a freeform idea.
- `/workspace`: explain the current result and suggest editable iterations.

## Core Flow

1. User opens Builder Chat.
2. User describes a strategy idea.
3. Chat calls the existing strategy parser endpoint.
4. Chat returns a structured draft and shows assumptions or unsupported-state guidance.
5. User opens the existing builder preview.
6. User reviews the strategy and explicitly clicks Run Backtest.
7. On the result page, chat can explain the result and suggest edits.
8. Suggested edits open the preview and do not mutate or rerun the live result automatically.

## UX Requirements

- Use a right-side contextual drawer on desktop.
- Use a full-width bottom/side sheet behavior on small screens via responsive fixed positioning.
- On Home, expose Chat Builder as a standalone full-width section rather than only as a CTA button.
- Keep the existing Strategy Builder modal as the structured review surface.
- Show clear loading, error, unsupported, and valid-draft states.
- Show a persistent "not financial advice" note.

## Context Inputs

Builder Chat receives:

- `source_page`
- `current_ticker`
- `selected_template_id`
- `current_strategy_json`
- `current_backtest_result`

## Result Iteration

When a result exists, chat can:

- Summarize total return, Sharpe, max drawdown, benchmark comparison, trade count, and warnings.
- Suggest one or more edits such as rebalance change, stop-loss addition, lower position concentration, or cost sensitivity review.
- Apply accepted edits to preview only.

## Assumptions

- V1 does not replace the existing template and wizard paths.
- V1 does not run backtests directly from chat.
- V1 does not save or publish strategies from chat.
- V1 does not require sign-up to draft or preview a paper strategy.
