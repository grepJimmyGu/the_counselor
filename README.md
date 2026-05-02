# Livermore AI

StrategyLab AI is a local MVP for natural-language investment strategy research. A user describes a price-based strategy in chat, the backend turns it into validated strategy JSON, a deterministic backtester runs it on historical data, and two separate AI-style layers respond:

- a friendly strategy explainer
- a skeptical sandbox reviewer that critiques trustworthiness

This MVP does **not** execute trades, does **not** accept arbitrary strategy code, and keeps the LLM role limited to parsing and commentary.

## Repo Structure

```text
apps/
  api/        FastAPI backend, market data cache, parser, validator, backtester
  web/        Next.js research workspace UI
packages/
  shared/     Shared seed payloads and future cross-app contract home
```

## What’s Included

- FastAPI backend with the requested MVP endpoints
- Alpha Vantage market data service with local persistence
- Strategy parser with deterministic fallback plus provider-adaptable LLM support
- Deterministic backtesting engine for:
  - moving average filter
  - moving average crossover
  - momentum rotation
  - RSI mean reversion
  - breakout
  - static allocation
- Metrics engine with risk and benchmark comparisons
- Explainer and sandbox reviewer with deterministic fallback plus provider-adaptable LLM support
- Next.js frontend research workspace with:
  - chat builder
  - strategy preview and editable simple fields
  - backtest dashboard
  - explanation tab
  - sandbox review tab
  - iteration comparison tab
- Unit tests for metrics calculations

## Required Environment Variables

Copy `.env.example` to `.env` and fill in the values you need.

```bash
cp .env.example .env
```

Required for full backtests:

- `ALPHA_VANTAGE_API_KEY`
- `NEXT_PUBLIC_API_BASE_URL`

Database configuration:

- `DATABASE_URL`
- `ALLOWED_ORIGINS`

Optional LLM configuration:

- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_STRATEGY_MODEL`
- `LLM_EXPLAINER_MODEL`
- `LLM_REVIEWER_MODEL`

### Database Note

The intended stack is PostgreSQL and the example environment file points there.

For local convenience, the backend currently falls back to a SQLite database file when `DATABASE_URL` is not set. That keeps the MVP runnable on a fresh machine that does not already have Postgres installed. For deployment or closer-to-prod behavior, set `DATABASE_URL` to PostgreSQL.

### CORS Note

The backend accepts a comma-separated `ALLOWED_ORIGINS` value. For production, set this to your Vercel frontend URL and any custom domain you attach later.

### LLM Adapter Note

The backend can run with no LLM configured at all. In that case it falls back to the local deterministic parser, explainer, and reviewer logic.

To enable live LLM calls, set:

- `LLM_PROVIDER=openai_compatible`
- `LLM_API_KEY=...`
- `LLM_BASE_URL=https://api.openai.com/v1` or another OpenAI-compatible endpoint
- `LLM_STRATEGY_MODEL=...`
- optionally `LLM_EXPLAINER_MODEL=...`
- optionally `LLM_REVIEWER_MODEL=...`

This keeps the integration adaptable: the app talks through one provider interface, and the current implementation targets OpenAI-compatible chat completion APIs instead of hardwiring one vendor-specific SDK into the product surface.

## Local Setup

### 1. Backend

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.txt
```

Run the API:

```bash
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload
```

The API will start on `http://127.0.0.1:8000`.

### 2. Frontend

Install frontend dependencies from the repo root or inside `apps/web`:

```bash
cd apps/web
npm install
```

Run the frontend:

```bash
npm run dev
```

The app will start on `http://127.0.0.1:3000`.

## API Endpoints

- `POST /api/chat/strategy`
- `POST /api/backtest/run`
- `GET /api/backtest/{backtest_id}`
- `POST /api/insights/explain`
- `POST /api/review/sandbox`
- `GET /api/symbols/search?query=`
- `GET /api/data/daily/{symbol}`

## Verification

Backend tests:

```bash
cd apps/api
../../.venv/bin/pytest
```

Frontend checks:

```bash
cd apps/web
npm run lint
npm run build
```

## Public Deployment: Vercel + Railway

This repo is set up for:

- `apps/web` on Vercel
- `apps/api` on Railway

### 1. Deploy the backend to Railway

Create a Railway project from the GitHub repo and set the service root to `apps/api`.

Railway service settings:

- Root directory: `apps/api`
- Start command: handled by `apps/api/railway.json`
- Health check path: `/health`

Railway environment variables:

- `ALPHA_VANTAGE_API_KEY`
- `DATABASE_URL`
- `ALLOWED_ORIGINS`
- optional LLM variables if you want production LLM-backed parsing and commentary

Recommended production `ALLOWED_ORIGINS` example:

```text
https://your-frontend-project.vercel.app,https://your-custom-domain.com
```

Once deployed, generate a public Railway domain for the API service.

### 2. Deploy the frontend to Vercel

Create a Vercel project from the same GitHub repo and set:

- Root directory: `apps/web`

Vercel environment variables:

- `NEXT_PUBLIC_API_BASE_URL=https://your-railway-api-domain`

After the first Vercel deploy finishes, copy the Vercel URL and add it to Railway `ALLOWED_ORIGINS`, then redeploy the Railway service if needed.

### 3. Recommended production database

For an always-on public deployment, use PostgreSQL instead of SQLite.

Good options:

- Railway Postgres
- Neon Postgres
- Supabase Postgres

### 4. Production caveat

The current Alpha Vantage integration is tuned for free-tier compatibility and may only have access to recent compact daily history depending on the API key plan. Shorter lookback strategies work better on the free tier than long-horizon 200-day signals.

## Current MVP Caveats

- The live LLM path currently expects an OpenAI-compatible chat completions API.
- If the LLM is unconfigured or returns invalid JSON, the backend falls back to deterministic local logic.
- Alpha Vantage rate limits still apply.
- Local symbol search is cached opportunistically as searches are made.
- Production deployment targets are not wired yet; this repo is focused on a local working MVP.
