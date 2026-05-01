from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.backtest import router as backtest_router
from app.api.routes.insights import router as insights_router
from app.api.routes.market_data import router as market_data_router
from app.api.routes.strategy import router as strategy_router
from app.core.config import get_settings
from app.db.migrations import run_startup_migrations
from app.db.session import Base, engine
from app.models import BacktestRecord, DataFetchLog, PriceBar, SymbolCache  # noqa: F401


@asynccontextmanager
async def lifespan(_: FastAPI):
    run_startup_migrations(engine)   # ADD COLUMN IF NOT EXISTS on symbols
    Base.metadata.create_all(bind=engine)  # creates new tables (data_fetch_logs, etc.)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(strategy_router)
app.include_router(backtest_router)
app.include_router(insights_router)
app.include_router(market_data_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
