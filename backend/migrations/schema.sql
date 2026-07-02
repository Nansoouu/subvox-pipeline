-- ═══════════════════════════════════════════════════════════════════
-- schema.sql — Subvox Full Database Schema
-- ═══════════════════════════════════════════════════════════════════
-- Apply: psql -d subvox -f schema.sql
-- ═══════════════════════════════════════════════════════════════════

-- ── Extensions ────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ═══════════════════════════════════════════════════════════════════
-- 1. USERS
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id               TEXT PRIMARY KEY,                        -- wallet address (Solana) or UUID (email)
    email            TEXT,
    wallet_address   TEXT UNIQUE,
    role             TEXT NOT NULL DEFAULT 'user',            -- 'user', 'admin', 'moderator'
    email_confirmed  BOOLEAN NOT NULL DEFAULT FALSE,
    avatar_url       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login       TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════════
-- 2. JOBS (pipeline tasks)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT REFERENCES users(id) ON DELETE SET NULL,
    source_url          TEXT NOT NULL,
    source_lang         TEXT,                                 -- detected source language
    target_lang         TEXT,                                 -- target language code ('none' for download)
    status              TEXT NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','downloading','transcribing',
                                          'translating','burning','uploading',
                                          'done','error')),
    error_msg           TEXT,
    mode                TEXT NOT NULL DEFAULT 'translate'
                        CHECK (mode IN ('translate', 'download')),
    download_only       BOOLEAN NOT NULL DEFAULT FALSE,
    title               TEXT,
    original_filename   TEXT,
    duration_s          INTEGER,                              -- video duration in seconds
    video_type          TEXT DEFAULT 'short',                  -- 'short','medium','long','extra_long'
    video_width         INTEGER,
    video_height        INTEGER,
    storage_url         TEXT,                                 -- final output storage URL
    storage_key         TEXT,                                 -- S3/storage key
    thumbnail_url       TEXT,
    source_storage_url  TEXT,                                 -- original video storage URL
    source_sub_url      TEXT,                                 -- original subtitle URL (if any)
    summary             TEXT,
    summaries           JSONB DEFAULT '{}',                   -- LLM summaries per segment
    cost_breakdown      JSONB DEFAULT '{}',                   -- wallet, subvox_deducted, splits
    processed_steps     JSONB DEFAULT '{}',                   -- pipeline step tracking
    step_timings        JSONB DEFAULT '{}',                   -- duration per pipeline step
    step_data           JSONB DEFAULT '{}',
    source_info         JSONB DEFAULT '{}',
    subtitle_info       JSONB DEFAULT '{}',
    processing_log      JSONB DEFAULT '[]',                   -- structured log entries
    job_metrics         JSONB DEFAULT '{}',                   -- quality/complexity metrics
    video_category      TEXT DEFAULT 'short',
    download_count      INTEGER NOT NULL DEFAULT 0,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    visitor_token       UUID,                                 -- anonymous session token
    visibility          TEXT NOT NULL DEFAULT 'public'
                        CHECK (visibility IN ('public', 'private', 'unlisted')),
    seo_slug            TEXT,
    seo_metadata        JSONB DEFAULT '{}',
    group_id            UUID,                                 -- multi-video group (X/Twitter threads, playlists)
    celery_task_id      TEXT,                                 -- Celery async task reference
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at         TIMESTAMPTZ
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_source_url ON jobs(source_url);
CREATE INDEX IF NOT EXISTS idx_jobs_target_lang ON jobs(target_lang);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_group_id ON jobs(group_id);
CREATE INDEX IF NOT EXISTS idx_jobs_seo_slug ON jobs(seo_slug);
CREATE INDEX IF NOT EXISTS idx_jobs_archived ON jobs(archived_at) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_feed ON jobs(created_at DESC, status, target_lang)
    WHERE archived_at IS NULL AND target_lang IS NOT NULL AND target_lang != 'none';

-- ═══════════════════════════════════════════════════════════════════
-- 3. TRANSCRIPTION SEGMENTS (for re-use across jobs)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS transcription_segments (
    id              BIGSERIAL PRIMARY KEY,
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    segment_index   INTEGER NOT NULL,
    start_time_s    DOUBLE PRECISION NOT NULL,
    end_time_s      DOUBLE PRECISION NOT NULL,
    text            TEXT NOT NULL,
    confidence      DOUBLE PRECISION,
    speaker_id      TEXT,
    language        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ts_job_id ON transcription_segments(job_id);
CREATE INDEX IF NOT EXISTS idx_ts_job_order ON transcription_segments(job_id, segment_index);

-- ═══════════════════════════════════════════════════════════════════
-- 4. USER GROQ / PROVIDER KEYS
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_groq_keys (
    user_id             TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    groq_key_hash       TEXT,
    groq_key_enc        TEXT,
    deepseek_key_hash   TEXT,
    deepseek_key_enc    TEXT,
    openrouter_key_hash TEXT,
    openrouter_key_enc  TEXT,
    is_valid            BOOLEAN NOT NULL DEFAULT FALSE,
    daily_usage_s       INTEGER NOT NULL DEFAULT 0,
    usage_date          DATE,
    validated_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ugk_valid ON user_groq_keys(is_valid) WHERE is_valid = TRUE;

-- ═══════════════════════════════════════════════════════════════════
-- 5. SUBSCRIPTIONS
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id                   TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    plan                      TEXT DEFAULT 'decouverte',
    tier                      TEXT DEFAULT 'decouverte',        -- decouverte, passion, builder
    role                      TEXT DEFAULT 'user',
    credits_remaining         BIGINT DEFAULT 0,
    subvox_balance_snapshot   BIGINT,
    groq_key_active           BOOLEAN DEFAULT FALSE,
    daily_translation_limit   INTEGER DEFAULT 3,
    period_end                TIMESTAMPTZ,
    watermark_text            TEXT DEFAULT 'Subvox',
    watermark_paid            BOOLEAN DEFAULT FALSE,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_tier ON subscriptions(tier);

-- ═══════════════════════════════════════════════════════════════════
-- 6. MISSIONS (reward system)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS missions (
    id                SERIAL PRIMARY KEY,
    slug              TEXT NOT NULL UNIQUE,
    title             TEXT NOT NULL,
    title_en          TEXT,
    description       TEXT,
    description_en    TEXT,
    instructions      TEXT,
    instructions_en   TEXT,
    mission_type      TEXT NOT NULL DEFAULT 'social',          -- 'social', 'api_key', 'onboarding'
    difficulty        TEXT DEFAULT 'easy',                     -- 'easy', 'medium', 'hard'
    reward_amount     BIGINT NOT NULL DEFAULT 500,
    reward_currency   TEXT NOT NULL DEFAULT 'SUBTEST',
    max_claimants     INTEGER DEFAULT 25,
    current_claimants INTEGER NOT NULL DEFAULT 0,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_missions_active ON missions(is_active, sort_order);

-- ═══════════════════════════════════════════════════════════════════
-- 7. USER MISSIONS (claim tracking)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS user_missions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mission_id      INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'submitted'
                    CHECK (status IN ('submitted', 'pending_verification',
                                      'verified', 'rejected', 'claimed')),
    proof_data      JSONB DEFAULT '{}',
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, mission_id)
);

CREATE INDEX IF NOT EXISTS idx_um_user ON user_missions(user_id);
CREATE INDEX IF NOT EXISTS idx_um_status ON user_missions(status);

-- ═══════════════════════════════════════════════════════════════════
-- 8. WELCOME MISSIONS (first-time bonus)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS welcome_missions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at      TIMESTAMPTZ NOT NULL,
    claimed_at      TIMESTAMPTZ,
    claim_tx        TEXT,
    claim_amount    BIGINT,
    bonus_credited  BOOLEAN DEFAULT FALSE,
    tweet_url       TEXT,
    x_username      TEXT,
    tweet_verified_at TIMESTAMPTZ,
    tweet_checked   BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

-- ═══════════════════════════════════════════════════════════════════
-- 9. PLATFORM CREDENTIALS (cookies for scraping)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS platform_credentials (
    id                BIGSERIAL PRIMARY KEY,
    user_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform_slug     TEXT NOT NULL,                           -- 'youtube', 'twitter', 'tiktok'
    cookies_encrypted TEXT NOT NULL,
    is_shared         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, platform_slug)
);

CREATE INDEX IF NOT EXISTS idx_pc_user ON platform_credentials(user_id);

-- ═══════════════════════════════════════════════════════════════════
-- 10. CREDENTIAL USAGE (track which job used which credential)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS credential_usage (
    id              BIGSERIAL PRIMARY KEY,
    credential_id   BIGINT NOT NULL REFERENCES platform_credentials(id) ON DELETE CASCADE,
    job_id          UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cu_credential ON credential_usage(credential_id);
CREATE INDEX IF NOT EXISTS idx_cu_job ON credential_usage(job_id);

-- ═══════════════════════════════════════════════════════════════════
-- 11. SUBVOX TOKEN HOLDERS (on-chain balance cache)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS subvox_token_holders (
    wallet_address TEXT PRIMARY KEY,
    balance        BIGINT NOT NULL DEFAULT 0,
    staked_amount  BIGINT NOT NULL DEFAULT 0,
    total_earned   BIGINT NOT NULL DEFAULT 0,
    total_spent    BIGINT NOT NULL DEFAULT 0,
    last_snapshot_at TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════════
-- 12. SUBVOX TRANSACTIONS (token economy log)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS subvox_transactions (
    id          BIGSERIAL PRIMARY KEY,
    from_wallet TEXT,
    to_wallet   TEXT,
    amount      BIGINT NOT NULL,
    tx_type     TEXT NOT NULL,                                 -- 'translation_payment', 'holder_reward',
                                                                -- 'groq_provider_payout', 'platform_fee',
                                                                -- 'subtest_payment', 'burn'
    metadata    JSONB DEFAULT '{}',
    job_id      UUID REFERENCES jobs(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stx_from ON subvox_transactions(from_wallet);
CREATE INDEX IF NOT EXISTS idx_stx_to ON subvox_transactions(to_wallet);
CREATE INDEX IF NOT EXISTS idx_stx_type ON subvox_transactions(tx_type);
CREATE INDEX IF NOT EXISTS idx_stx_created ON subvox_transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stx_job ON subvox_transactions(job_id);

-- ═══════════════════════════════════════════════════════════════════
-- 13. SUBVOX GROQ POOL (shared provider keys)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS subvox_groq_pool (
    wallet_address   TEXT PRIMARY KEY REFERENCES subvox_token_holders(wallet_address),
    groq_key_hash    TEXT NOT NULL,
    groq_key_enc     TEXT NOT NULL,
    daily_limit_s    INTEGER NOT NULL DEFAULT 1800,
    personal_ratio   INTEGER NOT NULL DEFAULT 50,             -- % reserved for owner
    shared_ratio     INTEGER NOT NULL DEFAULT 50,             -- % shared in community pool
    personal_used_s  INTEGER NOT NULL DEFAULT 0,
    shared_used_s    INTEGER NOT NULL DEFAULT 0,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_validated_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sgp_active ON subvox_groq_pool(is_active) WHERE is_active = TRUE;

-- ═══════════════════════════════════════════════════════════════════
-- 14. SUBVOX PRICING (configurable rate card)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS subvox_pricing (
    id             SERIAL PRIMARY KEY,
    video_type     TEXT NOT NULL,                              -- 'short', 'medium', 'long', 'extra_long'
    min_duration_s INTEGER NOT NULL,
    max_duration_s INTEGER NOT NULL,
    price_subvox   BIGINT NOT NULL,
    label          TEXT NOT NULL,
    label_en       TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO subvox_pricing (video_type, min_duration_s, max_duration_s, price_subvox, label, label_en) VALUES
    ('short',       0,   120,  10,  '< 2 min',    '< 2 min'),
    ('medium',    120,   300,  25,  '2-5 min',    '2-5 min'),
    ('long',      300,   900,  50,  '5-15 min',   '5-15 min'),
    ('extra_long', 900, 1800, 100,  '15-30 min',  '15-30 min')
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 15. PLATFORMS (supported video sources)
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS platforms (
    slug          TEXT PRIMARY KEY,                            -- 'youtube', 'twitter', 'tiktok', etc.
    name          TEXT NOT NULL,
    name_en       TEXT,
    seo_title     TEXT,
    seo_title_en  TEXT,
    icon_url      TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO platforms (slug, name, name_en, seo_title, seo_title_en) VALUES
    ('youtube',     'YouTube',     'YouTube',     'YouTube',     'YouTube'),
    ('twitter',     'X / Twitter', 'X / Twitter', 'X / Twitter', 'X / Twitter'),
    ('tiktok',      'TikTok',      'TikTok',      'TikTok',      'TikTok'),
    ('instagram',   'Instagram',   'Instagram',   'Instagram',   'Instagram'),
    ('vimeo',       'Vimeo',       'Vimeo',       'Vimeo',       'Vimeo'),
    ('dailymotion', 'Dailymotion', 'Dailymotion', 'Dailymotion', 'Dailymotion')
ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════
-- 16. SCHEMA MIGRATIONS TRACKER
-- ═══════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    hash        TEXT NOT NULL,                                  -- SHA-256 of migration file
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms INTEGER NOT NULL DEFAULT 0
);

-- ═══════════════════════════════════════════════════════════════════
-- Auto-update `updated_at` trigger (all tables)
-- ═══════════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to all tables with updated_at
DO $$
DECLARE
    tbl text;
BEGIN
    FOR tbl IN
        SELECT unnest(ARRAY[
            'users', 'jobs', 'subscriptions', 'missions', 'user_missions',
            'platform_credentials', 'subvox_token_holders', 'subvox_groq_pool',
            'subvox_pricing', 'platforms'
        ])
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%s_updated_at BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()',
            tbl, tbl
        );
    END LOOP;
END;
$$;

-- Record this migration
INSERT INTO schema_migrations (version, name, hash, duration_ms)
VALUES (0, 'schema.sql', 'initial-full-schema', 0)
ON CONFLICT (version) DO NOTHING;
