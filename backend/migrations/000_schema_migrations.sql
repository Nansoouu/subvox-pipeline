-- ─────────────────────────────────────────────────────────────
-- migration_000_schema_migrations.sql
-- Table de suivi des migrations appliquées au schéma.
-- ─────────────────────────────────────────────────────────────
-- S'inspire de Flyway : chaque migration est enregistrée avec
-- son numéro de version, son nom, et son hash SHA-256 pour
-- détecter les modifications non autorisées d'une migration
-- déjà appliquée.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    hash        TEXT NOT NULL,  -- SHA-256 du fichier au moment de l'application
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_ms INTEGER NOT NULL DEFAULT 0  -- temps d'exécution
);