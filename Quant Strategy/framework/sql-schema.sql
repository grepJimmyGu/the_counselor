-- =============================================================================
-- Livermore Strategy Library — Iteration Framework SQL Schema
-- =============================================================================
--
-- Two additive tables for periodic library refreshes:
--   1. knowledge_sources         — indexed mirror of /Quant Strategy/knowledge-base/
--   2. strategy_template_lifecycle — lifecycle state of every template
--
-- Both are populated by sync scripts that read the markdown front-matter and
-- upsert rows here. The markdown files remain the source of truth; this table
-- is for fast queries from the Livermore app (e.g. "show me the source paper
-- for this template", "which templates are deprecated").
--
-- Designed for PostgreSQL with a SQLite fallback (Livermore supports both).
-- All JSON columns use jsonb on Postgres; SQLite stores them as TEXT.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- knowledge_sources
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_sources (
    id                      UUID PRIMARY KEY,
    source_type             VARCHAR(40) NOT NULL,    -- 'book' | 'paper' | 'market-research' | 'strategy'
    title                   VARCHAR(500) NOT NULL,
    authors                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    year                    INTEGER,
    url                     VARCHAR(1000),
    file_path               VARCHAR(1000),           -- relative path under /Quant Strategy/
    md_path                 VARCHAR(1000) NOT NULL,  -- relative path to the kb markdown file
    summary                 TEXT,

    tags                    JSONB NOT NULL DEFAULT '[]'::jsonb,
    asset_classes           JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_tier           CHAR(1) CHECK (evidence_tier IN ('A','B','C')),
    strategies_referenced   JSONB NOT NULL DEFAULT '[]'::jsonb,

    status                  VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active' | 'archived'
    added_at                TIMESTAMP NOT NULL,
    last_reviewed_at        TIMESTAMP,
    reviewed_by             VARCHAR(200),
    superseded_by           UUID REFERENCES knowledge_sources(id),

    content_hash            VARCHAR(64),             -- sha256 of the md file, for incremental sync
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_sources_type
    ON knowledge_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_status
    ON knowledge_sources(status);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_evidence_tier
    ON knowledge_sources(evidence_tier);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_tags
    ON knowledge_sources USING gin (tags);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_strategies_referenced
    ON knowledge_sources USING gin (strategies_referenced);


-- -----------------------------------------------------------------------------
-- strategy_template_lifecycle
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS strategy_template_lifecycle (
    -- Slug is the canonical id (matches kebab-cased livermore_strategy_type).
    slug                    VARCHAR(100) PRIMARY KEY,

    livermore_strategy_type VARCHAR(100) NOT NULL,   -- matches StrategyType Literal in apps/api/app/schemas/strategy.py
    name                    VARCHAR(200) NOT NULL,
    md_path                 VARCHAR(1000) NOT NULL,  -- relative path to the template md file

    -- Lifecycle stage corresponds to the folder under /Quant Strategy/templates/
    status                  VARCHAR(20) NOT NULL
                            CHECK (status IN ('candidate','mvp','production','deprecated')),

    -- Classification (mirrors the template front-matter)
    edge_type               VARCHAR(40),             -- 'technical' | 'fundamental' | 'event-driven' | 'sentiment' | 'composite-ml'
    horizon                 VARCHAR(40),             -- 'intraday' | 'swing' | 'position' | 'multi-quarter'
    asset_class             VARCHAR(40),
    universe_shape          VARCHAR(40),             -- 'single-name' | 'pair' | 'basket' | 'full-universe'
    directionality          VARCHAR(40),             -- 'long-only' | 'long-cash' | 'long-short' | 'pair-neutral'
    evidence_tier           CHAR(1) CHECK (evidence_tier IN ('A','B','C')),
    capacity_tag            VARCHAR(40),             -- 'retail' | 'prosumer' | 'institutional'

    -- Provenance
    introduced_in_cycle     VARCHAR(20),             -- 'Q2-2026'
    source_ids              JSONB NOT NULL DEFAULT '[]'::jsonb,   -- knowledge_sources.id values
    reference_sharpe_range  VARCHAR(80),
    reference_drawdown_range VARCHAR(80),
    sample_window           VARCHAR(80),

    -- Usage telemetry (rolling 90d snapshot, refreshed by the monthly cron)
    backtests_90d           INTEGER NOT NULL DEFAULT 0,
    unique_users_90d        INTEGER NOT NULL DEFAULT 0,
    save_count_90d          INTEGER NOT NULL DEFAULT 0,
    fork_count_90d          INTEGER NOT NULL DEFAULT 0,
    thumbs_down_rate_90d    NUMERIC(5,4) NOT NULL DEFAULT 0,
    telemetry_as_of         TIMESTAMP,

    -- Lifecycle metadata
    last_reviewed_at        TIMESTAMP,
    deprecation_reason      TEXT,
    superseded_by           VARCHAR(100) REFERENCES strategy_template_lifecycle(slug),

    content_hash            VARCHAR(64),
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_template_lifecycle_status
    ON strategy_template_lifecycle(status);
CREATE INDEX IF NOT EXISTS idx_template_lifecycle_edge_horizon
    ON strategy_template_lifecycle(edge_type, horizon);
CREATE INDEX IF NOT EXISTS idx_template_lifecycle_capacity
    ON strategy_template_lifecycle(capacity_tag);


-- -----------------------------------------------------------------------------
-- VIEWS for the in-app gallery
-- -----------------------------------------------------------------------------

-- Production-visible templates with their primary source.
CREATE OR REPLACE VIEW v_template_gallery AS
SELECT
    t.slug,
    t.livermore_strategy_type,
    t.name,
    t.edge_type,
    t.horizon,
    t.asset_class,
    t.universe_shape,
    t.evidence_tier,
    t.capacity_tag,
    t.reference_sharpe_range,
    t.reference_drawdown_range,
    t.backtests_90d,
    t.save_count_90d,
    (
        SELECT json_agg(json_build_object(
            'title', k.title,
            'authors', k.authors,
            'year', k.year,
            'url', k.url
        ))
        FROM knowledge_sources k
        WHERE k.id::text = ANY (
            SELECT jsonb_array_elements_text(t.source_ids)
        )
    ) AS sources
FROM strategy_template_lifecycle t
WHERE t.status IN ('mvp','production');


-- Cold templates worth reviewing — used in the quarterly cycle Step 1.
CREATE OR REPLACE VIEW v_cold_templates AS
SELECT slug, name, status, backtests_90d, unique_users_90d, last_reviewed_at
FROM strategy_template_lifecycle
WHERE status IN ('mvp','production')
  AND backtests_90d < 5
ORDER BY backtests_90d ASC, last_reviewed_at NULLS FIRST;


-- -----------------------------------------------------------------------------
-- Telemetry events that have to exist on the user side for Step 1 to be useful.
-- Wire these in the existing backtest, strategy_storage, and sandbox routes.
-- -----------------------------------------------------------------------------

-- A lean events table; OK to keep separate from existing backtest_runs since
-- it tracks UX-side actions (saved, forked, thumbs-down) rather than runs.
CREATE TABLE IF NOT EXISTS template_usage_events (
    id          UUID PRIMARY KEY,
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW(),
    user_id     VARCHAR(100),
    strategy_id VARCHAR(100),
    template_slug VARCHAR(100),                     -- denormalized for fast filtering
    event_type  VARCHAR(40) NOT NULL,               -- 'backtest_run' | 'strategy_saved' | 'strategy_forked' | 'sandbox_thumbs_down' | 'sandbox_thumbs_up' | 'explainer_thumbs_down'
    metadata    JSONB
);

CREATE INDEX IF NOT EXISTS idx_template_usage_events_occurred
    ON template_usage_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_template_usage_events_template
    ON template_usage_events(template_slug, occurred_at);
CREATE INDEX IF NOT EXISTS idx_template_usage_events_type
    ON template_usage_events(event_type, occurred_at);


-- -----------------------------------------------------------------------------
-- Refresh script outline:
--
-- 1. KB sync: walk /Quant Strategy/knowledge-base/**/*.md, parse front-matter,
--    upsert into knowledge_sources keyed by md_path. Skip files unchanged
--    since last sync (content_hash).
--
-- 2. Template sync: walk /Quant Strategy/templates/<status>/*.md, upsert into
--    strategy_template_lifecycle keyed by slug. The folder location overrides
--    the front-matter status field (folder is source of truth for stage).
--
-- 3. Telemetry refresh: monthly cron writes backtests_90d, save_count_90d,
--    thumbs_down_rate_90d via aggregates over template_usage_events.
--
-- Suggested location of these scripts:
--   apps/api/app/scripts/sync_knowledge_sources.py
--   apps/api/app/scripts/sync_template_lifecycle.py
--   apps/api/app/scripts/refresh_template_telemetry.py
-- =============================================================================
