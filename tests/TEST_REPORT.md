# Rapport E2E — 5 Personas — Juillet 2026

## Infrastructure

| Service | Port | Status |
|---------|------|--------|
| PostgreSQL | 5432 | OK |
| Redis | 6379 | OK |
| Economy API | 8001 | OK |
| Pipeline API | 8000 | OK |
| Frontend | 3002 | OK |
| Worker short (x4) | - | OK |
| Worker medium (x2) | - | OK |
| Worker long (x1) | - | OK |
| Worker xlong (x1) | - | OK |

**Capacite totale**: 8 jobs simultanes

## Structure des dossiers

```
~/Desktop/subvox/
  ├── economy/       → gh:Nansoouu/subvox-economy
  ├── pipeline/      → gh:Nansoouu/subvox-pipeline
  ├── frontend/      → gh:Nansoouu/subvox-frontend-app
  └── community/     → gh:Nansoouu/subvox (public)
```

Plus de `subvox-frontend/` et `subvox-community/` a la racine du Bureau.
Plus de `x-translator-mvp/`.
La racine `subvox/` n'est plus un repo git.

## Resultats des tests

### Phase 1 — Preflight (estimation duree + cout)
| Persona | Duree | Cout | Pool |
|---------|-------|------|------|
| Alice (YT 19s → FR) | 19s | 100 SUBVOX | community |
| Bob (YT 4min → ES) | 252s | 225 SUBVOX | personal |
| Charlie (download) | 19s | 45 SUBVOX | personal |
| Diana (anon → JA) | 19s | 100 SUBVOX | community |
| Eve (single vid) | 19s | 100 SUBVOX | community |
| **5/5 OK** | | | |

### Phase 2 — Source-languages
- Retourne les langues deja traduites pour une URL donnee
- Format: `{source_url, existing_languages: [{lang, created_at}], total_languages}`
- **5/5 OK**

### Phase 3 — By-source (deduplication)
- Groupe les jobs par source_url + target_lang
- Montre les jobs existants avant soumission
- **5/5 OK**

### Phase 4 — Submit (5 jobs, ~60s total)
| Persona | Job ID | Status | Queue | Cached |
|---------|--------|--------|-------|--------|
| Alice | 3f56dffa | queued | 7 | non |
| Bob | 49fac9af | queued | 8 | non |
| Charlie | f250d9c2 | queued | 9 | non |
| Diana | 06f564b5 | queued | 10 | non |
| Eve | c3bfbaef | queued | 11 | non |
| **5/5 OK** | | | | |

Chaque reponse inclut: `video_index`, `source_job_id`, `discount_applicable`, `group_id`, `subtest_payment`.

### Bug trouve et corrige
- `UndefinedColumnError: column "group_id" does not exist` — la migration 034_group_id.sql n'etait pas appliquee en local
- Fix: `ALTER TABLE jobs ADD COLUMN group_id UUID` sur la DB locale
- La migration est dans le repo pipeline/ mais doit etre jouee sur chaque environnement

### Points d'attention

1. **yt-dlp lent sur l'API** — chaque soumission appelle yt-dlp synchrone, ce qui bloque l'API ~5s. En production, il faudrait un cache ou un extract asynchrone.

2. **Groq rate limits non testes** — les workers sont configures avec la cle du pool, mais les limites reelles (429) n'ont pas ete atteintes avec 5 jobs.

3. **Le worker a besoin des vars d'env** — GROQ_API_KEY et DEEPSEEK_API_KEY doivent etre dans l'environnement du worker (via .env ou docker-compose).

4. **Migration DB** — toute nouvelle instance doit appliquer les migrations dans `pipeline/backend/migrations/`.

5. **Erreur .zshrc** — ligne 6 contient `n#` qui fait une erreur a chaque shell, peut causer des soucis avec les subprocess.
