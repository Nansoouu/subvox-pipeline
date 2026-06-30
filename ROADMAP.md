# Roadmap Subvox Pipeline

Vision : un pipeline de traduction vidéo open-source, décentralisé, où les contributeurs sont récompensés en tokens.

---

## 🎯 Phase 1 — Fondations solides (maintenant)

*Ce qui est fait et ce qui manque pour que le projet soit crédible.*

| Priorité | Sujet | Ce qu'il manque | Effort |
|---|---|---|---|
| 🔴 P0 | **Clé DeepSeek / Groq** | Clés API dans l'env du worker (fait) | ✅ |
| 🔴 P0 | **Pipeline bout en bout** | Marche en local (vérifié) | ✅ |
| 🟡 P1 | **Tests automatisés** | Aucun test pour l'instant | 2j |
| 🟡 P1 | **CI fonctionnelle** | .github/workflows/ci.yml existe mais pytest échoue (pas de tests) | 1j |
| 🟡 P1 | **Docker Compose** | Démarrer tout le stack en 1 commande (`docker compose up`) | 1j |
| 🟢 P2 | **Documentation API** | Swagger auto-généré ✅ mais docs manuelles manquantes | 1j |
| 🟢 P2 | **Exemples d'utilisation** | Scripts d'exemple pour utiliser l'API | 0.5j |
| 🟢 P2 | **Badges README** | License, Python, build status | 0.5j |

**Total Phase 1 : ~6 jours** pour un contributeur motivé.

---

## 🚀 Phase 2 — Features clés (prochain  mois)

*Ce qui transforme le projet en outil utilisable par tout le monde.*

| Priorité | Sujet | Description |
|---|---|---|
| 🔴 P0 | **Support YouTube / Vimeo / Dailymotion** | Aujourd'hui uniquement X.com — manque yt-dlp complet |
| 🔴 P0 | **Traduction sans clé DeepSeek** | Fallback vers un modèle open-source (LLaMA local) |
| 🟡 P1 | **File d'attente visible** | Interface web pour voir l'état des jobs en cours |
| 🟡 P1 | **Annulation de job** | Pouvoir stopper une traduction en cours |
| 🟡 P1 | **Export SRT/VTT seul** | Pouvoir télécharger les sous-titres sans la vidéo |
| 🟢 P2 | **Multilingue simultané** | Traduire en 5+ langues en un clic |
| 🟢 P2 | **Détection auto de la langue source** | Deviner la langue de la vidéo avant traduction |

**Total Phase 2 : ~15 jours** avec un contributeur à temps partiel.

---

## 🌟 Phase 3 — Écosystème (3-6 mois)

*Ce qui fait du projet une plateforme.*

| Sujet | Description |
|---|---|
| **Plugin System** | Permettre à n'importe qui d'ajouter un moteur de traduction |
| **Webhook API** | Notifier les apps externes quand une traduction est prête |
| **Cache intelligent** | Ne pas re-transcrire une vidéo déjà faite |
| **CLI officiel** | `pip install subvox` → traduire depuis le terminal |
| **Rewards program** | Contributors récompensés en SUBVOX |

---

## 🪙 Token Rewards — Comment ça marcherait

L'idée : **récompenser les contributeurs avec des SUBTEST (devnet)**.

### Le système

```
1. Un contributeur ouvre une Issue ou PR
2. On évalue la difficulté : ⭐ = 10 SUBTEST, ⭐⭐ = 50, ⭐⭐⭐ = 200
3. Si la PR est mergée → le contributeur reçoit les tokens
4. Les tokens sont crédités dans subvox_token_holders
5. Le contributeur peut les utiliser pour lancer des traductions
```

### Mapping tâches → tokens

| Tâche | Difficulté | Tokens |
|---|---|---|
| Ajouter une langue | ⭐ | 10 |
| Écrire des tests | ⭐ | 10 |
| Corriger un bug simple | ⭐ | 15 |
| Ajouter une feature mineure | ⭐⭐ | 50 |
| Implémenter le cache | ⭐⭐ | 75 |
| Support YouTube complet | ⭐⭐⭐ | 200 |
| Migration async worker | ⭐⭐⭐ | 300 |
| Plugin system | ⭐⭐⭐ | 500 |

### Pourquoi ça marche

- **Le contributeur** gagne des tokens qu'il peut utiliser ou revendre
- **Le projet** avance gratuitement (les tokens n'ont pas de valeur réelle en devnet)
- **La communauté** se crée autour d'une économie partagée
- **L'utilisateur** voit un projet actif avec des contributeurs réguliers

### Ce qu'il faut coder

1. Un endpoint `POST /rewards/contribution` (privé, réservé à toi)
2. Une UI pour associer wallet GitHub → wallet Solana
3. Une page "Hall of Fame" qui liste les contributeurs et leurs récompenses

---

## 📊 Synthèse — Ce qu'on pourrait demander comme aide

| Type d'aide | Où la demander | Idéal pour |
|---|---|---|
| **Tests** | Issues "good first issue" | Débutants |
| **Nouvelles features** | Issues "help wanted" | Intermédiaires |
| **Revue de code** | PRs | Confirmés |
| **Documentation** | README + Wiki | Tous niveaux |
| **Traduction** | i18n du README | Multilingues |
| **Design** | Logo, bannières, screenshots | Créatifs |
| **Infra** | Docker, CI/CD | DevOps |

---

*Cette roadmap est vivante — elle évolue avec les retours et les contributions.*
