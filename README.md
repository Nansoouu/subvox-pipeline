<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>The open-source video translation engine.</strong><br/>
  Download. Transcribe. Translate. Burn subtitles. One pipeline, any language.
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#api">API</a> •
  <a href="#contributing">Contributing</a>
</p>

<p align="center">  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/python-3.14-blue" alt="Python">
  <img src="https://img.shields.io/badge/FFmpeg-required-orange" alt="FFmpeg">
  <img src="https://img.shields.io/github/stars/Nansouoouu/subvox-pipeline?style=flat&color=yellow" alt="Stars">
  <img src="https://img.shields.io/github/issues/Nansouoouu/subvox-pipeline?style=flat&color=red" alt="Issues">
  <img src="https://img.shields.io/github/actions/workflow/status/Nansouoouu/subvox-pipeline/ci.yml?branch=main&label=CI" alt="CI">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker" alt="Docker">
</p>

---

## ✨ Story

> J'ai 35 ans. Pendant 10 ans, j'ai dirigé une entreprise. Puis j'ai découvert la tech.
>
> Ce n'était pas un pivot de carrière. C'était une révélation. La possibilité de construire, depuis mon terminal, des outils qui traversent les frontières.
>
> Subvox est né de cette obsession : et si on pouvait prendre n'importe quelle vidéo, un discours politique coréen, un tutoriel en allemand, une conférence en arabe, et la rendre accessible dans ta langue maternelle, en quelques minutes, sans perdre la voix, le ton, l'intention ?
>
> C'est un projet solo, bâti commit par commit, parce que je crois que la technologie devrait appartenir à tout le monde. Pas juste à ceux qui parlent anglais.
>
> Ce pipeline est le cœur technique. Le reste, wallets, tokens, économie, vit ailleurs. Ici, c'est la machine à traduire le monde. Libre. Gratuite. Ouverte.
>
> *Nansou*

---

## 🎯 Features

| Step | What it does |
|---|---|
| **⬇️ Download** | Récupère la vidéo depuis X/Twitter, YouTube, ou URL directe |
| **🎙️ Transcribe** | Transcription audio via Groq (Whisper), 20+ langues |
| **🌐 Translate** | Traduction LLM (DeepSeek / OpenAI) vers la langue cible |
| **🎬 Burn** | Incrustation des sous-titres dans la vidéo (ffmpeg/libass) |
| **☁️ Upload** | Stockage local ou S3 du résultat final |

**Bonus :** VTT/SRT export, watermark automatique, détection de scènes, analyse de contenu.

---

## 🎬 La pipeline vue par l'utilisateur

```
1. Tu colles un lien vidéo
   │  YouTube, X/Twitter, TikTok, Instagram, Facebook...
   │  Le validateur vérifie en 2 secondes si c'est accessible
   ▼
2. Téléchargement
   │  yt-dlp récupère la vidéo (jusqu'à 4K)
   ▼
3. Transcription audio
   │  Groq Whisper transforme l'audio en texte
   │  Supporte 20+ langues
   ▼
4. Traduction
   │  DeepSeek / OpenAI traduit les sous-titres
   │  Dans la langue de ton choix
   ▼
5. Incrustation
   │  ffmpeg + libass gravent les sous-titres dans la vidéo
   │  Watermark automatique, style personnalisable
   ▼
6. Résultat
   │  Vidéo sous-titrée, prête à partager
   │  Export SRT/VTT possible
```

**Temps total :** 2-5 minutes pour une vidéo de 3 minutes.
**Pas besoin de coder.** Tu colles un lien, tu choisis une langue, tu obtiens une vidéo traduite.

---

## 🏗 Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │────▶│   Pipeline  │────▶│   Economy   │
│  Next.js    │◀────│  FastAPI    │◀────│  FastAPI     │
│  :3002      │     │  :8000      │     │  :8001       │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │                    │
                    ┌──────▼──────┐      ┌──────▼──────┐
                    │   Redis     │      │  PostgreSQL │
                    │  (queue)    │      │  (auth/bill)│
                    └──────┬──────┘      └─────────────┘
                           │
                    ┌──────▼──────┐
                    │   Celery    │
                    │  (worker)   │
                    └─────────────┘
```

**Pipeline** = pure technique (ce repo). Appelle **Economy** via HTTP pour l'auth.

---

## 🚀 Quick Start

### Avec Docker (recommandé)

```bash
# 1. Clone
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline

# 2. Lancer tout le stack
export GROQ_API_KEY="votre_clé_groq"
export DEEPSEEK_API_KEY="votre_clé_deepseek"
docker compose up -d

# 3. Vérifier
curl http://localhost:8000/health
```

### Sans Docker (dev local)

```bash
# 1. Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Config
cp .env.example .env
# → Éditer DATABASE_URL, REDIS_URL

# 3. Run
uvicorn backend.main:app --reload --port 8000
```

---

## 📡 API

| Route | Méthode | Description |
|---|---|---|
| `/jobs/feed` | GET | Dernières traductions publiques |
| `/jobs/{id}/status` | GET | Statut d'un job |
| `/jobs/{id}/subtitles` | GET | Sous-titres générés |
| `/health` | GET | Health check |

L'authentification et la gestion des tokens sont gérées par un service dédié (privé).

---

## 🧩 Stack

| Composant | Technologie |
|---|---|
| API | Python 3.14 / FastAPI |
| Queue | Celery + Redis |
| Video | FFmpeg 7 |
| Transcription | Groq (Whisper) |
| Traduction | DeepSeek / OpenAI |
| DB | PostgreSQL 16 |

---

## 🤝 Contributing

Ce projet est jeune et construit par une seule personne. Toute contribution est la bienvenue :

- **Issues** : signalez un bug, proposez une feature
- **PRs** : code, docs, tests — tout est bon à prendre
- **Discussions** : partagez votre cas d'usage

Le pipeline est **100% open-source** (MIT). L'économie (wallets, tokens) reste privée pour des raisons de sécurité.

---

## 📄 License

MIT — fait avec ❤️ par [Nansou](https://github.com/Nansouoouu)
