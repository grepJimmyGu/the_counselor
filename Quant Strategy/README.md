# Quant Strategy — Livermore Library Iteration Workspace

This folder is the source of truth for how the Livermore AI strategy template library is curated, refreshed, and shipped. It runs on a **quarterly cycle** with scheduled-task data collection and a human review gate.

## Folder Map

```
Quant Strategy/
├── README.md                              ← you are here
├── framework/                             ← framework docs, SQL schemas, scheduled-task specs
│   ├── Livermore_Library_Iteration_Framework.html
│   ├── quarterly-runbook.md
│   └── sql-schema.sql
├── knowledge-base/                        ← books, papers, market research (markdown source-of-truth)
│   ├── README.md
│   ├── _kb-entry-template.md
│   ├── books/
│   ├── papers/
│   ├── market-research/
│   └── strategies/
├── cycles/                                ← one folder per quarterly cycle
│   ├── _template/                         ← copy this when starting a new cycle
│   ├── _telemetry-snapshots/              ← monthly CSV drops from scheduled task
│   └── Q2-2026/                           ← current cycle
├── templates/                             ← template library lifecycle
│   ├── _template-spec.md
│   ├── candidate/                         ← proposed, not yet shipped
│   ├── mvp/                               ← shipped behind a flag
│   ├── production/                        ← available to all users
│   └── deprecated/                        ← retired with reason
└── Quant Strategy building/               ← long-form HTML deliverables (Stefanini framework, library v2)
    ├── Quant_Strategy_Framework.html
    └── Livermore_Strategy_Library_v2.html
```

## Quick Links

- **Framework doc**: `framework/Livermore_Library_Iteration_Framework.html` — the 4-step cycle, gates, artifacts.
- **Runbook**: `framework/quarterly-runbook.md` — copy-paste commands & prompts to run a cycle.
- **Current cycle**: `cycles/Q2-2026/` — work in progress for this quarter.
- **Strategy library catalogue**: `Quant Strategy building/Livermore_Strategy_Library_v2.html`.
- **Foundation framework**: `Quant Strategy building/Quant_Strategy_Framework.html`.

## How a Cycle Works

1. **Collect** (week 1) — pull Livermore template usage/feedback into `cycles/<cycle>/01-collect-telemetry.md`.
2. **Knowledge base scan** (week 1–2) — refresh KB with new books/papers/research, log into `02-research-scan.md`.
3. **Propose** (week 2) — draft 2–3 new templates as `templates/candidate/*.md`, with rationale in `03-template-proposals.md`.
4. **Refresh** (week 3–4) — promote/demote templates, queue implementation prompts for Livermore in `04-implementation-plan.md`.

See the framework HTML for full details.
