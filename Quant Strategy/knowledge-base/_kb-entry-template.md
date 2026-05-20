---
# Required
source_type: book | paper | market-research | strategy
title: ""
authors: []
year: 0
url: ""
file_path: ""                   # path to PDF/source if local, relative to /Quant Strategy/

# Categorization
tags: []                        # see ../README.md for tag vocabulary
evidence_tier: A | B | C        # see framework doc; default B for newly-added until reviewed
asset_classes: [equity]         # equity | etf | futures | options | fx | multi-asset

# Strategy linkage — these slugs match templates/<lifecycle>/*.md filenames
strategies_referenced: []       # e.g. ["cross-sectional-momentum", "low-volatility"]

# Lifecycle
added_at: YYYY-MM-DD
last_reviewed_at: YYYY-MM-DD
reviewed_by: ""
superseded_by: ""               # filename of newer source if applicable
status: active | archived
---

# {{Title}}

## TL;DR
*One paragraph: what does this source claim, why does it matter to Livermore?*

## Source Summary
*2–4 paragraphs distilling the source's argument or findings.*

## Strategies Extracted

For each distinct strategy the source describes, fill in the structured block below.
Use the same shape as `templates/_template-spec.md` so the sync script can lift it directly.

### Strategy 1: {{name}}

- **Thesis**: ...
- **Universe**: ...
- **Signal**: ...
- **Rebalance**: ...
- **Default parameters**: ...
- **Reported metrics**: ...
- **Caveats / failure modes**: ...

## Quotes & Numbers Worth Citing

> "{{quote 1}}" — p. X

- Reported Sharpe: ...
- Sample window: ...
- Universe size: ...

## Cross-References

- Related KB entries: ...
- Templates in Livermore library that draw on this: ...

## Reviewer Notes

*Date-stamped notes from each quarterly review pass. Append, don't rewrite.*

- **YYYY-MM-DD** — initial entry.
