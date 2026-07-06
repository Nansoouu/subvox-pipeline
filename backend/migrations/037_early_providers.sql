-- ═══════════════════════════════════════════════════════════════════
-- 037_early_providers.sql — Pool providers, rank, multiplier
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE subvox_groq_pool ADD COLUMN IF NOT EXISTS rank              INTEGER;        -- 1-25 (early), NULL (late)
ALTER TABLE subvox_groq_pool ADD COLUMN IF NOT EXISTS joined_at         TIMESTAMPTZ DEFAULT now();
ALTER TABLE subvox_groq_pool ADD COLUMN IF NOT EXISTS multiplier        DECIMAL DEFAULT 1.0;
ALTER TABLE subvox_groq_pool ADD COLUMN IF NOT EXISTS total_pool_seconds BIGINT DEFAULT 0;

-- Suppression de l'ancienne limite fixe (définitivement)
ALTER TABLE subvox_groq_pool DROP COLUMN IF EXISTS daily_limit_s;

-- Table des snapshots journaliers
CREATE TABLE IF NOT EXISTS provider_daily_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    wallet_address  TEXT NOT NULL,
    rank            INTEGER,
    multiplier      DECIMAL DEFAULT 1.0,
    seconds_shared  BIGINT NOT NULL DEFAULT 0,     -- secondes fournies au pool ce jour
    seconds_used    BIGINT NOT NULL DEFAULT 0,      -- secondes utilisées (jobs)
    reward_subvox   BIGINT DEFAULT 0,               -- SUBVOX gagnés ce jour
    tx_sent         BOOLEAN DEFAULT FALSE,           -- reward déjà distribué on-chain
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_date, wallet_address)
);

CREATE INDEX IF NOT EXISTS idx_pds_date   ON provider_daily_snapshots(snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_pds_wallet ON provider_daily_snapshots(wallet_address);

-- Ajouter mission_type 'provider_early' dans la contrainte missions si nécessaire
-- (la colonne mission_type est TEXT sans CHECK, donc déjà compatible)

-- Record migration
INSERT INTO schema_migrations (version, name, hash, duration_ms)
VALUES (37, '037_early_providers.sql', 'early-providers-pool-snapshot', 0)
ON CONFLICT (version) DO NOTHING;
