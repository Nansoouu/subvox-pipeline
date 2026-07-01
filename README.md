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
  <a href="README.fr.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇫🇷-Français-blue" alt="Français"></a>
  <a href="README.es.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇪🇸-Español-green" alt="Español"></a>
  <a href="README.pt.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇵🇹-Português-brightgreen" alt="Português"></a>
  <a href="README.de.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇩🇪-Deutsch-orange" alt="Deutsch"></a>
  <a href="README.it.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇮🇹-Italiano-red" alt="Italiano"></a>
  <a href="README.ja.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇯🇵-日本語-blueviolet" alt="日本語"></a>
  <a href="README.zh.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇨🇳-中文-critical" alt="中文"></a>
  <a href="README.ar.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇸🇦-العربية-lightgrey" alt="العربية"></a>
</p>

<p align="center">
  <a href="docs/readmes/README.fr.md"><img src="https://img.shields.io/badge/🇫🇷-Français-blue" alt="Français"></a>
  <a href="docs/readmes/README.es.md"><img src="https://img.shields.io/badge/🇪🇸-Español-green" alt="Español"></a>
  <a href="docs/readmes/README.pt.md"><img src="https://img.shields.io/badge/🇵🇹-Português-brightgreen" alt="Português"></a>
  <a href="docs/readmes/README.de.md"><img src="https://img.shields.io/badge/🇩🇪-Deutsch-orange" alt="Deutsch"></a>
  <a href="docs/readmes/README.it.md"><img src="https://img.shields.io/badge/🇮🇹-Italiano-red" alt="Italiano"></a>
  <a href="docs/readmes/README.ja.md"><img src="https://img.shields.io/badge/🇯🇵-日本語-blueviolet" alt="日本語"></a>
  <a href="docs/readmes/README.zh.md"><img src="https://img.shields.io/badge/🇨🇳-中文-critical" alt="中文"></a>
  <a href="docs/readmes/README.ar.md"><img src="https://img.shields.io/badge/🇸🇦-العربية-lightgrey" alt="العربية"></a>
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

## 🎬 Pipeline walkthrough

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

### With Docker (recommended)

```bash
# 1. Clone
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline

# 2. Launch the full stack
export GROQ_API_KEY="your_groq_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
docker compose up -d

# 3. Check it
curl http://localhost:8000/health
```

### Sans Docker (dev local)

```bash
# 1. Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Config
cp .env.example .env
# → Edit DATABASE_URL, REDIS_URL

# 3. Run
uvicorn backend.main:app --reload --port 8000
```

---

## 📡 API

| Route | Method | Description |
|---|---|---|
| `/jobs/feed` | GET | Latest public translations |
| `/jobs/{id}/status` | GET | Job status |
| `/jobs/{id}/subtitles` | GET | Generated subtitles |
| `/health` | GET | Health check |

Authentication and token management are handled by a dedicated service (private).

---

## 🧩 Stack

| Component | Technology |
|---|---|
| API | Python 3.14 / FastAPI |
| Queue | Celery + Redis |
| Video | FFmpeg 7 |
| Transcription | Groq (Whisper) |
> **Note:** Groq offers 2 hours of free transcription per day. Perfect for development and small projects.
| Translation | DeepSeek / OpenAI |
| DB | PostgreSQL 16 |

---

## 🤝 Contributing

This project is young and built by one person. Every contribution is welcome:

- **Issues**: report a bug, suggest a feature
- **PRs**: code, docs, tests, everything helps
- **Discussions**: share your use case

The pipeline is **100% open-source** (MIT). The economy layer (wallets, tokens) stays private for security reasons.

---

## 🙏 Acknowledgments

Subvox Pipeline relies on essential open-source projects:

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Groq](https://groq.com) · [DeepSeek](https://deepseek.com) · [OpenAI](https://openai.com) · [FFmpeg](https://ffmpeg.org) · [FastAPI](https://fastapi.tiangolo.com) · [Celery](https://docs.celeryq.dev) · [Redis](https://redis.io) · [PostgreSQL](https://postgresql.org)

---

## 📄 License

MIT,  made with ❤️ by [Nansou](https://github.com/Nansouoouu)
