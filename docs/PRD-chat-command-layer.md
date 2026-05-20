# PRD: Chat Command Layer

Status: Planned
Date: 2026-05-20

## Summary

Livermore chat should become a typed command layer for product workflows, starting with Strategy Builder only. V1 helps signed-in users turn plain-language strategy ideas into structured paper strategies, review them in the existing builder preview, run a backtest only after explicit confirmation, and understand the result afterward.

The long-term command layer can expand into research, community, and account workflows, but V1 deliberately avoids community mutations, financial advice, trade execution, auto-copying, and unconfirmed publishing.

## Product Direction

- V1: Builder Chat only.
- V2: Add stock and community research summaries.
- V3: Add confirmed low-risk mutations such as watchlist changes, thesis drafts, votes, and strategy saves.
- Never allow live trading, auto-copying, brokerage execution, or personalized financial advice.

## User Promise

Users can say what they want to test, see a structured strategy draft, review the assumptions, and run a historical backtest after confirmation. Chat acts as a guided command surface, not a recommendation engine.

## Capability Boundaries

- Allowed in V1:
  - Draft a strategy from natural language.
  - Open the builder preview with a structured draft.
  - Explain a completed backtest result.
  - Suggest editable strategy changes after a result.
  - Apply suggested edits only to the preview state.
- Not allowed in V1:
  - Watchlist changes.
  - Bull/bear/hold voting.
  - Thesis publishing.
  - Strategy saving or publishing.
  - Community posting.
  - Trade execution or copy trading.

## Safety Language

All chat copy must frame outputs as research tooling:

- Use: "backtest", "paper strategy", "historical result", "candidate", "review", "not financial advice".
- Avoid: "buy signal", "guaranteed", "must buy", "personal recommendation", "safe trade".

## Success Metrics

- Signed-in users who open Builder Chat.
- Prompt-to-preview conversion rate.
- Preview-to-backtest conversion rate.
- Unsupported prompt rate.
- Result explanation usage after a completed backtest.
- Suggested edit acceptance rate.

## Assumptions

- Builder Chat is signed-in only.
- The existing `/workspace` route remains the technical results route.
- Product copy may call `/workspace` "Strategy Results" or "Research Report".
- V1 uses the existing strategy parser API before introducing a generalized backend agent router.
