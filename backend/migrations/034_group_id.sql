-- 034_group_id.sql
-- Groupe de jobs liés (multi-vidéo X/Twitter, playlists Youtube, etc.)
-- Permet de grouper N jobs créés à partir d'une même URL source contenant
-- plusieurs vidéos (ex: X thread avec /1, /2, /3)

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS group_id UUID;
CREATE INDEX IF NOT EXISTS idx_jobs_group_id ON jobs(group_id);
