# Stage 1 — Identity + Entitlements

**Depends on:** Nothing. This is the prerequisite for every other stage.
**Unblocks:** Stages 2, 3, 4, 5, 6.
**Estimated build:** 2 weeks (10 working days).
**Branch:** `stage-1-identity-entitlements`

---

## 1. Context

Livermore today has no user identity (per `project_log.md`: "no auth/user concept → frontend passes iteration_count to sandbox reviewer"). Every existing endpoint is anonymous. The tiered GTM proposal requires:

1. **User accounts** — so we can attach a plan, count usage, and personalize.
2. **Plan record** — Scout / Strategist / Quant.
3. **Entitlements engine** — a single function that, given a user, returns the capability caps used by every gating decision downstream.
4. **Usage metering** — count `backtest_runs_this_month` per user, reset monthly.

This stage adds those four primitives. It does **not** apply gating yet (that's Stage 3) and does **not** add billing yet (that's Stage 2). The goal is: every user request after this stage carries an identity + a plan + a running usage count, and any downstream code can call `get_entitlements(user)` to know what they're allowed to do.

---

## 2. Scope

### In scope
- NextAuth.js v5 in `apps/web` with email/password + Google OAuth providers
- User table + Plan table + Usage table in PostgreSQL
- Anonymous → authenticated migration path (existing backtest records get a synthetic `legacy` user)
- Entitlements resolver service in `apps/api`
- Monthly usage reset (cron-like)
- Session propagation from Next.js to FastAPI (JWT-based)
- "My Account" basics page (email, plan, usage)
- Profile fields: handle, display name, locale, avatar URL

### Out of scope (deferred)
- Stripe checkout (Stage 2)
- Actually blocking requests when limits are hit (Stage 3)
- Password reset email (deferred — use magic link in Stage 6 alongside Resend)
- Team accounts, SSO (Year 2)

---

## 3. Data model

### 3.1 New SQLAlchemy models

Create `apps/api/app/models/user.py`:

```python
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, DateTime, Date, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID v4
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    handle: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # bcrypt; null if OAuth-only
    oauth_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # "google", null if password
    oauth_subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped["Plan"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    usage: Mapped["MonthlyUsage"] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("oauth_provider", "oauth_subject", name="uq_users_oauth"),
    )


class Plan(Base):
    """One row per user. tier ∈ {'scout', 'strategist', 'quant'}.
    For Scouts the row exists with tier='scout' from signup; no Stripe references yet.
    Stage 2 will populate stripe_customer_id, stripe_subscription_id, status, current_period_end, trial_end."""
    __tablename__ = "plans"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tier: Mapped[str] = mapped_column(String(16), default="scout", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)  # active | trialing | past_due | canceled
    billing_cycle: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # monthly | annual

    # Stripe — filled by Stage 2
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    trial_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="plan")


class MonthlyUsage(Base):
    """One row per (user, year_month). Incremented on each metered action.
    backtest_runs is the primary counter; other counters added later (publishes, etc.)."""
    __tablename__ = "monthly_usage"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    period_start: Mapped[date] = mapped_column(Date, primary_key=True)  # first day of month UTC
    backtest_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    robustness_runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chat_prompts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saved_strategies: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # cumulative count, not monthly

    user: Mapped["User"] = relationship(back_populates="usage")

    __table_args__ = (
        Index("ix_monthly_usage_period", "period_start"),
    )
```

### 3.2 Add `user_id` to existing tables

These tables exist today and have no `user_id`. Add a nullable column. Backfill anonymous rows to a single synthetic user (`id='legacy-anon-0000'`, email `legacy@livermore.app`, plan `scout`, marked `is_legacy=true`).

Tables to migrate (confirm against current schema):

- `backtest_results` — add `user_id` nullable, FK to users, indexed
- `robustness_jobs` — add `user_id` nullable, FK to users, indexed
- `saved_strategies` (if exists) — add `user_id` non-null after backfill

Migration file: `apps/api/app/migrations/0001_add_users_and_plan.py` (Alembic) or extend `run_startup_migrations()` if not using Alembic. Project log indicates startup migrations are already used (`run_startup_migrations()`); extend that path.

### 3.3 Pydantic schemas

Create `apps/api/app/schemas/identity.py`:

```python
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field


class UserPublic(BaseModel):
    id: str
    handle: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]
    locale: str


class UserMe(UserPublic):
    email: EmailStr
    created_at: datetime
    plan: "PlanPublic"
    usage: "UsageThisMonth"


class PlanPublic(BaseModel):
    tier: Literal["scout", "strategist", "quant"]
    status: Literal["active", "trialing", "past_due", "canceled"]
    billing_cycle: Optional[Literal["monthly", "annual"]] = None
    trial_end: Optional[datetime] = None
    current_period_end: Optional[datetime] = None


class UsageThisMonth(BaseModel):
    period_start: str  # ISO date
    backtest_runs: int
    robustness_runs: int
    saved_strategies_count: int


class Entitlements(BaseModel):
    """Returned by /api/me/entitlements. Used by frontend to render UI states."""
    tier: Literal["scout", "strategist", "quant"]
    status: Literal["active", "trialing", "past_due", "canceled"]
    backtest_runs_remaining: Optional[int]  # null = unlimited
    universe_size_max: int
    history_window_years: int
    asset_classes: list[str]  # ["equities"] | ["equities", "commodities"] | ["equities", "commodities", "a_shares"]
    robustness_tests: list[str]  # ["param_sensitivity", "benchmark"] | full list | []
    market_pulse_ticker_scope: Literal["top_250", "all_us", "all_us_plus_alerts"]
    business_model_section: Literal["full", "full_plus_supply_chain"]
    commodity_framework: bool
    saved_strategies_max: int
    api_access: bool
    community_badge: Optional[Literal["verified", "creator"]] = None
```

### 3.4 Entitlement resolver

Create `apps/api/app/services/entitlements.py`. Single source of truth — every gating call goes through this.

```python
from app.models.user import User, Plan, MonthlyUsage
from app.schemas.identity import Entitlements
from datetime import date

TIER_CAPS = {
    "scout": {
        "backtest_runs_per_month": 5,
        "universe_size_max": 5,
        "history_window_years": 5,
        "asset_classes": ["equities"],
        "robustness_tests": [],
        "market_pulse_ticker_scope": "top_250",
        "business_model_section": "full",
        "commodity_framework": False,
        "saved_strategies_max": 3,
        "api_access": False,
    },
    "strategist": {
        "backtest_runs_per_month": None,  # unlimited
        "universe_size_max": 25,
        "history_window_years": 10,
        "asset_classes": ["equities", "commodities"],
        "robustness_tests": ["param_sensitivity", "benchmark"],
        "market_pulse_ticker_scope": "all_us",
        "business_model_section": "full",
        "commodity_framework": True,
        "saved_strategies_max": 25,
        "api_access": False,
    },
    "quant": {
        "backtest_runs_per_month": None,
        "universe_size_max": 100,
        "history_window_years": 20,
        "asset_classes": ["equities", "commodities", "a_shares"],
        "robustness_tests": ["param_sensitivity", "sub_period", "transaction_cost", "benchmark", "peer_ticker"],
        "market_pulse_ticker_scope": "all_us_plus_alerts",
        "business_model_section": "full_plus_supply_chain",
        "commodity_framework": True,
        "saved_strategies_max": 10_000,  # effectively unlimited
        "api_access": True,
    },
}


def get_entitlements(user: User, usage: MonthlyUsage | None) -> Entitlements:
    tier = user.plan.tier
    caps = TIER_CAPS[tier]
    runs_used = usage.backtest_runs if usage else 0
    runs_per_month = caps["backtest_runs_per_month"]
    runs_remaining = None if runs_per_month is None else max(0, runs_per_month - runs_used)

    return Entitlements(
        tier=tier,
        status=user.plan.status,
        backtest_runs_remaining=runs_remaining,
        universe_size_max=caps["universe_size_max"],
        history_window_years=caps["history_window_years"],
        asset_classes=caps["asset_classes"],
        robustness_tests=caps["robustness_tests"],
        market_pulse_ticker_scope=caps["market_pulse_ticker_scope"],
        business_model_section=caps["business_model_section"],
        commodity_framework=caps["commodity_framework"],
        saved_strategies_max=caps["saved_strategies_max"],
        api_access=caps["api_access"],
        community_badge=("creator" if user.plan.tier == "quant" and getattr(user, "is_creator", False) else
                         "verified" if user.plan.tier == "quant" else None),
    )


def get_or_create_current_usage(db, user_id: str) -> MonthlyUsage:
    today = date.today()
    period_start = today.replace(day=1)
    row = db.get(MonthlyUsage, (user_id, period_start))
    if row is None:
        row = MonthlyUsage(user_id=user_id, period_start=period_start)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def increment_backtest_runs(db, user_id: str) -> int:
    usage = get_or_create_current_usage(db, user_id)
    usage.backtest_runs += 1
    db.commit()
    return usage.backtest_runs
```

---

## 4. API contracts

All new endpoints live under `apps/api/app/api/routes/auth.py` and `me.py`.

### 4.1 NextAuth-compatible callback

NextAuth handles signup/login on the frontend. The backend exposes a minimal callback for OAuth and a password-hash check endpoint.

```
POST /api/auth/password/login
  body:  {"email": str, "password": str}
  resp:  {"user": UserPublic, "session_token": str} | 401

POST /api/auth/password/signup
  body:  {"email": str, "password": str, "display_name": str?, "locale": "en"|"zh"?}
  resp:  201 {"user": UserPublic, "session_token": str} | 409 if email taken

POST /api/auth/oauth/google/callback
  body:  {"id_token": str}  # validated server-side via Google certs
  resp:  {"user": UserPublic, "session_token": str, "is_new": bool}
```

Session token is a short JWT signed with `NEXTAUTH_SECRET`, payload `{sub: user_id, exp: now+30d, tier: <plan.tier>}`. Frontend stores it as a secure httpOnly cookie via NextAuth.

### 4.2 Identity routes

```
GET /api/me
  auth: required
  resp: UserMe  (includes plan + this-month usage)

GET /api/me/entitlements
  auth: required
  resp: Entitlements  (always fresh from DB)

PATCH /api/me
  auth: required
  body: {"handle"?: str, "display_name"?: str, "locale"?: "en"|"zh", "avatar_url"?: str}
  resp: UserPublic
  errors: 409 if handle taken
```

Handle constraints: 3–32 chars, `^[a-z0-9_]+$`, reserved list (`admin`, `livermore`, `claude`, etc.).

### 4.3 Anonymous compatibility

For Stage 1, **endpoints stay anonymous-by-default**. Stage 3 will start requiring auth on metered endpoints. To make this work:

- Add a FastAPI dependency `get_current_user_or_anonymous(request)` that returns either the authenticated `User` or a synthetic `User(id='legacy-anon-0000', tier='scout')` if no session.
- Every existing endpoint accepts this dependency now; nothing changes in behavior. Stage 3 will swap it for `get_current_user` (strict) on metered paths.

This lets Stage 1 ship without breaking the existing product.

---

## 5. Frontend (Next.js)

### 5.1 NextAuth setup

`apps/web/src/app/api/auth/[...nextauth]/route.ts` — NextAuth v5 handler with two providers:

```typescript
import NextAuth from "next-auth";
import GoogleProvider from "next-auth/providers/google";
import CredentialsProvider from "next-auth/providers/credentials";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    CredentialsProvider({
      name: "Email",
      credentials: { email: {}, password: {} },
      async authorize(creds) {
        const r = await fetch(`${process.env.API_BASE_URL}/api/auth/password/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(creds),
        });
        if (!r.ok) return null;
        const data = await r.json();
        return { id: data.user.id, email: creds.email, name: data.user.display_name, image: data.user.avatar_url, sessionToken: data.session_token };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) token.sessionToken = (user as any).sessionToken;
      return token;
    },
    async session({ session, token }) {
      (session as any).sessionToken = token.sessionToken;
      return session;
    },
  },
  pages: { signIn: "/login" },
});
```

### 5.2 New pages

- `src/app/login/page.tsx` — email/password form + "Continue with Google" button
- `src/app/signup/page.tsx` — same, with display name + locale picker
- `src/app/account/page.tsx` — current plan, this-month usage, edit handle/display name (Stage 2 will add billing portal link)

### 5.3 SessionProvider wrap

In `src/app/layout.tsx`, wrap children with `<SessionProvider>`. Also expose `useEntitlements()` hook that fetches `GET /api/me/entitlements` once per page load and caches in React Query / SWR.

### 5.4 Existing pages — minimal changes

- Add a `<UserMenu>` to the nav (top-right). Shows "Sign in" if anonymous, or avatar + dropdown (Account, Sign out) if authed.
- Do NOT add tier-based gating to any page in this stage. Stage 3 handles all gating.

### 5.5 TypeScript types

Add to `src/lib/contracts.ts`:

```typescript
export type Tier = "scout" | "strategist" | "quant";

export type PlanStatus = "active" | "trialing" | "past_due" | "canceled";

export interface Entitlements {
  tier: Tier;
  status: PlanStatus;
  backtest_runs_remaining: number | null;  // null = unlimited
  universe_size_max: number;
  history_window_years: number;
  asset_classes: ("equities" | "commodities" | "a_shares")[];
  robustness_tests: string[];
  market_pulse_ticker_scope: "top_250" | "all_us" | "all_us_plus_alerts";
  business_model_section: "full" | "full_plus_supply_chain";
  commodity_framework: boolean;
  saved_strategies_max: number;
  api_access: boolean;
  community_badge: "verified" | "creator" | null;
}
```

---

## 6. Scheduled jobs

### Monthly usage reset

We do **not** reset rows. We use `(user_id, period_start)` as the primary key so a new month creates a new row automatically on first usage event. No cron needed.

But we do need a **garbage collection** for old usage rows (older than 13 months). Add a daily APScheduler job:

```python
@scheduler.scheduled_job("cron", hour=4, minute=0)
def cleanup_old_usage():
    cutoff = date.today() - timedelta(days=400)
    db.query(MonthlyUsage).filter(MonthlyUsage.period_start < cutoff).delete()
    db.commit()
```

---

## 7. Acceptance criteria

These must all pass before merging Stage 1.

1. **Signup works (password)** — POST `/api/auth/password/signup` with new email returns 201 + token; same email returns 409.
2. **Signup works (Google)** — frontend Google flow → backend callback → user row exists with `oauth_provider='google'`, `password_hash IS NULL`.
3. **Login works** — POST `/api/auth/password/login` with correct creds returns 200 + token; wrong password returns 401.
4. **Plan defaults to Scout** — every new user has a `plans` row with `tier='scout', status='active'`.
5. **Entitlements endpoint** — `GET /api/me/entitlements` returns the Scout caps from `TIER_CAPS["scout"]` for a fresh user.
6. **Usage starts at zero** — `GET /api/me` returns `usage.backtest_runs == 0` for a fresh user.
7. **Anonymous compat** — `POST /api/backtest/run` works for an unauthenticated request (returns 200, runs as legacy-anon user).
8. **Handle uniqueness** — `PATCH /api/me` with a taken handle returns 409; case-insensitive.
9. **Existing tests still pass** — the existing 52-test backend suite continues to pass with no modifications needed.
10. **Migration is idempotent** — running startup migration twice produces no errors and creates no duplicate rows.

---

## 8. Test plan

### Unit tests

`apps/api/tests/test_entitlements.py`:

- `test_scout_caps` — new user has Scout caps
- `test_runs_remaining_decrements` — incrementing usage decrements `backtest_runs_remaining`
- `test_runs_remaining_unlimited_for_paid` — Strategist + Quant users see `null`
- `test_new_month_resets_implicitly` — usage in May does not affect June

`apps/api/tests/test_auth_password.py`:

- `test_signup_creates_user_and_plan`
- `test_signup_duplicate_email_returns_409`
- `test_login_wrong_password_returns_401`
- `test_password_hashing_uses_bcrypt` — bcrypt cost factor ≥ 12

`apps/api/tests/test_auth_oauth.py`:

- `test_google_callback_creates_user_on_first_login`
- `test_google_callback_finds_existing_user_by_oauth_subject`
- `test_google_callback_rejects_invalid_id_token`

`apps/api/tests/test_handle.py`:

- `test_handle_validation_rules` — length, charset, reserved
- `test_handle_uniqueness_case_insensitive`

### Integration tests

`apps/api/tests/test_anon_compat.py`:

- POST a backtest without auth → 200, row created with `user_id='legacy-anon-0000'`
- POST a backtest with auth → 200, row created with `user_id=<authed user id>`

### Frontend tests

Playwright e2e in `apps/web/tests/e2e/auth.spec.ts`:

- Visit `/signup`, fill form, submit → redirected to `/account` with avatar showing email initial
- Click "Continue with Google" → mock OAuth flow → redirected to `/account`
- Click sign out from user menu → token cleared → redirected to `/`

---

## 9. Edge cases & error handling

- **Email validation** — RFC 5322 strict (use `email_validator` package); reject disposable domains (use blocklist library; this is a Year-1 anti-abuse measure but cheap to add now).
- **Bcrypt timing** — always run bcrypt verify on login, even on unknown email, to prevent timing attacks.
- **Race in `get_or_create_current_usage`** — use `INSERT ... ON CONFLICT DO NOTHING` semantics. Two parallel backtests on the first of the month must not both create rows.
- **Clock skew across servers** — period_start is server-side UTC. Document that monthly resets happen at midnight UTC, not user's local time.
- **OAuth account merging** — if a Google login arrives for an email that already has a password account, **do not auto-merge** in Stage 1. Return 409 with a clear error: "An account with this email already exists. Sign in with password." Year 2 will add account linking.
- **JWT revocation** — Stage 1 ships without a revocation list. JWTs are 30-day. To force logout (e.g., compromised account), rotate `NEXTAUTH_SECRET`. Document this in the auth README.
- **Locale fallback** — `locale` defaults to `"en"`. Frontend reads the browser `Accept-Language` on signup form but server is the source of truth post-signup.

---

## 10. Migration plan

1. Deploy backend with new tables + nullable `user_id` columns. Run startup migration.
2. Backfill `legacy-anon-0000` synthetic user and assign existing rows.
3. Deploy frontend with NextAuth + new pages. No gating yet.
4. Smoke test: existing anonymous flows still work; new auth flows work.
5. Monitor for 24h before starting Stage 2.

Rollback: drop the new tables, drop `user_id` columns (data loss only on the new rows, which are minimal in the first day).

---

## 11. Files to create / modify

**Backend (create):**
- `apps/api/app/models/user.py`
- `apps/api/app/schemas/identity.py`
- `apps/api/app/services/entitlements.py`
- `apps/api/app/services/auth_service.py` (password hashing, JWT, Google token verify)
- `apps/api/app/api/routes/auth.py`
- `apps/api/app/api/routes/me.py`
- `apps/api/app/api/deps.py` (FastAPI deps: `get_current_user`, `get_current_user_or_anonymous`)
- `apps/api/app/migrations/0001_add_users_and_plan.py`
- `apps/api/tests/test_entitlements.py`
- `apps/api/tests/test_auth_password.py`
- `apps/api/tests/test_auth_oauth.py`
- `apps/api/tests/test_handle.py`
- `apps/api/tests/test_anon_compat.py`

**Backend (modify):**
- `apps/api/app/main.py` — register new routers, add APScheduler startup
- `apps/api/app/core/config.py` — add `NEXTAUTH_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `apps/api/app/core/database.py` — confirm engine exposes session correctly
- Existing route files — add `Depends(get_current_user_or_anonymous)` to read user without breaking anonymous

**Frontend (create):**
- `apps/web/src/app/api/auth/[...nextauth]/route.ts`
- `apps/web/src/app/login/page.tsx`
- `apps/web/src/app/signup/page.tsx`
- `apps/web/src/app/account/page.tsx`
- `apps/web/src/components/UserMenu.tsx`
- `apps/web/src/lib/useEntitlements.ts`
- `apps/web/tests/e2e/auth.spec.ts`

**Frontend (modify):**
- `apps/web/src/app/layout.tsx` — add SessionProvider, add UserMenu to nav
- `apps/web/src/lib/contracts.ts` — add `Tier`, `Entitlements`, `UserPublic`
- `apps/web/src/lib/i18n.ts` — add strings for login/signup/account

**Env vars (add to `.env.example`):**

```
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<openssl rand -base64 32>
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
API_BASE_URL=http://localhost:8000
```

---

## 12. Open questions (to confirm before Stage 2)

- Confirm Stripe products will be created at fixed prices ($24/$19, $79/$59) — locked in proposal.
- Confirm trial duration 14 days no CC — locked in proposal.
- Confirm one synthetic legacy user is acceptable for existing anonymous rows — recommend yes.
- Confirm we do NOT auto-merge OAuth and password accounts — recommend no.
- Confirm 30-day JWT expiry — recommend yes.

---

## 13. Definition of done

- All acceptance criteria above pass.
- All new tests pass; full backend suite passes.
- Frontend `npm run build` clean, `npm run lint` clean.
- One smoke deploy to staging Railway + Vercel with real Google OAuth client.
- Roadmap dependencies updated — Stage 2 can start.
