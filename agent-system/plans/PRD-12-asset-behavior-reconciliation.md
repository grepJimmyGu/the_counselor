# PRD-12: Asset Behavior Fingerprint — Reconciliation Memo

**Status**: ✅ Already shipped as **Module 2 (PR #97 → reverted PR #102 → re-applied PR #106)**. **No additional build work** for the asset-behavior fingerprint itself.
**Phase**: Sprint 1 — reconciliation, not a build
**Depends on**: None (memo)
**Blocks**: nothing
**Effort**: 0 build effort. Reading this memo: 5 minutes.
**Owner**: PM / docs

---

## TL;DR

The "asset behavior fingerprint service" originally scoped as PRD-12 in the Sprint 1 plan was already built and merged as **Module 2** in PR #97 (and re-applied in PR #106 after a brief revert via PR #102). This memo exists to:

1. Document the canonical name (Module 2 = Asset Behavior Fingerprint = the API + helper PRD-12 was going to scope).
2. Tell PRD-13b and PRD-14 authors **exactly what to consume** so they don't rebuild it.
3. Flag the **one open administrative item** — confirming PR #106 has actually landed on `main` (commit `ab255e5` appears on feature branches but the working tree on `main` doesn't include the files yet; verify before consumers depend on it).

**No code work is in this PRD.** PRD-13b and PRD-14 reference this memo for the contract they should call against.

---

## What Module 2 already ships

PR #97 (`feat(strategy-picker): Module 2 — Asset Behavior Fingerprint`), re-applied in PR #106 after PR #102 reverted it.

### Backend

| File | What it does |
|---|---|
| `apps/api/app/services/asset_behavior_service.py` | Pure computation. Takes a pandas Series of daily closes; returns an `AssetBehaviorFingerprint` dataclass with all 10 spec fields. Empty / tiny inputs return `None` (metric) or `"insufficient"` (quality) rather than crashing. |
| `apps/api/app/schemas/asset_behavior.py` | Pydantic response model — `AssetBehaviorFingerprintResponse`. |
| `apps/api/app/api/routes/asset_behavior.py` | `GET /api/assets/{symbol}/behavior` — pulls ~6 years of daily bars via `PriceDataService`, calls the computation service, returns the response. No auth gate (matches `/api/data/daily/{symbol}` pattern). |
| `apps/api/tests/test_asset_behavior.py` | 31 tests covering all 6 required spec areas + end-to-end synthetic series. Suite went from 727 → 758 passing on PR #97 merge. |

### Frontend

| File | What it does |
|---|---|
| `apps/web/src/lib/contracts.ts` | TypeScript types — `AssetBehaviorFingerprint`, `AssetType`, `CurrentRegime`, `DataQuality`. 1-to-1 with backend Pydantic schema. |
| `apps/web/src/lib/api.ts` | `getAssetBehavior(symbol: string): Promise<AssetBehaviorFingerprint>` helper. ~9 lines. |
| `apps/web/src/components/strategy-picker/AssetBehaviorFingerprintCard.tsx` | Self-fetching React component. Pass `symbol={...}` and it loads; pass `fingerprint={preFetched}` to skip the fetch (SSR or parent-managed loading). Renders symbol + asset type + regime badge + data-quality badge in the header, two-column metrics grid, implication footer with the standard "not investment advice" disclaimer. Plain-English labels throughout; null metrics render as "Not enough data" rather than crashing. Insufficient-data quality triggers an amber warning banner. |

### The 10 fingerprint fields

`AssetBehaviorFingerprint` carries:

1. **`asset_type`** — broad ETF / sector ETF / commodity ETF / single stock (ticker-set lookup; single_stock fallback)
2. **`trending_pct`** — % of 200-day windows where price > MA AND MA slope > 0
3. **`mean_reverting_pct`** — % of |z|>1.5 extremes (60-day rolling z-score) that revert within 10 trading days. `null` when <5 extremes.
4. **`realized_vol_1y`** — annualized stdev of daily returns, 1-year window
5. **`realized_vol_5y`** — annualized stdev, 5-year window
6. **`max_drawdown_5y`** — `min((p − cummax) / cummax)` over the last 5 years
7. **`current_regime`** — rule-based: `volatile` > `trending` > `range_bound` > `mixed`
8. **`data_quality`** — bucketed by row count (`3y+` / `1-3y` / `<1y` / `insufficient`)
9. **`strategy_implication`** — short plain-English string. **No buy/sell verbs.** This is the field that surfaces to retail users as "what does this mean for me?"
10. **`symbol`** — echoed back from the request

---

## How PRD-13b consumes Module 2

PRD-13b's `PortfolioDiagnosisService.diagnose(holdings)` does NOT rebuild the per-symbol fingerprint. It **calls Module 2 once per holding** and aggregates.

```python
# apps/api/app/services/portfolio_diagnosis_service.py (PRD-13b)
from app.services.asset_behavior_service import compute_asset_behavior_fingerprint
from app.services.price_data_service import PriceDataService

class PortfolioDiagnosisService:
    async def diagnose(
        self, db: Session, holdings: list[Holding]
    ) -> PortfolioDiagnosis:
        # Per-holding fingerprints
        fingerprints = await asyncio.gather(*[
            self._fingerprint_for(db, h.ticker) for h in holdings
        ])

        # Aggregate
        return PortfolioDiagnosis(
            holdings=[
                HoldingDiagnosis(ticker=h.ticker, weight=h.weight, fingerprint=fp)
                for h, fp in zip(holdings, fingerprints)
            ],
            weighted_trending_pct=_weighted_avg(holdings, fingerprints, "trending_pct"),
            weighted_mean_reverting_pct=_weighted_avg(holdings, fingerprints, "mean_reverting_pct"),
            sector_concentration=_compute_sector_concentration(fingerprints),
            # ... etc.
        )

    async def _fingerprint_for(self, db: Session, symbol: str) -> AssetBehaviorFingerprint:
        prices = await price_data_service.get_close_series(db, symbol, lookback_years=6)
        return compute_asset_behavior_fingerprint(symbol, prices)
```

Note: PRD-13b's diagnosis service is the **multi-ticker aggregator**, not a re-implementation of the per-ticker fingerprint. Module 2 owns the per-ticker computation.

Frontend equivalent: PRD-13b's `<PortfolioDiagnosis>` brick renders an aggregated view; for the per-holding drill-down (clicking a row), reuse the existing `<AssetBehaviorFingerprintCard symbol={ticker} />` from Module 2.

---

## How PRD-14 consumes Module 2

PRD-14 (Stock-page "Apply a strategy" button) surfaces the existing `<AssetBehaviorFingerprintCard>` directly on the stock detail page.

```tsx
// apps/web/src/app/stocks/[ticker]/page.tsx (modified by PRD-14)
import { AssetBehaviorFingerprintCard } from "@/components/strategy-picker/AssetBehaviorFingerprintCard";
import { getAssetBehavior } from "@/lib/api";

export default async function StockPage({ params }) {
  const fingerprint = await getAssetBehavior(params.ticker); // server-side
  return (
    <>
      {/* ... existing stock-page sections ... */}
      <AssetBehaviorFingerprintCard symbol={params.ticker} fingerprint={fingerprint} />
      <ApplyStrategyButton ticker={params.ticker} />
    </>
  );
}
```

PRD-14 does NOT add a new endpoint, a new component, or new types — only places the existing card on the stock page and wires the new "Apply a strategy" button.

---

## The one open administrative item

⚠️ **Verify before PRD-13b or PRD-14 starts**: at the time this memo was drafted, the working tree on `main` (HEAD `4d5ace3`) does not contain the Module 2 files. `git branch -a --contains ab255e5` shows the commit on feature branches (`claude/feat/fred-cfnai-hy-oas-real-signals`, etc.) but the local `main` checkout doesn't have them.

This could mean:
- (a) Local `main` is behind; `git pull` will bring it in. Most likely.
- (b) PR #106 didn't actually land cleanly on `main` and another revert is needed. Less likely but check.

**Action before PRD-13b or PRD-14 starts**:

```bash
cd /Users/jimmygu/the_counselor
git fetch origin
git checkout main
git pull origin main
ls apps/api/app/services/asset_behavior_service.py \
   apps/api/app/api/routes/asset_behavior.py \
   apps/api/app/schemas/asset_behavior.py \
   apps/web/src/components/strategy-picker/AssetBehaviorFingerprintCard.tsx
# All four files should exist. If not, check why PR #106 isn't on main.
```

If the files are missing after `git pull`, **stop** and escalate to `claude-main` before starting PRD-13b or PRD-14 — they'll fail without Module 2.

---

## Why this is a memo and not a build PRD

The Sprint 1 plan in `HANDOFF-livermore-product-flow-v2.md` originally listed PRD-12 as "Asset behavior fingerprint service — ~3 hours." That ~3-hour scope was correct in absolute terms, but the work was already done outside the Sprint 1 packet as Module 2 (PR #97 + #106). Writing a build PRD for work that's already merged would be duplicative and risk an agent rebuilding the same service.

Reconciliation memos like this are how we keep the PRD packet honest: when work shows up out of the Sprint planning order, it gets documented so dependent PRDs know what to call.

---

## Brick inventory contribution

The Module 2 bricks (already shipped, not added by this memo):

| Brick | Location | Used by |
|---|---|---|
| `compute_asset_behavior_fingerprint(symbol, prices)` | `asset_behavior_service.py` | PRD-13b's portfolio diagnosis (called per holding) |
| `GET /api/assets/{symbol}/behavior` | `routes/asset_behavior.py` | PRD-14 (stock page); PRD-13b indirectly via the service |
| `getAssetBehavior(symbol)` helper | `apps/web/src/lib/api.ts` | PRD-14 (server-side fetch); future Mode 1 picker |
| `<AssetBehaviorFingerprintCard>` component | `apps/web/src/components/strategy-picker/` | PRD-14 (stock page); future Mode 1 picker; PRD-13b's per-holding drill-down |

The HANDOFF doc §6 (Brick inventory) should be updated to mark these as ✅ shipped under "Module 2 (PR #97/#106)" — see follow-up action below.

---

## Follow-up actions

- [ ] Confirm PR #106 (`ab255e5`) is on `main` (see "open administrative item" above).
- [ ] Update HANDOFF §6 Brick inventory: mark Module 2 bricks as ✅ with PR #97/#106 attribution (instead of PRD-12 ⏳).
- [ ] Update HANDOFF §4 PRD table: change PRD-12 row from "Draft pending" to "Reconciliation memo only — Module 2 already shipped (PR #97/#106)."
- [ ] Inform PRD-13b owner that they consume Module 2; do not rebuild.
- [ ] Inform PRD-14 owner that they compose `<AssetBehaviorFingerprintCard>`; do not write a new one.

---

## Cross-references

- Source PRs: [#97](https://github.com/grepJimmyGu/the_counselor/pull/97) (original), [#102](https://github.com/grepJimmyGu/the_counselor/pull/102) (revert), [#106](https://github.com/grepJimmyGu/the_counselor/pull/106) (re-apply, commit `ab255e5`)
- Consumer PRDs: PRD-13b (portfolio diagnosis composes it), PRD-14 (stock page surfaces it), future Mode 1 picker refactor
- Master handoff: `agent-system/plans/HANDOFF-livermore-product-flow-v2.md`
- Source spec: `/Quant Strategy/framework/livermore_product_flow_v2.html` §2 Mode 1 (where the behavior fingerprint surfaces at picker time)

---

*Memo drafted 2026-05-26. This file replaces what was previously planned as PRD-12-asset-behavior-fingerprint.md — the work was already done as Module 2.*
