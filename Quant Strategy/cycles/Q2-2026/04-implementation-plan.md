# Step 4 — Implementation & Refresh Plan

**Purpose**: Turn the 2–3 candidate templates from Step 3 into shippable changes in Livermore, and decide which production templates to retire or refresh.

**DoD**: For each new template, a numbered coding-agent prompt block ready to paste. For each existing template touched, a `mv` from one lifecycle folder to another with updated front-matter.

## 4.1 Implementation plan for new templates

For each candidate, follow the prompt pattern from the Strategy Library v2 doc (the format of "Prompts 1–11" we wrote in the workspace). Each block should include:

- file paths
- additive schema changes (StrategyType literal, optional StrategyRule fields)
- engine branch
- test plan
- acceptance criteria

### New template 1 — `<slug>`

```
<paste coding-agent prompt here>
```

### New template 2 — `<slug>`

```
<paste coding-agent prompt here>
```

## 4.2 Promotions

Templates moving forward in the lifecycle this cycle:

| Slug | From | To | Reason |
|---|---|---|---|
| `...` | candidate | mvp | passed QA checklist |
| `...` | mvp | production | shipped to 100% with no regressions |

For each promotion: `git mv templates/<from>/<slug>.md templates/<to>/<slug>.md` then update front-matter `status`, `last_reviewed_at`, append a Promotion Log entry.

## 4.3 Deprecations

Templates retiring this cycle:

| Slug | Reason | Replacement |
|---|---|---|
| `...` | low usage, no clear thesis | `...` |

For each: `git mv templates/<status>/<slug>.md templates/deprecated/<slug>.md`. Set `deprecation_reason` and `superseded_by` in front-matter. Open a follow-up ticket to hide the template in the gallery and surface a deprecation notice for existing users with saved strategies of that type.

## 4.4 Sync to Livermore

After all `mv` operations are committed:

```bash
# from repo root
python apps/api/app/scripts/sync_template_lifecycle.py \
    --source "/Users/jimmygu/the_counselor/Quant Strategy/templates" \
    --apply

# Idempotent: upserts strategy_template_lifecycle rows.
# Dry-run with --plan to print intended changes without writing.
```

## 4.5 Cycle close checklist

- [ ] All candidate spec files committed to `templates/candidate/`
- [ ] Coding-agent prompts pasted into project tracker (or executed)
- [ ] Promotions and deprecations committed
- [ ] Sync script run successfully
- [ ] Cycle summary written (`cycle-summary.md`)
- [ ] Date set for next cycle review
