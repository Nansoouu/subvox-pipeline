-- 039_retraduction_parent_job.sql
-- Ajoute parent_job_id pour les retraductions (Phase 3 - Revenue split)
-- Permet de tracker le job original d'une vidéo pour le revenue sharing
-- quand un autre utilisateur retraduit la même source.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS parent_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL;

-- Index pour chercher les retraductions par parent
CREATE INDEX IF NOT EXISTS idx_jobs_parent_job_id ON jobs(parent_job_id);

-- Index pour trouver le premier job d'une source (ordonné par created_at)
CREATE INDEX IF NOT EXISTS idx_jobs_source_first ON jobs(source_url, created_at ASC)
    WHERE status = 'done';
