"""Shared pytest fixtures for Stage 1 identity tests.

Uses an in-memory SQLite database so tests are fully isolated and fast.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db.session import Base
from app.db.migrations import run_startup_migrations

# Import all models so Base.metadata includes them
import app.models  # noqa: F401


@pytest.fixture(scope="function")
def db() -> Session:
    """Fresh in-memory SQLite DB per test, with all tables + Stage 1 migration applied."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def make_user(db: Session):
    """Factory: create a real user+plan in the test DB and return the User ORM object."""
    from app.api.routes.auth import _create_user_with_plan

    def _factory(
        email: str = "test@example.com",
        password: str | None = None,
        tier: str = "scout",
        oauth_provider: str | None = None,
        oauth_subject: str | None = None,
    ):
        from app.services.auth_service import hash_password as _hp
        pw_hash = _hp(password) if password else None
        user = _create_user_with_plan(
            db,
            email=email,
            password_hash=pw_hash,
            oauth_provider=oauth_provider,
            oauth_subject=oauth_subject,
        )
        if tier != "scout":
            user.plan.tier = tier
            db.commit()
            db.refresh(user)
        return user

    return _factory
