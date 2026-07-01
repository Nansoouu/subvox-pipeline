# Contributing to Subvox Pipeline

Hey ! Merci de t'intéresser au projet. Que tu sois débutant ou senior, y'a plein de façons d'aider.

## 🎯 Good First Issues

Pas besoin d'être expert. Voici ce qui serait utile :

### Pour les débutants en Python

| Tâche | Difficulté | Temps estimé |
|---|---|---|
| **Ajouter une langue** (ar, hi, etc.) dans `SUBTITLE_LANG_NAMES` | ⭐ | 10 min |
| **Écrire des tests** pour les endpoints `/health`, `/jobs/feed` | ⭐ | 30 min |
| **Améliorer les messages d'erreur** (remplacer les stack traces par du français clair) | ⭐ | 20 min |
| **Ajouter un badge** de build status dans le README | ⭐ | 10 min |

### Pour les développeurs Python intermédiaires

| Tâche | Difficulté | Temps estimé |
|---|---|---|
| **Remplacer les prints par du logging structuré** dans les étapes de pipeline | ⭐⭐ | 1h |
| **Ajouter un timeout configurable** aux appels Groq API | ⭐⭐ | 1h |
| **Implémenter le cache de transcription** (éviter de re-transcrire une vidéo déjà faite) | ⭐⭐ | 2h |
| **Ajouter le support des sous-titres SRT multi-langues** | ⭐⭐ | 2h |

### Pour les développeurs avancés

| Tâche | Difficulté | Temps estimé |
|---|---|---|
| **Migration vers async/await complet** dans le worker Celery | ⭐⭐⭐ | 4h |
| **Ajouter le support S3/AWS** pour le stockage des vidéos | ⭐⭐⭐ | 3h |
| **Implémenter le découpage automatique** des vidéos longues (>30 min) | ⭐⭐⭐ | 4h |
| **Dashboard de monitoring** des workers et files d'attente | ⭐⭐⭐ | 6h |

## 🚀 Workflow

```bash
# 1. Fork le projet sur GitHub
# 2. Clone ton fork
git clone https://github.com/ton-pseudo/subvox-pipeline.git
cd subvox-pipeline

# 3. Crée ta branche
git checkout -b feat/ma-contribution

# 4. Code, commit, push
git add .
git commit -m "feat(pipeline): ajoute le support de l'arabe"
git push origin feat/ma-contribution

# 5. Ouvre une Pull Request vers develop
```

## 📝 Convention de commits

```
type(scope): description

Types: feat, fix, docs, test, refactor, chore
Scope: pipeline, api, core, config, docs

Exemples:
  feat(pipeline): ajoute le watermark personnalisé
  fix(api): corrige le timeout sur les gros fichiers
  docs(readme): ajoute la section quickstart
```

## 🧪 Tester

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer les tests
pytest tests/
```

## 🪙 Rewards

Chaque contribution peut être récompensée en **SUBTEST** (tokens sur Solana devnet).

| Contribution | Tokens |
|---|---|
| Ajouter une langue | 100 SUBTEST |
| Écrire des tests | 100 SUBTEST |
| Corriger un bug | 150 SUBTEST |
| Feature mineure | 500 SUBTEST |
| Cache transcription | 750 SUBTEST |
| Grosse feature | 2000+ SUBTEST |

Les tokens sont crédités sur ton wallet Solana après merge de ta PR.
Ils font partie d'une **économie réelle** : les SUBTEST sont convertibles en SOL sur le réseau Solana (devnet).
Tu peux les utiliser pour lancer des traductions, les échanger, ou les conserver comme participation au projet.

## 💬 Communication

- **Issues** : signalez un bug, proposez une idée
- **Discussions** : posez des questions sur l'architecture
- **PRs** : n'ayez pas peur, on review gentiment

---

---

## 🙏 Remerciements

Ce projet n'existerait pas sans les projets open-source qui rendent tout possible :

| Projet | Ce qu'il apporte |
|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Téléchargement vidéo depuis 1872 sites |
| [Groq](https://groq.com) | Transcription audio Whisper ultra-rapide |
| [DeepSeek](https://deepseek.com) | Traduction LLM de qualité |
| [OpenAI](https://openai.com) | API de transcription et traduction |
| [FFmpeg](https://ffmpeg.org) | Incrustation des sous-titres et traitement vidéo |
| [FastAPI](https://fastapi.tiangolo.com) | Framework API Python |
| [Celery](https://docs.celeryq.dev) | File d'attente asynchrone |
| [Redis](https://redis.io) | Broker de messages |
| [PostgreSQL](https://postgresql.org) | Base de données |

---

> Contribuer plutôt que copier fait avancer le monde plus rapidement.
> La communauté open-source est la preuve qu'on va plus loin ensemble.
>
> Chaque PR, chaque issue, chaque retour compte.
> Tu n'es pas un utilisateur. Tu es un membre de la communauté.

Fait avec ❤️ par [Nansou](https://github.com/Nansoouu) — le projet est jeune, toute aide est précieuse.
