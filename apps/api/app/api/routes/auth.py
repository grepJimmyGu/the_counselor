from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.anonymous_session import AnonymousSession
from app.models.user import User, Plan
from app.schemas.identity import (
    GoogleTokenResponse,
    LoginRequest,
    OAuthGoogleRequest,
    PasswordChangeRejected,
    PasswordChangeRequest,
    PasswordRejected,
    PasswordResetAccepted,
    PasswordResetConfirm,
    PasswordResetRejected,
    PasswordResetRequest,
    PatchMeRequest,
    SignupRequest,
    TokenResponse,
    UserPublic,
)
from app.services.anonymous_service import COOKIE_NAME as ANON_COOKIE_NAME
from app.services.anonymous_service import merge_anonymous_into_user
from app.services import password_policy, password_reset
from app.services.pwned_passwords import breach_count
from app.services.auth_service import (
    create_session_token,
    decode_session_token_ignoring_expiry,
    token_predates_password_change,
    hash_password,
    new_user_id,
    validate_handle,
    verify_google_id_token,
    verify_password_safe,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_token_response(user: User) -> TokenResponse:
    token = create_session_token(user.id, user.plan.tier)
    pub = UserPublic(
        id=user.id,
        handle=user.handle,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        locale=user.locale,
    )
    return TokenResponse(user=pub, session_token=token)


def _get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.lower()).first()


def _create_user_with_plan(
    db: Session,
    *,
    email: str,
    password_hash: Optional[str] = None,
    display_name: Optional[str] = None,
    locale: str = "en",
    oauth_provider: Optional[str] = None,
    oauth_subject: Optional[str] = None,
    avatar_url: Optional[str] = None,
    email_verified_at: Optional[datetime] = None,
) -> User:
    user = User(
        id=new_user_id(),
        email=email.lower(),
        password_hash=password_hash,
        display_name=display_name,
        locale=locale,
        oauth_provider=oauth_provider,
        oauth_subject=oauth_subject,
        avatar_url=avatar_url,
        email_verified_at=email_verified_at,
    )
    plan = Plan(user_id=user.id, tier="scout", status="active")
    db.add(user)
    db.add(plan)
    db.commit()
    db.refresh(user)
    return user


def _try_merge_anonymous_session(
    db: Session,
    user_id: str,
    anon_session_id: Optional[str],
) -> None:
    """Stage 1a: if this signup came from an anonymous browser, attach the
    one-shot backtest to the new user and mark the session converted.
    Idempotent and silent on failure (signup must not fail because of merge issues)."""
    if not anon_session_id:
        return
    session = db.get(AnonymousSession, anon_session_id)
    if session is None:
        return
    try:
        merge_anonymous_into_user(db, session, user_id)
    except Exception:
        # Never block signup on merge failure.
        db.rollback()


def _try_convert_attribution(db: Session, request: Request, user: User) -> None:
    """Stage 4a: if the signup came from a /s/<slug>?via=<handle> click,
    convert the un-converted attribution row to this user. Silent on failure."""
    try:
        from app.services.attribution_service import convert_on_signup
        convert_on_signup(db, request, user)
    except Exception:
        db.rollback()


def _track_signup_completed(user: User, provider: str) -> None:
    """Stage 6a: fire signup_completed analytics event. Safe no-op."""
    try:
        from app.services.posthog_service import capture
        capture(user.id, "signup_completed", {
            "provider": provider,
            "locale": user.locale or "en",
        })
    except Exception:
        pass

    # Stage 6a — DEFERRED_TRIGGER: ZH email templates are not localized yet.
    # When the first ZH user signs up, log so we can prioritize translating
    # the welcome email (and future templates) (see docs/DEFERRED.md).
    if (user.locale or "en") == "zh":
        import logging as _logging
        _logging.getLogger("livermore.deferred").info(
            "DEFERRED_TRIGGER: zh_email_templates — user_id=%s signed up with "
            "locale=zh; welcome email currently EN-only (see docs/DEFERRED.md)",
            user.id,
        )


def _try_send_welcome_email(db: Session, user: User) -> None:
    """Stage 6a: fire-and-forget welcome email. Safe no-op when Resend
    isn't configured. Failure must never block signup."""
    try:
        from app.emails.welcome import render_welcome
        from app.services.email_service import send_email
        rendered = render_welcome(user)
        send_email(
            db, user,
            template="welcome",
            subject=rendered["subject"],
            html=rendered["html"],
            text=rendered["text"],
            category="marketing",  # welcome is borderline; respects unsub
        )
    except Exception:
        pass


# ── Password signup / login ───────────────────────────────────────────────────

def _password_rejected(code: str, detail: str, failed: Optional[List[str]] = None) -> JSONResponse:
    body = PasswordRejected(detail=detail, code=code, failed=failed or [])
    return JSONResponse(status_code=400, content=body.model_dump())


@router.post(
    "/password/signup",
    status_code=201,
    response_model=TokenResponse,
    responses={400: {"model": PasswordRejected}},
)
def password_signup(
    body: SignupRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    failed = password_policy.violations(body.password, body.email, body.display_name)
    if failed:
        detail = " ".join(password_policy.MESSAGES[code] for code in failed)
        return _password_rejected("weak_password", detail, failed)
    existing = _get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    # After the 409 so that an address that is already taken costs no lookup.
    if breach_count(body.password):
        return _password_rejected("breached_password", _BREACHED)
    hashed = hash_password(body.password)
    user = _create_user_with_plan(
        db,
        email=body.email,
        password_hash=hashed,
        display_name=body.display_name,
        locale=body.locale,
    )
    # Stage 1a: attach any anonymous one-shot backtest to this new account.
    _try_merge_anonymous_session(db, user.id, request.cookies.get(ANON_COOKIE_NAME))
    # Stage 4a: convert any /s/<slug>?via=<handle> attribution.
    _try_convert_attribution(db, request, user)
    # Stage 6a: signup_completed event + welcome email.
    _track_signup_completed(user, provider="password")
    _try_send_welcome_email(db, user)
    return _make_token_response(user)


@router.post("/password/login")
def password_login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = _get_user_by_email(db, body.email)
    # Always run bcrypt to normalise timing even if user doesn't exist
    stored_hash = existing.password_hash if existing else None
    if not verify_password_safe(body.password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if existing is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    existing.last_login_at = datetime.utcnow()
    db.commit()
    return _make_token_response(existing)


# ── Password reset ────────────────────────────────────────────────────────────

_BREACHED = "That password has appeared in a known data breach. Choose a different one."


def _reset_rejected(code: str, detail: str, failed: Optional[List[str]] = None) -> JSONResponse:
    body = PasswordResetRejected(detail=detail, code=code, failed=failed or [])
    return JSONResponse(status_code=400, content=body.model_dump())


def _send_reset_code(db: Session, email: str) -> None:
    """Email a reset code to `email` if it has an account and has not been
    sent too many. Says nothing to its caller either way."""
    user = _get_user_by_email(db, email)
    if user is None:
        return
    code = password_reset.issue_code(db, user)
    if code is None:
        return
    from app.emails.password_reset import render_reset_code
    from app.services.email_service import send_email
    rendered = render_reset_code(user, code)
    sent = send_email(
        db, user,
        template="password_reset",
        subject=rendered["subject"],
        html=rendered["html"],
        text=rendered["text"],
        category="transactional",
    )
    if not sent:
        # send_email is a silent no-op without RESEND_API_KEY. Here that means
        # a user is waiting for a code that will never arrive.
        logging.getLogger("livermore.auth").error(
            "password reset code NOT emailed (is RESEND_API_KEY set?): user_id=%s", user.id,
        )


def _send_reset_code_after_reply(email: str) -> None:
    # The request's own session is gone by the time this runs.
    with SessionLocal() as db:
        try:
            _send_reset_code(db, email)
        except Exception:
            logging.getLogger("livermore.auth").exception("password reset request failed")


def _send_password_changed_after_reply(user_id: str) -> None:
    from app.emails.password_reset import render_password_changed
    from app.services.email_service import send_email
    with SessionLocal() as db:
        try:
            user = db.get(User, user_id)
            if user is None:
                return
            rendered = render_password_changed(user)
            send_email(
                db, user,
                template="password_changed",
                subject=rendered["subject"],
                html=rendered["html"],
                text=rendered["text"],
                category="transactional",
            )
        except Exception:
            logging.getLogger("livermore.auth").exception("password-changed notice failed")


@router.post("/password/reset/request", status_code=202, response_model=PasswordResetAccepted)
def request_password_reset(
    body: PasswordResetRequest,
    background_tasks: BackgroundTasks,
) -> PasswordResetAccepted:
    """Ask for a reset code by email.

    The reply is the same for every address and is sent before the account
    is even looked up, so neither its words nor how long it takes says
    whether the address is registered.
    """
    background_tasks.add_task(_send_reset_code_after_reply, body.email)
    return PasswordResetAccepted(
        detail="If that address has a Livermore account, a reset code is on its way.",
    )


@router.post(
    "/password/reset/confirm",
    response_model=TokenResponse,
    responses={400: {"model": PasswordResetRejected}},
)
def confirm_password_reset(
    body: PasswordResetConfirm,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Set a new password with the emailed code, and sign in.

    Works for an account that has only ever used Google: the code proves the
    same thing a Google sign-in does, control of the mailbox, and afterwards
    the account can sign in either way.
    """
    user = _get_user_by_email(db, body.email)
    failed = password_policy.violations(
        body.new_password, body.email, user.display_name if user else None,
    )
    if failed:
        # Before the code is looked at, so a typo in the password does not
        # cost one of the code's guesses.
        detail = " ".join(password_policy.MESSAGES[code] for code in failed)
        return _reset_rejected("weak_password", detail, failed)
    # One answer for a wrong code, an expired one, a used one and an address
    # with no account.
    used = password_reset.check_code(db, user, body.code) if user else None
    if used is None:
        return _reset_rejected("invalid_code", "That code is wrong or has expired. Ask for a new one.")
    # The code stays open, so a different password can be tried with it.
    if breach_count(body.new_password):
        return _reset_rejected("breached_password", _BREACHED)
    password_reset.set_password(db, user, used, body.new_password)
    background_tasks.add_task(_send_password_changed_after_reply, user.id)
    return _make_token_response(user)


# ── Changing the password while signed in ─────────────────────────────────────

def _change_rejected(code: str, detail: str, failed: Optional[List[str]] = None) -> JSONResponse:
    body = PasswordChangeRejected(detail=detail, code=code, failed=failed or [])
    return JSONResponse(status_code=400, content=body.model_dump())


@router.post(
    "/password/change",
    response_model=TokenResponse,
    responses={400: {"model": PasswordChangeRejected}},
)
def change_password(
    body: PasswordChangeRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Replace the signed-in user's password.

    Being signed in is not enough: the current password is asked for again,
    so a session left open on a borrowed phone, or a stolen token, cannot be
    turned into lasting control of the account.

    Every other session is signed out. This one would be too, since its token
    is older than the change, so the reply carries a new token to carry on with.
    """
    if user.password_hash is None:
        # Signed in through Google, with no password to confirm. Setting one
        # from here would let a stolen session add its own way in; the reset
        # by email proves the mailbox instead.
        return _change_rejected(
            "no_password",
            "This account signs in with Google and has no password yet. "
            "Sign out and use Forgot password to set one.",
        )
    if not verify_password_safe(body.current_password, user.password_hash):
        return _change_rejected("wrong_password", "That is not your current password.")
    if body.new_password == body.current_password:
        return _change_rejected("same_password", "Choose a password you are not already using.")
    failed = password_policy.violations(body.new_password, user.email, user.display_name)
    if failed:
        detail = " ".join(password_policy.MESSAGES[code] for code in failed)
        return _change_rejected("weak_password", detail, failed)
    if breach_count(body.new_password):
        return _change_rejected("breached_password", _BREACHED)
    # Plain values now: the commit below expires `user`.
    user_id = user.id
    password_reset.replace_password(db, user, body.new_password)
    db.commit()
    background_tasks.add_task(_send_password_changed_after_reply, user_id)
    return _make_token_response(user)


# ── Google OAuth callback ─────────────────────────────────────────────────────

@router.post("/oauth/google/callback", response_model=GoogleTokenResponse)
def google_oauth_callback(
    body: OAuthGoogleRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    try:
        payload = verify_google_id_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    google_sub = payload.get("sub")
    email = payload.get("email", "").lower()
    name = payload.get("name")
    picture = payload.get("picture")
    email_verified = payload.get("email_verified", False)

    # Look up by oauth_subject first (most reliable)
    user = db.query(User).filter(
        User.oauth_provider == "google", User.oauth_subject == google_sub
    ).first()

    is_new = False
    if user is None:
        # Check if email already exists (may be a password account)
        existing_by_email = _get_user_by_email(db, email)
        if existing_by_email and existing_by_email.password_hash is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "An account with this email already exists. "
                    "Sign in with your password instead."
                ),
            )
        if existing_by_email:
            # Existing Google-only user whose oauth_subject wasn't set yet — update
            existing_by_email.oauth_provider = "google"
            existing_by_email.oauth_subject = google_sub
            existing_by_email.last_login_at = datetime.utcnow()
            db.commit()
            user = existing_by_email
        else:
            user = _create_user_with_plan(
                db,
                email=email,
                oauth_provider="google",
                oauth_subject=google_sub,
                display_name=name,
                avatar_url=picture,
                email_verified_at=datetime.utcnow() if email_verified else None,
            )
            is_new = True
    else:
        # Update profile fields from Google on each login
        user.display_name = user.display_name or name
        user.avatar_url = user.avatar_url or picture
        user.last_login_at = datetime.utcnow()
        db.commit()

    # Stage 1a: merge anonymous backtest on NEW Google signups only.
    # Returning users already have their account; nothing to merge.
    if is_new:
        _try_merge_anonymous_session(db, user.id, request.cookies.get(ANON_COOKIE_NAME))
        # Stage 4a: convert any /s/<slug>?via=<handle> attribution.
        _try_convert_attribution(db, request, user)
        # Stage 6a: signup_completed event + welcome email.
        _track_signup_completed(user, provider="google")
        _try_send_welcome_email(db, user)

    token = create_session_token(user.id, user.plan.tier)
    pub = UserPublic(
        id=user.id,
        handle=user.handle,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        locale=user.locale,
    )
    return {"user": pub.model_dump(), "session_token": token, "is_new": is_new}


# ── Legacy sync-user endpoint (NextAuth Google OAuth — kept for backward compat) ──

from fastapi import Header  # noqa: E402
from pydantic import BaseModel  # noqa: E402


class _SyncUserRequest(BaseModel):
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    provider: str = "google"
    provider_user_id: str
    # Stage 1a: NextAuth forwards the livermore_anon_id cookie value so we
    # can merge any pre-signup anonymous backtest into the new user.
    anonymous_session_id: Optional[str] = None
    # Stage 4a: NextAuth forwards the livermore_vsid cookie value so we can
    # convert the referrer-attribution row to this new user.
    visitor_session_id: Optional[str] = None


class _UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime
    # The backend-minted JWT session token. Returned by sync-user so the
    # Next.js auth.ts jwt() callback can store it as session.backendToken,
    # which the workspace + other authed endpoints read on subsequent calls.
    session_token: Optional[str] = None


def _verify_internal_key(x_internal_key: Optional[str] = Header(default=None)) -> None:
    from app.core.config import get_settings
    settings = get_settings()
    required = settings.internal_api_key
    if not required:
        raise HTTPException(status_code=503, detail="INTERNAL_API_KEY not configured.")
    if x_internal_key != required:
        raise HTTPException(status_code=401, detail="Invalid internal key.")


@router.post("/sync-user", response_model=_UserResponse, dependencies=[Depends(_verify_internal_key)])
def sync_user(body: _SyncUserRequest, db: Session = Depends(get_db)) -> _UserResponse:
    """Upsert a user on OAuth sign-in from Next.js server-side auth."""
    now = datetime.utcnow()
    user = db.query(User).filter(
        User.oauth_provider == body.provider,
        User.oauth_subject == body.provider_user_id,
    ).first()

    if user is None:
        user = _get_user_by_email(db, body.email)

    is_new_user = user is None
    if user:
        user.display_name = body.display_name or user.display_name
        user.avatar_url = body.avatar_url or user.avatar_url
        user.last_login_at = now
        if not user.oauth_subject:
            user.oauth_provider = body.provider
            user.oauth_subject = body.provider_user_id
        db.commit()
    else:
        user = _create_user_with_plan(
            db,
            email=body.email,
            display_name=body.display_name,
            avatar_url=body.avatar_url,
            oauth_provider=body.provider,
            oauth_subject=body.provider_user_id,
            email_verified_at=now,
        )

    # Stage 1a: merge anonymous backtest on NEW signups only.
    # Stage 4a: convert any /s/<slug>?via=<handle> attribution by faking a
    # cookie object on a temp request — convert_on_signup just reads
    # request.cookies.get('livermore_vsid').
    if is_new_user:
        _try_merge_anonymous_session(db, user.id, body.anonymous_session_id)
        if body.visitor_session_id:
            try:
                from app.services.attribution_service import (
                    VSID_COOKIE_NAME,
                    convert_on_signup,
                )

                class _FauxReq:
                    cookies = {VSID_COOKIE_NAME: body.visitor_session_id}

                convert_on_signup(db, _FauxReq(), user)  # type: ignore[arg-type]
            except Exception:
                db.rollback()

    # Heal orphaned User rows that have no Plan row attached. This came up
    # for users created during the May 19/20 migration odyssey, where a
    # partial-failure path could commit a User without its companion Plan.
    # Without this heal, every subsequent sync-user call 500s on
    # `user.plan.tier` and the user is permanently stuck with backendToken=null.
    if user.plan is None:
        db.add(Plan(user_id=user.id, tier="scout", status="active"))
        db.commit()
        db.refresh(user)
        logging.getLogger("livermore.auth").warning(
            "healed orphaned user without plan: user_id=%s email=%s",
            user.id, user.email,
        )

    return _UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        session_token=create_session_token(user.id, user.plan.tier),
    )


class _RefreshSessionTokenRequest(BaseModel):
    email: str
    # The token the caller holds now, expired or not. Optional so a website
    # deployed before 2026-11-19 keeps working; without it a session that a
    # password reset signed out cannot be told from any other.
    current_token: Optional[str] = None


class _RefreshSessionTokenResponse(BaseModel):
    id: str
    session_token: str


@router.post(
    "/refresh-session-token",
    response_model=_RefreshSessionTokenResponse,
    dependencies=[Depends(_verify_internal_key)],
)
def refresh_session_token(
    body: _RefreshSessionTokenRequest, db: Session = Depends(get_db)
) -> _RefreshSessionTokenResponse:
    """Mint a fresh backend session token for an already-authenticated user.

    Called from the Next.js `jwt()` callback when the stored `backendToken` is
    missing or near its 30-day expiry. NextAuth has already verified its own
    signed session cookie before that callback runs, so `email` here is a
    trusted claim; the `X-Internal-Key` guard keeps the endpoint off the public
    surface.

    Deliberately mint-only — unlike `sync-user` this writes NOTHING. Broadening
    the re-mint trigger from "token missing" to "token expired" makes this path
    fire for password users too, and `sync-user` would stamp
    `oauth_provider`/`oauth_subject` onto their rows (it sets them whenever
    `oauth_subject` is falsy). A token refresh must not mutate how an account
    logs in.
    """
    user = _get_user_by_email(db, body.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # A password reset signs out every session that existed before it. The
    # website's session would otherwise outlive that: its cookie rolls forward
    # on its own, and this endpoint would hand it a new backend token on request.
    held = decode_session_token_ignoring_expiry(body.current_token) if body.current_token else None
    if held is not None and token_predates_password_change(held, user.password_changed_at):
        raise HTTPException(status_code=401, detail="This session was signed out by a password reset.")

    # An orphaned User without a Plan would AttributeError on `.tier`. `sync-user`
    # heals that row; this endpoint stays read-only and falls back to the same
    # default tier `get_current_user_or_anonymous` uses, so a refresh can never
    # be the thing that writes a Plan.
    tier = user.plan.tier if user.plan else "scout"
    if user.plan is None:
        logging.getLogger("livermore.auth").warning(
            "refresh-session-token: user has no plan, defaulting tier=scout: "
            "user_id=%s email=%s",
            user.id, user.email,
        )

    return _RefreshSessionTokenResponse(
        id=user.id,
        session_token=create_session_token(user.id, tier),
    )


@router.get("/me", dependencies=[Depends(_verify_internal_key)])
def legacy_get_me(
    provider_user_id: str,
    provider: str = "google",
    db: Session = Depends(get_db),
) -> _UserResponse:
    """Legacy lookup by provider + provider_user_id (called from Next.js)."""
    user = db.query(User).filter(
        User.oauth_subject == provider_user_id,
        User.oauth_provider == provider,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return _UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )
