# Stage 4 — Community + Sharing

**Depends on:** Stage 1 (users + handles).
**Unblocks:** Stage 5 (Creator referral attribution uses share URLs).
**Estimated build:** 2 weeks (10 working days).
**Branch:** `stage-4-community-sharing`

---

## 1. Context

`/community` is one of the three confirmed pillars of Livermore but per `project_log.md` it is "currently thin." The GTM proposal's growth flywheel depends on community: users publish strategies, others discover and clone them, watermarked share URLs drive Scout signups. This stage builds the community pillar out from "thin" to "useful enough to start the flywheel."

The core viral loop:

1. A Strategist runs a backtest with strong results.
2. They publish the strategy to `/community`.
3. The strategy gets a public watermarked URL: `livermore.app/s/<slug>?via=<handle>`.
4. They share it (Twitter, Reddit, Discord, group chat).
5. Anonymous viewer clicks → sees the strategy + result → "Try it yourself, free" CTA → signs up.
6. Attribution recorded for Creator Program (Stage 5).

---

## 2. Scope

### In scope
- `published_strategies` table — published copy of a saved strategy
- Publish / unpublish / edit endpoints
- `/community` feed page — sortable + filterable
- Strategy detail page `/s/[slug]` — public, no auth required
- Follow / unfollow user
- Like (toggle) on a published strategy
- Threaded comments (one level deep)
- Watermarked share URL generation with `?via=<handle>` param
- Verified badge UI (Quant tier OR Creator)
- Basic moderation: report button, hidden state, admin queue
- Search by ticker, by strategy type, by handle (DB `ILIKE` for now — Year 2 could add full-text)

### Out of scope (deferred)
- Comment notifications (Stage 6)
- Forking with iteration history (Year 2)
- Strategy versioning beyond `updated_at` (Year 2)
- Reputation / scoring system (Year 2)
- Mentions / @-tagging in comments (Year 2)
- Full-text search (Year 2)
- Anonymous interactions (must be signed in to like/comment/follow)

---

## 3. Data model

### 3.1 Published strategy

`apps/api/app/models/published_strategy.py`:

```python
class PublishedStrategy(Base):
    """A strategy a user has chosen to publish to /community.
    Decoupled from saved_strategies so users can publish a frozen snapshot
    without subsequent edits to the saved version leaking out."""
    __tablename__ = "published_strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Strategy payload (frozen at publish time)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strategy_json: Mapped[dict] = mapped_column(JSON, nullable=False)  # the full strategy config
    backtest_result_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("backtest_results.id"), nullable=True)
    # Snapshot metrics so we can display without re-running:
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)  # {total_return, sharpe, max_dd, win_rate, ...}
    universe_snapshot: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    benchmark_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # for filtering

    # State
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # moderator-hidden
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # user-deleted (soft)
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    # Counts (denormalized for feed performance)
    follow_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship()
```

### 3.2 Follows

```python
class StrategyFollow(Base):
    __tablename__ = "strategy_follows"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(36), ForeignKey("published_strategies.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class UserFollow(Base):
    __tablename__ = "user_follows"
    follower_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    followee_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
```

### 3.3 Likes + comments

```python
class StrategyLike(Base):
    __tablename__ = "strategy_likes"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(36), ForeignKey("published_strategies.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(36), ForeignKey("published_strategies.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("comments.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

### 3.4 Reports (moderation)

```python
class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)  # "strategy" | "comment" | "user"
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    reporter_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(32), nullable=False)  # "spam", "abuse", "misleading", "other"
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending | resolved | dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
```

### 3.5 Share-URL attribution

Watermark URL `?via=<handle>` parses and writes to an `attribution_visits` table for the Creator Program (Stage 5 will read this):

```python
class AttributionVisit(Base):
    __tablename__ = "attribution_visits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    visitor_session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    referrer_handle: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    referrer_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    landed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    landed_url: Mapped[str] = mapped_column(String(500), nullable=False)
    converted_to_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)  # filled on signup
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_to_paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

Visitor session id is a first-party cookie set on first visit (`livermore_vsid`), 90-day expiry.

---

## 4. API contracts

`apps/api/app/api/routes/community.py`:

### 4.1 Publish a strategy

```
POST /api/community/strategies
  auth: required
  body: {
    saved_strategy_id?: str,  // option A: publish a saved strategy
    backtest_id?: str,        // option B: publish directly from a backtest result
    title: str (3-120),
    description?: str (0-2000),
  }
  resp: 201 PublishedStrategyDetail
```

Slug generation: `slugify(title)` + 6-char nanoid suffix. Collision-safe.

Snapshot the strategy JSON, metrics, universe, benchmark — published strategies never change downstream when the user edits their saved copy.

### 4.2 Feed

```
GET /api/community/strategies
  auth: optional (but anonymous users see view-only)
  query: {
    sort?: "trending" | "newest" | "top_returns" | "top_sharpe" (default trending)
    strategy_type?: str (filter by one of the 6)
    ticker?: str (filter by universe containing ticker)
    handle?: str (filter to one user's strategies)
    locale?: "en" | "zh"
    page?: int (default 1)
    page_size?: int (default 20, max 50)
  }
  resp: { items: PublishedStrategySummary[], total: int, page: int }
```

Trending formula: `(like_count * 3 + comment_count * 2 + follow_count) / (hours_since_publish + 2)^1.5`. Recompute on every fetch (small enough N).

### 4.3 Detail

```
GET /api/community/strategies/{slug}
  auth: optional
  resp: PublishedStrategyDetail | 404 if hidden/deleted
```

Detail payload includes the full strategy JSON, snapshot metrics, author info, follow/like state for current user, and the first 20 comments.

### 4.4 Update / unpublish

```
PATCH /api/community/strategies/{id}
  auth: required (must be owner)
  body: { title?, description? }

DELETE /api/community/strategies/{id}
  auth: required (must be owner)
  // Soft delete: is_deleted=true. Frees the slug for reuse after 30 days.
```

### 4.5 Follow / unfollow strategy

```
POST /api/community/strategies/{id}/follow
DELETE /api/community/strategies/{id}/follow
  auth: required
```

Per the latest proposal revision: **unlimited follows at every tier including Scout.** No quota.

### 4.6 Follow / unfollow user

```
POST /api/community/users/{handle}/follow
DELETE /api/community/users/{handle}/follow
  auth: required
```

### 4.7 Like / unlike

```
POST /api/community/strategies/{id}/like
DELETE /api/community/strategies/{id}/like
  auth: required
```

Increments `like_count` denorm. Rate-limited to 60 likes/min per user.

### 4.8 Comments

```
GET /api/community/strategies/{id}/comments
  query: page, page_size
  resp: ThreadedComments

POST /api/community/strategies/{id}/comments
  auth: required
  body: { body: str (1-2000), parent_id?: str }
  resp: 201 Comment

DELETE /api/community/comments/{id}
  auth: required (must be owner OR admin)
```

### 4.9 Report

```
POST /api/community/report
  auth: required
  body: { target_type, target_id, reason, note? }
  resp: 201
```

### 4.10 Admin moderation

```
GET /api/admin/reports?status=pending
POST /api/admin/reports/{id}/resolve  body: { action: "hide_target" | "dismiss" }
```

Admin auth: simple env-var allowlist (`ADMIN_EMAILS`) — Year 1 simplicity.

### 4.11 Attribution

```
POST /api/community/attribution/track
  auth: optional
  body: { url: str, via: str (handle) }
  resp: 200 (sets cookie if not set, writes row)
```

Called by the frontend on `/s/[slug]` page mount when `?via=` is present.

```
GET /api/me/referrals
  auth: required
  resp: { total_visits, total_signups, total_paid_conversions, recent: [...] }
```

Used by Stage 5's Creator dashboard but the endpoint can live here.

---

## 5. Frontend

### 5.1 Routes added

- `/community` — main feed
- `/community/[strategyType]` — filtered feed for a single strategy type
- `/community/u/[handle]` — user profile + their published strategies
- `/s/[slug]` — public strategy detail page (works without auth)
- `/account/published` — list of my own published strategies

### 5.2 Feed page `/community`

Header:
- Sort tabs: Trending / Newest / Top Returns / Top Sharpe
- Filter pills: All / Equities / Commodities / by strategy type
- Search bar (handle or ticker)

Per card:
- Author avatar + handle + verified badge (if applicable)
- Strategy title + 1-line description
- Top 4 metrics: total return, Sharpe, max drawdown, win rate (color-coded vs benchmark)
- Universe summary (e.g., "5 tickers · equities")
- Like / comment / follow counts
- "View" CTA → `/s/[slug]`

Pagination: infinite scroll via React Query.

### 5.3 Strategy detail `/s/[slug]`

**Anonymous viewer:**
- Strategy preview card with all 8 layers of the strategy framework
- Backtest result chart (equity curve + benchmark)
- Metrics table
- Author info
- Follow + like buttons hidden / disabled with tooltip "Sign in to follow"
- **Persistent CTA at top:** "Try this strategy yourself — free" → `/signup?via=<handle>&template=<slug>`

**Authenticated viewer (Scout+):**
- All anonymous content
- Active follow + like buttons
- Comment thread
- "Clone to my workspace" button → copies strategy JSON to a new saved strategy in their account
- If their universe size or asset class exceeds their tier, Clone shows SoftPaywall.

### 5.4 Publish flow

From `/workspace` (research workspace), after a successful backtest, add a "Publish to community" button (Strategist+ only; Scouts see SoftPaywall — **decision**: should Scouts be able to publish? Per the proposal, "Community — publish" is `Yes` for all tiers. Confirm: **Scouts can publish.** Update SoftPaywall logic to skip.)

Publish modal:
- Pre-filled title (LLM-generated from strategy)
- Description textarea
- Locale toggle
- Public preview (what others will see)
- Publish button

### 5.5 Watermarked share

When user is on `/s/[slug]` (their own strategy or any), the Share button copies:

```
https://livermore.app/s/<slug>?via=<their-handle>
```

Includes Open Graph meta tags for nice link previews (title = strategy title, image = a generated OG image with equity curve + return badge).

OG image generation: `apps/web/src/app/api/og/strategy/[slug]/route.tsx` (Next.js image route using `next/og`).

### 5.6 Verified badge

Show a small badge next to handle:
- **None** for Scout / Strategist
- **Verified** (blue checkmark) for Quant
- **Creator** (gold star) for users in the Creator Program (Stage 5)

`apps/web/src/components/VerifiedBadge.tsx`.

### 5.7 Attribution capture

`apps/web/src/app/s/[slug]/page.tsx` on mount:

```typescript
useEffect(() => {
  const via = searchParams.get("via");
  if (via) {
    fetch("/api/community/attribution/track", {
      method: "POST",
      body: JSON.stringify({ url: window.location.href, via }),
    });
  }
}, [searchParams]);
```

Cookie `livermore_vsid` is set by backend; the signup endpoint (Stage 1) reads it and writes `converted_to_user_id` on the attribution row.

### 5.8 Profile `/community/u/[handle]`

- Avatar, display name, handle, verified badge
- Bio (max 280 chars; editable for own profile in /account)
- Follow / unfollow button
- Stats: published count, follower count, total followers' likes
- Tabbed list of their published strategies

### 5.9 New TypeScript types

Add to `src/lib/contracts.ts`:

```typescript
export interface PublishedStrategySummary {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  author: { id: string; handle: string; display_name: string | null; badge: "verified" | "creator" | null };
  strategy_type: string;
  universe: string[];
  benchmark: string;
  metrics: { total_return: number; sharpe: number; max_drawdown: number; win_rate: number };
  follow_count: number;
  like_count: number;
  comment_count: number;
  liked_by_me: boolean;
  followed_by_me: boolean;
  created_at: string;
}

export interface PublishedStrategyDetail extends PublishedStrategySummary {
  strategy_json: Record<string, unknown>;
  backtest_curve: { date: string; equity: number; benchmark: number }[];
  comments_preview: Comment[];
}

export interface Comment {
  id: string;
  body: string;
  author: { handle: string; display_name: string | null; badge: string | null };
  parent_id: string | null;
  created_at: string;
  is_owner: boolean;
}
```

---

## 6. Acceptance criteria

1. **Publish** — Strategist runs a backtest, clicks Publish, fills form, sees the strategy at `/s/<slug>` within 2 seconds.
2. **Snapshot integrity** — User edits their saved strategy later → published version unchanged.
3. **Public detail** — Anonymous visitor sees full detail page including chart and metrics; CTA visible.
4. **Watermark** — `livermore.app/s/<slug>?via=jimmy` records attribution row with `referrer_handle='jimmy'`.
5. **Conversion attribution** — Anonymous click → signup within 90 days → `attribution_visits.converted_to_user_id` populated; → starts trial → `converted_to_paid_at` populated by webhook handler (Stage 2 extension).
6. **Follow** — User follows strategy; appears in their `/account/following` list.
7. **Unlimited follows** — Scout can follow 1,000 strategies without error.
8. **Like rate limit** — 61st like in a minute returns 429.
9. **Comment threading** — Reply to a comment renders nested one level.
10. **Verified badge** — Quant user's handle shows blue check everywhere their author info renders.
11. **Report** — User reports a strategy; appears in admin queue at `/admin/reports`.
12. **Hide** — Admin hides a strategy; `/s/<slug>` returns 404; feed no longer lists it.
13. **OG image** — `https://livermore.app/api/og/strategy/<slug>` returns a 1200×630 PNG with strategy title and equity curve.
14. **Feed performance** — Trending feed for 1,000 strategies returns in <300ms (p95).

---

## 7. Test plan

### Unit / integration

`apps/api/tests/test_publish.py`:
- `test_publish_creates_snapshot`
- `test_publish_generates_unique_slug`
- `test_edit_saved_strategy_does_not_affect_published`

`apps/api/tests/test_feed.py`:
- `test_trending_sort_recency_decay`
- `test_filter_by_strategy_type`
- `test_filter_by_ticker_in_universe`
- `test_anonymous_can_view_feed`

`apps/api/tests/test_follow_like.py`:
- `test_follow_idempotent`
- `test_unlimited_follows_for_scout`
- `test_like_rate_limit_429`

`apps/api/tests/test_comments.py`:
- `test_comment_one_level_threading`
- `test_delete_comment_soft_deletes`

`apps/api/tests/test_attribution.py`:
- `test_attribution_track_sets_cookie`
- `test_signup_converts_attribution_row`
- `test_paid_signup_converts_to_paid_row`

`apps/api/tests/test_moderation.py`:
- `test_report_creates_pending_row`
- `test_admin_hide_target_404s_detail`

### Frontend tests

Playwright `apps/web/tests/e2e/community.spec.ts`:
- Strategist runs backtest → publishes → strategy visible at `/s/<slug>` → anonymous tab can view → click "Try this strategy yourself" → land on signup with template prefill
- Anonymous → land on `/s/<slug>?via=jimmy` → backend logs attribution → signup with same vsid → attribution row converts

---

## 8. Edge cases & error handling

- **Slug collision** — 6-char nanoid suffix makes collision rate ~1/68B. Retry on rare collision.
- **Deleted user's strategies** — soft-delete user's published strategies on user delete (cascade). Leave in DB for analytics, hide from feed.
- **Spam burst** — rate limit publish to 10/day per user; alert on >50/day.
- **Comment spam** — rate limit 10 comments/min per user; 30/hour.
- **Hidden strategy** — `is_hidden=true` returns 404 for everyone except the owner and admin (owner sees a "Under review" state).
- **OG image cache** — cache OG response 7 days at the CDN; bust on strategy update.
- **Attribution race** — visitor clicks share URL, signs up minutes later. Use `livermore_vsid` cookie as the join key; backend signup endpoint reads cookie, looks up the most-recent un-converted attribution row, fills `converted_to_user_id`.
- **Multiple referrers** — if visitor visits via two different `?via=` URLs before signup, take the **first** attribution that hasn't converted (don't double-count).
- **Self-attribution** — if signup user's handle matches `referrer_handle`, do not record a referral (creator can't refer themselves).
- **PII in strategy descriptions** — basic profanity + PII regex scrub on submit. Year 2: LLM moderation.
- **Comment Markdown** — render safely with `remark-rehype` + `rehype-sanitize`. No HTML pass-through. Links: yes, auto-link; no embeds.

---

## 9. Files to create / modify

**Backend (create):**
- `apps/api/app/models/published_strategy.py`
- `apps/api/app/models/strategy_follow.py`, `user_follow.py`, `strategy_like.py`, `comment.py`, `report.py`, `attribution_visit.py`
- `apps/api/app/schemas/community.py`
- `apps/api/app/services/community_service.py`
- `apps/api/app/services/attribution_service.py`
- `apps/api/app/api/routes/community.py`
- `apps/api/app/api/routes/admin_moderation.py`
- Tests

**Backend (modify):**
- `apps/api/app/api/routes/auth.py` — signup reads `livermore_vsid` cookie, converts attribution
- `apps/api/app/api/routes/stripe_webhook.py` — on `customer.subscription.created`, mark referenced attribution row's `converted_to_paid_at`
- `apps/api/app/main.py` — register new routers

**Frontend (create):**
- `apps/web/src/app/community/page.tsx`
- `apps/web/src/app/community/[strategyType]/page.tsx`
- `apps/web/src/app/community/u/[handle]/page.tsx`
- `apps/web/src/app/s/[slug]/page.tsx`
- `apps/web/src/app/api/og/strategy/[slug]/route.tsx`
- `apps/web/src/app/account/published/page.tsx`
- `apps/web/src/components/StrategyCard.tsx`
- `apps/web/src/components/StrategyDetailHero.tsx`
- `apps/web/src/components/PublishModal.tsx`
- `apps/web/src/components/CommentThread.tsx`
- `apps/web/src/components/ShareButton.tsx`
- `apps/web/src/components/VerifiedBadge.tsx`
- `apps/web/src/lib/useCommunity.ts`

**Frontend (modify):**
- `apps/web/src/components/research-workspace.tsx` — add Publish button after backtest
- `apps/web/src/lib/api.ts` — add ~15 new methods
- `apps/web/src/lib/contracts.ts` — add 6 new types
- `apps/web/src/lib/i18n.ts` — community strings EN + ZH
- Nav: link to `/community`

---

## 10. Definition of done

- All acceptance criteria pass.
- Tests pass (target: ≥30 new tests; existing suite unchanged).
- 10 seed strategies published (by Jimmy as a dogfood pass) so feed isn't empty at launch.
- Share URL with `?via=` works end-to-end in staging.
- Moderation flow tested with one fake report.
- Stage 5 can begin (attribution + verified badge are dependencies).
