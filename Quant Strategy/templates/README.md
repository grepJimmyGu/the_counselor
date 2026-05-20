# Templates — Lifecycle

Each Livermore strategy template has one markdown file at all times. The file lives in one of four subfolders that represent its lifecycle stage:

```
candidate/   → Proposed in a cycle; not yet implemented in Livermore.
mvp/         → Implemented behind a feature flag; available to internal / opt-in users.
production/  → Generally available in the Livermore template gallery.
deprecated/  → Retired; the file is kept for audit. Includes deprecation_reason.
```

## Moving a template between stages

A template's location is just a `mv` operation. Update the front-matter when you move:

- `status:` field
- `last_reviewed_at:`
- `deprecation_reason:` (only when moving to `deprecated/`)
- Append a "Promotion Log" entry at the bottom of the file

When the move is committed, run the KB sync (`framework/quarterly-runbook.md` step 5) to update the Livermore `strategy_template_lifecycle` table.

## File naming

Use the **slug** that matches `livermore_strategy_type` with dashes:
`cross_sectional_momentum` → `cross-sectional-momentum.md`

Schema: see `_template-spec.md`.
