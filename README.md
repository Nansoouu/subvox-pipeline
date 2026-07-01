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

<p align="center">
  <a href="README.fr.md"><img src="https://img.shields.io/badge/🇫🇷-Version%20française-blue" alt="Français"></a>
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

> I am 35. For 10 years I ran a business. Then I discovered tech.
>
> It was not a career pivot. It was a revelation. The ability to build, from my terminal, tools that cross borders.
>
> Subvox was born from this obsession: what if you could take any video, a Korean political speech, a German tutorial, an Arabic conference, and make it accessible in your native language, in minutes, without losing the voice, the tone, the intent?
>
> Subvox is also about contributing as a community to make video translation accessible to everyone. Unlike **Veed.io**, **Kapwing**, **Descript**, or **Opus Clip**, giants that charge a fortune for what should be free, that limit your exports, that lock you into subscriptions. Subvox is open, transparent, and built by the people who use it.
>
> This is a solo project, built commit by commit, because I believe technology should belong to everyone. Not just those who speak English.
>
> This pipeline is the technical heart. The rest, wallets, tokens, economy, lives elsewhere. Here, it is the machine to translate the world. Free. Open. Yours.
>
> *Nansou*

---

## 🎯 Features

| Step | Description |
|---|---|
| **⬇️ Download** | Fetches video from X/Twitter, YouTube, or direct URL |
| **🎙️ Transcribe** | Audio transcription via Groq (Whisper), 20+ languages |
| **🌐 Translate** | LLM translation (DeepSeek / OpenAI) to target language |
| **🎬 Burn** | Subtitle overlay into video (ffmpeg/libass) |
| **☁️ Upload** | Local or S3 storage of the final result |

**Bonus:** VTT/SRT export, auto watermark, scene detection, content analysis.

---

## 🎬 La pipeline vue par l'utilisateur

```
1. Paste a video link
   │  YouTube, X/Twitter, TikTok, Instagram, Facebook...
   │  Validator checks accessibility in 2 seconds
   ▼
2. Download
   │  yt-dlp fetches the video (up to 4K)
   ▼
3. Audio transcription
   │  Groq Whisper converts audio to text
   │  Supports 20+ languages
   ▼
4. Translation
   │  DeepSeek / OpenAI translates subtitles
   │  In the language of your choice
   ▼
5. Burn
   │  ffmpeg + libass burn subtitles into the video
   │  Auto watermark, customizable style
   ▼
6. Result
   │  Subtitled video, ready to share
   │  SRT/VTT export available
```

**Total time:** 2-5 minutes for a 3-minute video.
**No coding required.** Paste a link, pick a language, get a translated video.

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

**Pipeline** = pure tech (this repo). Calls **Economy** via HTTP for auth.

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

Authentication and token management are handled by a dedicated service (private).

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
- **PRs** : code, docs, tests ,  tout est bon à prendre
- **Discussions** : partagez votre cas d'usage

Le pipeline est **100% open-source** (MIT). L'économie (wallets, tokens) reste privée pour des raisons de sécurité.

---

## 🙏 Remerciements

Subvox Pipeline s'appuie sur des projets open-source essentiels :

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Groq](https://groq.com) · [DeepSeek](https://deepseek.com) · [OpenAI](https://openai.com)
[FFmpeg](https://ffmpeg.org) · [FastAPI](https://fastapi.tiangolo.com) · [Celery](https://docs.celeryq.dev) · [Redis](https://redis.io) · [PostgreSQL](https://postgresql.org)

---

## 📄 License

MIT ,  fait avec ❤️ par [Nansou](https://github.com/Nansouoouu)
