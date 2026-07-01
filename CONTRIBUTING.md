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
| Ajouter une langue | 10 SUBTEST |
| Écrire des tests | 10 SUBTEST |
| Corriger un bug | 15 SUBTEST |
| Feature mineure | 50 SUBTEST |
| Cache transcription | 75 SUBTEST |
| Grosse feature | 200+ SUBTEST |

Les tokens sont crédités sur ton wallet Solana après merge de ta PR.
Ils te permettent de lancer des traductions sur la plateforme.

## 💬 Communication

- **Issues** : signalez un bug, proposez une idée
- **Discussions** : posez des questions sur l'architecture
- **PRs** : n'ayez pas peur, on review gentiment

---

Fait avec ❤️ par Nansou — le projet est jeune, toute aide est précieuse.
