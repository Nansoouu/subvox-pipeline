-- ═══════════════════════════════════════════════════════════════════
-- 038_reward_claims_unified.sql — Table unique + early adopters
-- ═══════════════════════════════════════════════════════════════════

-- Table unique pour tous les rewards en attente de claim manuel
CREATE TABLE IF NOT EXISTS reward_claims (
    id              BIGSERIAL PRIMARY KEY,
    wallet_address  TEXT NOT NULL,
    reward_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    reward_type     TEXT NOT NULL CHECK (reward_type IN (
                        'provider_daily',
                        'platform_test',
                        'early_adopter',
                        'early_provider',
                        'platform_test_mission'
                    )),
    amount          BIGINT NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'SUBVOX',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'claimed', 'expired')),
    reference_id    BIGINT,          -- id dans la table source (platform_test_urls, missions, etc.)
    metadata        JSONB DEFAULT '{}',
    claimed_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (reward_date, wallet_address, reward_type, reference_id)
);

CREATE INDEX IF NOT EXISTS idx_rc_wallet   ON reward_claims(wallet_address, status);
CREATE INDEX IF NOT EXISTS idx_rc_date     ON reward_claims(reward_date);
CREATE INDEX IF NOT EXISTS idx_rc_type     ON reward_claims(reward_type);
CREATE INDEX IF NOT EXISTS idx_rc_pending  ON reward_claims(status) WHERE status = 'pending';

-- Early adopters : 150 premiers jobs done
CREATE TABLE IF NOT EXISTS early_adopters (
    id              BIGSERIAL PRIMARY KEY,
    wallet_address  TEXT NOT NULL,
    rank            INTEGER NOT NULL,   -- 1 à 150
    job_id          UUID REFERENCES jobs(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (wallet_address)
);

CREATE INDEX IF NOT EXISTS idx_ea_rank ON early_adopters(rank);

-- Record migration
INSERT INTO schema_migrations (version, name, hash, duration_ms)
VALUES (38, '038_reward_claims_unified.sql', 'reward-claims-unified-early-adopters', 0)
ON CONFLICT (version) DO NOTHING;
