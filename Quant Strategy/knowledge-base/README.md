# Knowledge Base

Markdown source-of-truth for everything the Livermore strategy library is built on: books, papers, market research, and individual strategy notes. Each file follows a standardized front-matter schema so a script can sync the KB into the Livermore Postgres `knowledge_sources` table.

## Structure

```
knowledge-base/
├── README.md
├── _kb-entry-template.md       ← copy this to start a new entry
├── books/                      ← books (Wiley, academic textbooks, practitioner)
├── papers/                     ← peer-reviewed and working papers (SSRN, arXiv, AQR)
├── market-research/            ← practitioner commentary, broker research, regime notes
└── strategies/                 ← per-strategy deep dives that cross-reference multiple sources
```

## File Naming

- Books: `<author-slug>-<short-title>-<year>.md`  → `stefanini-investment-strategies-2006.md`
- Papers: `<first-author>-<short-title>-<year>.md` → `jegadeesh-titman-momentum-1993.md`
- Market research: `<source-slug>-<topic>-<yyyymm>.md` → `aqr-quant-comeback-202503.md`
- Strategies: `<strategy-slug>.md` → `cross-sectional-momentum.md`

## Front-Matter Schema

Every file starts with a YAML front-matter block. The sync script reads these fields into the `knowledge_sources` table (see `../framework/sql-schema.sql`).

See `_kb-entry-template.md` for the full template.

## Tags Convention

Tags are short kebab-case strings, drawn from:

- **Edge type**: `technical`, `fundamental`, `event-driven`, `sentiment`, `composite-ml`
- **Horizon**: `intraday`, `swing`, `position`, `multi-quarter`
- **Asset class**: `equity`, `etf`, `sector-etf`, `futures`, `options`, `fx`, `multi-asset`
- **Universe**: `single-name`, `pair`, `basket`, `full-universe`
- **Methodology**: `momentum`, `value`, `quality`, `low-vol`, `mean-reversion`, `trend`, `pairs`, `arbitrage`
- **Evidence**: `tier-a`, `tier-b`, `tier-c`

Keep total tags per entry ≤ 8 to keep the index lean.
