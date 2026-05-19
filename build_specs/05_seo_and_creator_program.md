# Stage 5 — SEO + Creator Program

**Depends on:** Stage 2 (billing/subscription state), Stage 4 (attribution + verified badge).
**Unblocks:** Top-of-funnel growth, creator-driven referrals (~30% of new paid signups per the GTM target).
**Estimated build:** 2 weeks (10 working days).
**Branch:** `stage-5-seo-creator`

---

## 1. Context

The GTM proposal's growth strategy rests on two engines:

1. **Organic SEO** — 50 long-tail template landing pages + 2–3 head-to-head comparison pages. Targets 20–30K organic sessions/mo by Month 12 (Composer ≈ 180K, Stock Rover ≈ 280K).
2. **Creator-led referrals** — 50 mid-tier finance creators in Year 1, each driving ~10 paid signups/quarter via watermarked share URLs.

Stage 4 built the watermarked share URL plumbing. Stage 5 adds the SEO pages, the Creator Program application + dashboard + payout flow, and the performance gate that enforces creator behavior.

---

## 2. Scope

### In scope
- 50 SEO template landing pages — dynamically generated from template registry
- 2 comparison pages: `/compare/composer`, `/compare/tradingview-plus`
- `sitemap.xml` and `robots.txt`
- JSON-LD structured data (SoftwareApplication, FAQPage, HowTo)
- Open Graph tags + Twitter cards
- Creator application form `/creators/apply`
- Creator dashboard `/creators/dashboard` (referrals, conversions, revshare estimate)
- Creator approval admin queue
- Revshare calculation: 10% of first-year MRR from referred paid users
- Performance gate enforcement job (drop creators failing minimum thresholds)
- Manual Stripe transfer flow for monthly payouts
- Public `/creators` landing page explaining the program

### Out of scope (deferred)
- Self-serve creator payouts via Stripe Connect (Year 2 — manual transfers work at 50 creators)
- Creator-tier paid product (no separate tier in Year 1; creators get comped Strategist)
- A/B test on landing page copy (Stage 6 will add)
- Creator analytics beyond conversion counts (Year 2)
- Affiliate tracking via third party (Rewardful, FirstPromoter) — building in-house

---

## 3. SEO Landing Pages

### 3.1 Template registry

Reuse the existing template gallery data structure. Each template needs SEO metadata:

```python
# apps/api/app/services/seo_templates.py
TEMPLATE_LANDING_PAGES = [
    {
        "slug": "backtest-200-day-moving-average-nvda",
        "title": "Backtest a 200-day moving average strategy on NVDA — free",
        "h1": "Backtest a 200-day moving average filter on NVDA",
        "template_id": "ma-filter-nvda-200",  # references existing demoStrategies
        "primary_kw": "backtest 200-day moving average",
        "secondary_kw": ["nvda moving average strategy", "moving average backtest free"],
        "intro_md": "...",  # ~150 word intro
        "explanation_md": "...",  # ~300 word strategy explanation
        "results_summary_md": "...",  # ~200 word result interpretation
        "faqs": [
            {"q": "What is a 200-day moving average?", "a": "..."},
            {"q": "Does this strategy work in 2026?", "a": "..."},
            {"q": "Can I run this for free?", "a": "..."},
        ],
        "default_universe": ["NVDA"],
        "default_history_years": 5,
    },
    # ... 49 more
]
```

Create 50 entries covering:
- 10 ticker-specific MA filter pages (NVDA, AAPL, TSLA, SPY, QQQ, GLD, BTC-ETF, MSFT, GOOGL, META)
- 10 ticker-specific RSI mean reversion pages
- 5 momentum rotation pages (sector ETFs, mag-7, commodities, dividend ETFs, international)
- 5 breakout pages (small-cap, large-cap, sector, etc.)
- 5 static allocation pages (60/40, all-weather, permanent portfolio, three-fund, target-date)
- 5 strategy-type explainer pages (no specific ticker): "What is momentum rotation?" etc.
- 10 long-tail head-to-head: "RSI vs MA strategy on NVDA", "Best moving average length for SPY", etc.

This content can be drafted by Claude with the per-template factual constraints baked in (no fabricated returns; reference real Alpha Vantage data).

### 3.2 Dynamic page generation

`apps/web/src/app/templates/[slug]/page.tsx`:

```typescript
import { TEMPLATE_LANDING_PAGES } from "@/lib/seo-templates";

export async function generateStaticParams() {
  return TEMPLATE_LANDING_PAGES.map(t => ({ slug: t.slug }));
}

export async function generateMetadata({ params }: { params: { slug: string } }) {
  const page = TEMPLATE_LANDING_PAGES.find(t => t.slug === params.slug);
  if (!page) return notFound();
  return {
    title: page.title,
    description: page.intro_md.slice(0, 160),
    openGraph: {
      title: page.title,
      description: page.intro_md.slice(0, 160),
      images: [`/api/og/template/${page.slug}`],
    },
    alternates: { canonical: `https://livermore.app/templates/${page.slug}` },
  };
}

export default async function TemplateLandingPage({ params }) {
  const page = TEMPLATE_LANDING_PAGES.find(t => t.slug === params.slug);
  if (!page) return notFound();

  // Server-side: fetch a fresh backtest result for this template
  const result = await api.runBacktestForLanding(page.template_id);

  return (
    <article>
      <StructuredData type="SoftwareApplication" />
      <StructuredData type="HowTo" data={page} />
      <StructuredData type="FAQPage" data={page.faqs} />

      <Hero h1={page.h1} cta="Run this strategy free — no signup needed" />
      <IntroProse content={page.intro_md} />
      <LiveBacktestResult result={result} />
      <Explanation content={page.explanation_md} />
      <ResultsSummary content={page.results_summary_md} />
      <FAQSection faqs={page.faqs} />
      <CTABanner href="/signup?template={page.template_id}" />
      <RelatedTemplates exclude={page.slug} limit={6} />
    </article>
  );
}
```

### 3.3 Live backtest result on landing page

For credibility, the landing page shows a **fresh** backtest result computed on cached price data. Cache the result for 24h to avoid hammering the backtester.

API: `GET /api/backtest/landing/{template_id}` returns the cached or freshly computed result.

### 3.4 Structured data

`apps/web/src/components/StructuredData.tsx` renders JSON-LD for:

- `SoftwareApplication` — overall Livermore app
- `HowTo` — per template page (steps: 1. open template, 2. enter ticker, 3. click run)
- `FAQPage` — the 3 FAQs per page
- `BreadcrumbList` — home / templates / [strategy_type] / [this template]

### 3.5 Sitemap + robots

`apps/web/src/app/sitemap.ts`:

```typescript
import { TEMPLATE_LANDING_PAGES } from "@/lib/seo-templates";

export default async function sitemap() {
  const base = "https://livermore.app";
  return [
    { url: base, lastModified: new Date(), priority: 1.0 },
    { url: `${base}/pricing`, priority: 0.9 },
    { url: `${base}/community`, priority: 0.8 },
    { url: `${base}/creators`, priority: 0.7 },
    { url: `${base}/compare/composer`, priority: 0.7 },
    { url: `${base}/compare/tradingview-plus`, priority: 0.7 },
    ...TEMPLATE_LANDING_PAGES.map(t => ({
      url: `${base}/templates/${t.slug}`,
      lastModified: new Date(),
      priority: 0.6,
    })),
  ];
}
```

`apps/web/public/robots.txt`:

```
User-agent: *
Allow: /
Disallow: /workspace
Disallow: /account
Disallow: /creators/dashboard
Disallow: /admin

Sitemap: https://livermore.app/sitemap.xml
```

### 3.6 Comparison pages

`/compare/composer` and `/compare/tradingview-plus`:

Structured page with:
- H1: "Livermore vs Composer — which is better for backtesting in 2026?"
- Feature comparison table (use the GTM proposal's competitor table as a base)
- Honest pros/cons of each tool
- "Try Livermore free" CTA
- FAQ section
- JSON-LD `ComparisonPage` (custom; not a standard Schema.org type, use `WebPage` with `mainEntity`)

Tone: even-handed. Search engines and users penalize hostile comparison pages. Match competitor strengths honestly; emphasize Livermore's robustness suite + EN/ZH + evaluation dashboards.

---

## 4. Creator Program

### 4.1 Public `/creators` page

Marketing landing. Explain:
- Free Strategist tier while in program
- 10% revshare on first-year MRR of referred paid users
- Performance gate: ≥2 strategies/quarter, ≥10 referrals/quarter
- Verified Creator badge in community
- Apply CTA

### 4.2 Application form `/creators/apply`

```python
class CreatorApplication(Base):
    __tablename__ = "creator_applications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    handle_link: Mapped[str] = mapped_column(String(200))  # link to their content channel
    follower_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_format: Mapped[str] = mapped_column(String(32))  # "tiktok" | "youtube" | "substack" | "twitter" | "other"
    sample_url: Mapped[str] = mapped_column(String(500))
    pitch: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | approved | rejected
    reviewed_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class Creator(Base):
    """Active creators. Created on application approval."""
    __tablename__ = "creators"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("creator_applications.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | suspended | terminated
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payout_email: Mapped[str] = mapped_column(String(320), nullable=False)  # for manual transfers
    payout_country: Mapped[str] = mapped_column(String(2), nullable=False, default="US")
    stripe_connect_account_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

### 4.3 Approval flow

Admin queue `/admin/creators/applications` — list pending, click → review modal → approve/reject.

On approve:
1. Insert `creators` row.
2. Set `users.is_creator=true` and upgrade their `plans.tier='strategist', status='active'`, mark as `comped=true` (new column on `plans`).
3. Email them (Stage 6) with welcome + content kit link.
4. Add Creator badge in community.

### 4.4 Creator dashboard `/creators/dashboard`

Sections:
- **This quarter performance**
  - Strategies published this quarter (count) — must be ≥ 2 by quarter end
  - Referred signups this quarter — must be ≥ 10 by quarter end
  - Performance gate status: green/yellow/red
- **Lifetime stats**
  - Total referrals: visits / signups / paid conversions
  - Revshare earned to date: $X.XX
  - Next payout estimate
- **Content kit**
  - Template share links with `?via=` pre-baked
  - Generated thumbnails / OG images per template
  - Brand assets (logo, color palette, do/don't guide)
- **Payout settings**
  - Payout email
  - Payout country
  - Stripe Connect link (optional, manual transfer fallback)

### 4.5 Revshare calculation

`apps/api/app/services/revshare_service.py`:

```python
def compute_creator_revshare(creator_user_id: str, as_of: date | None = None) -> Decimal:
    """
    Sum 10% of first-year MRR for every paid user converted via this creator.
    First-year = first 12 months from each referred user's `converted_to_paid_at`.
    """
    referrals = db.query(AttributionVisit).filter(
        AttributionVisit.referrer_user_id == creator_user_id,
        AttributionVisit.converted_to_paid_at.is_not(None),
    ).all()

    total = Decimal("0")
    for r in referrals:
        # find their subscription invoices in the first 12 months
        end_date = r.converted_to_paid_at + timedelta(days=365)
        invoices = db.query(StripeInvoice).filter(  # tracked from webhooks
            StripeInvoice.customer_user_id == r.converted_to_user_id,
            StripeInvoice.paid_at.between(r.converted_to_paid_at, end_date),
            StripeInvoice.status == "paid",
        ).all()
        total += sum(Decimal(i.amount_paid_cents) / 100 for i in invoices) * Decimal("0.10")

    return total
```

Stage 2's webhook handler must store paid invoices in a `stripe_invoices` table for this to work. Add that here.

### 4.6 Performance gate enforcement

Quarterly cron, runs first day of new quarter:

```python
@scheduler.scheduled_job("cron", day=1, month="1,4,7,10", hour=2)
def enforce_creator_performance_gate():
    prev_q_start, prev_q_end = previous_quarter_range()
    for creator in db.query(Creator).filter(Creator.status == "active"):
        n_strategies = db.query(PublishedStrategy).filter(
            PublishedStrategy.user_id == creator.user_id,
            PublishedStrategy.created_at.between(prev_q_start, prev_q_end),
        ).count()
        n_referrals = db.query(AttributionVisit).filter(
            AttributionVisit.referrer_user_id == creator.user_id,
            AttributionVisit.converted_at.between(prev_q_start, prev_q_end),
            AttributionVisit.converted_to_paid_at.is_not(None),
        ).count()

        if n_strategies < 2 or n_referrals < 10:
            creator.status = "suspended"
            creator.suspended_at = datetime.utcnow()
            # Revert their plan to paid Strategist (no longer comped)
            plan = db.get(Plan, creator.user_id)
            plan.comped = False
            # Stage 6 will queue an email
            queue_creator_suspension_email(creator.user_id)
    db.commit()
```

Suspension is reversible — admin can manually reactivate within 30 days. After 30 days, status → `terminated` and `users.is_creator=false`.

### 4.7 Payout flow (manual, Year 1)

Monthly cron runs first day of month, generates a CSV of creators owed payouts:

```python
@scheduler.scheduled_job("cron", day=1, hour=6)
def generate_creator_payout_report():
    rows = []
    for creator in db.query(Creator).filter(Creator.status == "active"):
        owed = compute_creator_revshare(creator.user_id)
        already_paid = sum_paid_out_to_creator(creator.user_id)
        balance = owed - already_paid
        if balance > Decimal("25.00"):  # $25 minimum threshold
            rows.append({
                "user_id": creator.user_id,
                "email": creator.payout_email,
                "balance_due": balance,
                "country": creator.payout_country,
            })
    write_csv(rows, f"/var/payouts/{date.today().isoformat()}.csv")
    notify_admin_email(rows)
```

Admin manually processes via Stripe Connect transfer or Wise. After processing, admin uploads a confirmation CSV that updates `creator_payouts` table.

```python
class CreatorPayout(Base):
    __tablename__ = "creator_payouts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    method: Mapped[str] = mapped_column(String(16))  # "stripe_connect" | "wise" | "other"
    external_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

---

## 5. API contracts

### Creator program

```
POST /api/creators/applications
  auth: required
  body: { handle_link, follower_count?, content_format, sample_url, pitch }
  resp: 201 { application_id, status: "pending" }

GET /api/creators/me
  auth: required
  resp: { is_creator: bool, status?, performance_this_quarter?, lifetime_stats?, revshare_owed_cents }

GET /api/admin/creators/applications?status=pending
  auth: admin
  resp: list

POST /api/admin/creators/applications/{id}/decide
  auth: admin
  body: { action: "approve" | "reject", note? }

POST /api/admin/creators/payouts/upload
  auth: admin
  body: csv of payouts paid out
```

### Stripe invoice tracking (extension of Stage 2)

Add `stripe_invoices` table populated by webhook `invoice.payment_succeeded`. Needed by revshare calc.

```python
class StripeInvoice(Base):
    __tablename__ = "stripe_invoices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Stripe invoice id
    customer_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    subscription_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_paid_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(16))  # paid | refunded
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, nullable=False)
```

---

## 6. Acceptance criteria

1. **50 landing pages** — all render at `/templates/<slug>` with title, H1, JSON-LD, FAQ, live backtest result.
2. **Sitemap** — `GET /sitemap.xml` contains all 50 template pages + comparison pages + home + pricing.
3. **OG images** — `/api/og/template/<slug>` returns 1200×630 PNG with strategy preview.
4. **Lighthouse SEO** — score ≥ 95 on a sample landing page (no missing alt text, valid structured data, mobile-friendly, fast).
5. **Comparison page** — `/compare/composer` and `/compare/tradingview-plus` render with comparison table.
6. **Creator application** — POST creates a pending application; admin can approve.
7. **Creator approval** — approves application → user becomes creator, plan comped to Strategist, badge appears in community.
8. **Creator dashboard** — shows referrals, conversions, revshare estimate.
9. **Revshare math** — for a referred user paying $19/mo annual ($228/yr), creator earns $22.80 over first year. Verified by test.
10. **Performance gate** — quarterly job suspends creator below threshold; reactivation possible by admin.
11. **Payout CSV** — monthly cron generates CSV in `/var/payouts/`.
12. **Self-attribution blocked** — creator's signup with their own `?via=` does not create an attribution row.

---

## 7. Test plan

### Unit tests

`apps/api/tests/test_seo_templates.py`:
- `test_all_50_templates_have_required_fields`
- `test_all_slugs_unique`
- `test_landing_endpoint_returns_cached_result_within_24h`

`apps/api/tests/test_creator_application.py`:
- `test_application_creates_pending`
- `test_approval_promotes_user_to_creator`
- `test_approval_sets_comped_strategist`
- `test_rejection_emails_with_note`

`apps/api/tests/test_revshare.py`:
- `test_revshare_10_percent_of_paid_first_year`
- `test_revshare_excludes_refunded_invoices`
- `test_revshare_caps_at_12_months_from_conversion`
- `test_revshare_zero_for_free_signups`

`apps/api/tests/test_performance_gate.py`:
- `test_gate_passes_with_2_strategies_10_referrals`
- `test_gate_fails_with_1_strategy_15_referrals`
- `test_gate_fails_with_3_strategies_5_referrals`
- `test_suspended_creator_loses_comp`

`apps/api/tests/test_payout_report.py`:
- `test_csv_includes_creators_above_threshold`
- `test_csv_excludes_already_paid`

### Frontend tests

Playwright `apps/web/tests/e2e/seo.spec.ts`:
- Visit `/templates/backtest-200-day-moving-average-nvda` as anonymous → page renders → click "Try it yourself" → land on `/signup?template=ma-filter-nvda-200`
- Inspect page source → JSON-LD parsable, FAQPage with 3 questions

Playwright `apps/web/tests/e2e/creator.spec.ts`:
- Sign up → apply for creator program → see "pending" state on `/creators/dashboard`
- (Admin tab) approve application → reload user dashboard → see active state, Strategist comp, badge

---

## 8. Edge cases & error handling

- **Slug clashes between SEO templates and community strategies** — community uses `/s/<slug>`, templates use `/templates/<slug>`. No collision.
- **OG image generation timeout** — fall back to a static brand image.
- **Self-referral abuse** — already covered in Stage 4; double-check here.
- **Revshare on annual prepay** — when a user pays $228 annual, the full $228 lands in the invoice. Revshare is 10% of that ($22.80) attributed at the time of payment, not pro-rated monthly. Document this in the program ToS.
- **Refunds** — if a referred user is refunded, mark `StripeInvoice.status='refunded'` via webhook. Revshare calc excludes refunded invoices. If already paid out to creator, **do not claw back** (Year 1 simplicity); flag for manual review.
- **Performance gate false positives** — if cron runs and a creator was on vacation, allow admin to grant a 1-quarter waiver via `creators.notes`. Job reads notes for `"WAIVER:<quarter>"` and skips.
- **Stage 6 not yet shipped (creator emails)** — log to a queue table; Stage 6 will drain.
- **Stripe Connect onboarding** — optional. Creators can use payout_email + Wise. Stripe Connect adds onboarding friction; defer.
- **Comparison page legal risk** — keep claims factual. No "best" without basis. Reviewed at launch.
- **Template page cache invalidation** — cached backtest can age out of regime; reload weekly via cron.

---

## 9. Files to create / modify

**Backend (create):**
- `apps/api/app/services/seo_templates.py` (the 50 entries — content can be Claude-generated)
- `apps/api/app/api/routes/seo_landing.py`
- `apps/api/app/models/creator_application.py`, `creator.py`, `creator_payout.py`, `stripe_invoice.py`
- `apps/api/app/schemas/creator.py`
- `apps/api/app/services/creator_service.py`
- `apps/api/app/services/revshare_service.py`
- `apps/api/app/api/routes/creators.py`
- `apps/api/app/api/routes/admin_creators.py`
- `apps/api/app/jobs/creator_jobs.py` (performance gate, payout report)
- Tests

**Backend (modify):**
- `apps/api/app/api/routes/stripe_webhook.py` — also write `stripe_invoices` row on `invoice.payment_succeeded`
- `apps/api/app/models/plan.py` (Stage 1's plan model) — add `comped: bool` column
- `apps/api/app/main.py` — register new routers + jobs

**Frontend (create):**
- `apps/web/src/app/templates/[slug]/page.tsx` (dynamic landing pages)
- `apps/web/src/app/compare/[competitor]/page.tsx`
- `apps/web/src/app/creators/page.tsx`
- `apps/web/src/app/creators/apply/page.tsx`
- `apps/web/src/app/creators/dashboard/page.tsx`
- `apps/web/src/app/admin/creators/page.tsx`
- `apps/web/src/app/sitemap.ts`
- `apps/web/src/components/StructuredData.tsx`
- `apps/web/src/components/FAQSection.tsx`
- `apps/web/src/components/ComparisonTable.tsx`
- `apps/web/src/components/CreatorBadge.tsx`
- `apps/web/src/lib/seo-templates.ts`
- `apps/web/public/robots.txt`

**Frontend (modify):**
- `apps/web/src/app/layout.tsx` — global OG / Twitter meta
- `apps/web/src/lib/api.ts` — add ~12 new methods
- Nav: link to Templates, Creator program

---

## 10. Definition of done

- All acceptance criteria pass.
- 50 landing pages live, indexed in Google Search Console submitted.
- 2 comparison pages live.
- Sitemap submitted, robots.txt deployed.
- Creator application live; 5 test applications processed.
- 1 dogfood creator (Jimmy or alias) approved and dashboard verified.
- Revshare math tested with 3 simulated paid conversions.
- Performance gate cron tested by setting current quarter as "previous" in test env.
- Payout CSV generated for sample data.
- Stage 6 can begin.
