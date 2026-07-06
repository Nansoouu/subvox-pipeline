-- ═══════════════════════════════════════════════════════════════════
-- 036_platform_test_missions.sql — Infrastructure platform tests
-- ═══════════════════════════════════════════════════════════════════

-- 1. Ajouter des colonnes à la table missions pour le cycle 15j
ALTER TABLE missions ADD COLUMN IF NOT EXISTS requirements   JSONB DEFAULT '{}';
ALTER TABLE missions ADD COLUMN IF NOT EXISTS starts_at      TIMESTAMPTZ;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS ends_at        TIMESTAMPTZ;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS repeat_every_days INTEGER;
ALTER TABLE missions ADD COLUMN IF NOT EXISTS proof_type     TEXT DEFAULT 'url';  -- 'url', 'text', 'screenshot', 'twitter_handle', 'api_key'

-- Index pour requêtes temporelles (missions actives à une date donnée)
CREATE INDEX IF NOT EXISTS idx_missions_starts_ends ON missions(starts_at, ends_at) WHERE starts_at IS NOT NULL;

-- 2. Table des URLs de test de plateforme
CREATE TABLE IF NOT EXISTS platform_test_urls (
    id              BIGSERIAL PRIMARY KEY,
    platform_slug   TEXT NOT NULL REFERENCES platforms(slug),
    video_type      TEXT NOT NULL CHECK (video_type IN ('short', 'medium', 'long')),
    url             TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'curator', 'auto')),
    submitted_by    TEXT REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'verified', 'broken', 'timeout')),
    last_checked_at TIMESTAMPTZ,
    last_http_code  INTEGER,
    job_id          UUID REFERENCES jobs(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (platform_slug, video_type, url)
);

CREATE INDEX IF NOT EXISTS idx_ptu_platform   ON platform_test_urls(platform_slug);
CREATE INDEX IF NOT EXISTS idx_ptu_status     ON platform_test_urls(status);
CREATE INDEX IF NOT EXISTS idx_ptu_job        ON platform_test_urls(job_id);

-- Trigger updated_at
CREATE TRIGGER trg_platform_test_urls_updated_at
    BEFORE UPDATE ON platform_test_urls
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Record migration
INSERT INTO schema_migrations (version, name, hash, duration_ms)
VALUES (36, '036_platform_test_missions.sql', 'platform-test-missions-infra', 0)
ON CONFLICT (version) DO NOTHING;
