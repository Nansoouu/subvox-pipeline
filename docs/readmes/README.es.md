<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>El motor open-source de traducción de vídeo.</strong><br/>
  Descargar. Transcribir. Traducir. Incrustar. Una pipeline, cualquier idioma.
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#api">API</a> •
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🇬🇧-English-blue" alt="English"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/🇫🇷-Français-blue" alt="Français"></a>
  <a href="README.ja.md"><img src="https://img.shields.io/badge/🇯🇵-日本語-blue" alt="日本語"></a>
  <a href="README.zh.md"><img src="https://img.shields.io/badge/🇨🇳-中文-red" alt="中文"></a>
  <a href="README.de.md"><img src="https://img.shields.io/badge/🇩🇪-Deutsch-orange" alt="Deutsch"></a>
  <a href="README.it.md"><img src="https://img.shields.io/badge/🇮🇹-Italiano-blue" alt="Italiano"></a>
  <a href="README.ar.md"><img src="https://img.shields.io/badge/🇸🇦-العربية-green" alt="العربية"></a>
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

> Tengo 35 años. Durante 10 años dirigí una empresa. Luego descubrí la tecnología.
>
> No fue un cambio de carrera. Fue una revelación. La posibilidad de construir, desde mi terminal, herramientas que cruzan fronteras.
>
> Subvox nació de esta obsesión: ¿y si pudieras tomar cualquier vídeo, un discurso político coreano, un tutorial en alemán, una conferencia en árabe, y hacerlo accesible en tu idioma nativo, en minutos, sin perder la voz, el tono, la intención?
>
> Subvox también se trata de contribuir como comunidad para hacer accesible la traducción de vídeo para todos. A diferencia de **Veed.io**, **Kapwing**, **Descript** u **Opus Clip**, gigantes que cobran una fortuna por lo que debería ser gratuito y que limitan mucho. Subvox es abierto, transparente y construido por quienes lo usan.
>
> Es un proyecto en solitario, construido commit a commit, porque creo que la tecnología debería pertenecer a todos. No solo a quienes hablan inglés.
>
> Este pipeline es el corazón técnico. El resto, wallets, tokens, economía, vive en otro lado. Aquí está la máquina para traducir el mundo. Libre. Abierto. Tuyo.
>
> *Nansou*

---

## 🎯 Features

| Step | Description |
|---|---|
| **⬇️ Download** | Obtiene vídeo de X/Twitter, YouTube o URL directa |
| **🎙️ Transcribe** | Transcripción de audio via Groq (Whisper), 20+ idiomas |
| **🌐 Translate** | Traducción LLM (DeepSeek / OpenAI) al idioma destino |
| **🎬 Burn** | Incrustación de subtítulos en el vídeo (ffmpeg/libass) |
| **☁️ Upload** | Almacenamiento local o S3 del resultado final |

**Bonus:** Exportación VTT/SRT, watermark auto, detección de escenas, análisis de contenido.

---

## 🎬 La pipeline vista por el usuario

```
1. Pegas un enlace de vídeo
   │  YouTube, X/Twitter, TikTok, Instagram, Facebook...
   │  El validador comprueba en 2 segundos si es accesible
   ▼
2. Descarga
   │  yt-dlp obtiene el vídeo (hasta 4K)
   ▼
3. Transcripción de audio
   │  Groq Whisper convierte el audio a texto
   │  Soporta 20+ idiomas
   ▼
4. Traducción
   │  DeepSeek / OpenAI traduce los subtítulos
   │  En el idioma que elijas
   ▼
5. Incrustación
   │  ffmpeg + libass incrustan los subtítulos en el vídeo
   │  Watermark auto, estilo personalizable
   ▼
6. Resultado
   │  Vídeo subtitulado, listo para compartir
   │  Exportación SRT/VTT disponible
```

**Tiempo total:** 2-5 minutos para un vídeo de 3 minutos.
**Sin necesidad de programar.** Pega un enlace, elige un idioma, obtén un vídeo traducido.

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

### Con Docker (recomendado)

```bash
# 1. Clone
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline

# 2. Iniciar todo el stack
export GROQ_API_KEY="tu_clave_groq"
export DEEPSEEK_API_KEY="tu_clave_deepseek"
docker compose up -d

# 3. Verificar
curl http://localhost:8000/health
```

### Sans Docker (dev local)

```bash
# 1. Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Config
cp .env.example .env
# → Editar DATABASE_URL, REDIS_URL

# 3. Run
uvicorn backend.main:app --reload --port 8000
```

---

## 📡 API

| Ruta | Método | Descripción |
|---|---|---|
| `/jobs/feed` | GET | Últimas traducciones públicas |
| `/jobs/{id}/status` | GET | Estado del trabajo |
| `/jobs/{id}/subtitles` | GET | Subtítulos generados |
| `/health` | GET | Health check |

La autenticación y gestión de tokens son manejadas por un servicio dedicado (privado).

---

## 🧩 Stack

| Componente | Tecnología |
|---|---|
| API | Python 3.14 / FastAPI |
| Queue | Celery + Redis |
| Video | FFmpeg 7 |
| Transcription | Groq (Whisper) |
> **Nota:** Groq ofrece 2 horas de transcripción gratuita al día. Perfecto para desarrollo y proyectos pequeños.
| Traducción | DeepSeek / OpenAI |
| DB | PostgreSQL 16 |

---

## 🤝 Contributing

Este proyecto es joven y está construido por una sola persona. Toda contribución es bienvenida:

- **Issues**: reporta un error, sugiere una funcionalidad
- **PRs**: código, docs, tests, todo ayuda
- **Discusiones**: comparte tu caso de uso

El pipeline es **100% open-source** (MIT). La capa económica (wallets, tokens) permanece privada por razones de seguridad.

---

## 🙏 Agradecimientos

Subvox Pipeline se basa en proyectos open-source esenciales:

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Groq](https://groq.com) · [DeepSeek](https://deepseek.com) · [OpenAI](https://openai.com) · [FFmpeg](https://ffmpeg.org) · [FastAPI](https://fastapi.tiangolo.com) · [Celery](https://docs.celeryq.dev) · [Redis](https://redis.io) · [PostgreSQL](https://postgresql.org)

---

## 📄 License

MIT,  hecho con ❤️ por [Nansou](https://github.com/Nansouoouu)
