from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
database_url = settings.database_url

# Railway Postgres URLs are commonly provided as `postgresql://...` (or sometimes
# legacy `postgres://...`). SQLAlchemy's default PostgreSQL dialect expects
# psycopg2 for those schemes, but this app ships Psycopg 3 via `psycopg[binary]`.
# Normalize the URL so hosted environments use the installed driver.
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)

engine_kwargs: dict = {"future": True}
if database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Postgres-only resilience knobs (2026-05-26 Railway pool-exhaustion fix).
    #
    # Why these settings exist:
    #
    # • pool_pre_ping=True — Each checkout issues a lightweight `SELECT 1` to
    #   confirm the connection is still alive. Without this, a connection
    #   killed server-side (Postgres idle timeout, network blip, Railway
    #   restart) sits in the pool as a "live" slot; the next query that
    #   draws it dies with `OperationalError: server closed the connection
    #   unexpectedly`. Repeat a few times and the pool is full of zombies
    #   that look used but can't serve queries. Cheap (~1ms per checkout)
    #   and well worth it in any hosted environment.
    #
    # • pool_recycle=1800 — Drop and recreate connections older than 30
    #   minutes. Belt-and-braces against the same zombie class for hosts
    #   that silently close conns after N minutes of inactivity.
    #
    # • pool_size=10, max_overflow=20 — bump from SQLAlchemy defaults
    #   (5 + 10). Production carries APScheduler cron jobs + LLM-batched
    #   chat requests + async route handlers that hold sessions across
    #   external `await` calls (see apps/api/CLAUDE.md trap #12). 15 was
    #   not enough headroom; 30 gives ~2x cushion before queue-and-wait.
    #
    # • pool_timeout=20 — fail-fast: a connection wait that exceeds 20s
    #   means something is wedged. Surface it as a 500 immediately instead
    #   of holding the request handler for the full 30s default, which
    #   compounds the pile-up when traffic is bursty.
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 20,
    })
engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
