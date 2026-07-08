-- ═══════════════════════════════════════════════════════════════════
-- 035_platforms_extend.sql — Ajout des colonnes pour le frontend /features
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE platforms ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'untested'
    CHECK (status IN ('active', 'broken', 'untested', 'deprecated'));

ALTER TABLE platforms ADD COLUMN IF NOT EXISTS content_type  TEXT NOT NULL DEFAULT 'video'
    CHECK (content_type IN ('video', 'social', 'live', 'audio', 'gaming', 'news', 'adult', 'education'));

ALTER TABLE platforms ADD COLUMN IF NOT EXISTS website       TEXT;

ALTER TABLE platforms ADD COLUMN IF NOT EXISTS yt_dlp_extractor TEXT;

ALTER TABLE platforms ADD COLUMN IF NOT EXISTS importance    INTEGER NOT NULL DEFAULT 0;

ALTER TABLE platforms ADD COLUMN IF NOT EXISTS video_count   INTEGER NOT NULL DEFAULT 0;

-- Index pour les filtres
CREATE INDEX IF NOT EXISTS idx_platforms_status       ON platforms(status);
CREATE INDEX IF NOT EXISTS idx_platforms_content_type ON platforms(content_type);
CREATE INDEX IF NOT EXISTS idx_platforms_importance   ON platforms(importance DESC);

-- Record migration
INSERT INTO schema_migrations (version, name, hash, duration_ms)
VALUES (35, '035_platforms_extend.sql', 'extend-platforms-with-features-columns', 0)
ON CONFLICT (version) DO NOTHING;
