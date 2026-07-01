<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>O mecanismo open-source de tradução de vídeo.</strong><br/>
  Baixar. Transcrever. Traduzir. Incorporar. Um pipeline, qualquer idioma.
</p>

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🇬🇧-English-blue" alt="English"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/🇫🇷-Français-blue" alt="Français"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/🇪🇸-Español-green" alt="Español"></a>
  <a href="README.pt.md"><img src="https://img.shields.io/badge/🇵🇹-Português-brightgreen" alt="Português"></a>
  <a href="README.de.md"><img src="https://img.shields.io/badge/🇩🇪-Deutsch-orange" alt="Deutsch"></a>
  <a href="README.it.md"><img src="https://img.shields.io/badge/🇮🇹-Italiano-red" alt="Italiano"></a>
  <a href="README.nl.md"><img src="https://img.shields.io/badge/🇳🇱-Nederlands-brightblue" alt="Nederlands"></a>
  <a href="README.pl.md"><img src="https://img.shields.io/badge/🇵🇱-Polski-purple" alt="Polski"></a>
  <a href="README.ru.md"><img src="https://img.shields.io/badge/🇷🇺-Русский-purple" alt="Русский"></a>
  <a href="README.uk.md"><img src="https://img.shields.io/badge/🇺🇦-Українська-yellow" alt="Українська"></a>
  <a href="README.ar.md"><img src="https://img.shields.io/badge/🇸🇦-العربية-lightgrey" alt="العربية"></a>
  <a href="README.hi.md"><img src="https://img.shields.io/badge/🇮🇳-हिन्दी-orange" alt="हिन्दी"></a>
  <a href="README.fa.md"><img src="https://img.shields.io/badge/🇮🇷-فارسی-green" alt="فارسی"></a>
  <a href="README.he.md"><img src="https://img.shields.io/badge/🇮🇱-עברית-blue" alt="עברית"></a>
  <a href="README.zh.md"><img src="https://img.shields.io/badge/🇨🇳-中文-critical" alt="中文"></a>
  <a href="README.ja.md"><img src="https://img.shields.io/badge/🇯🇵-日本語-blueviolet" alt="日本語"></a>
  <a href="README.ko.md"><img src="https://img.shields.io/badge/🇰🇷-한국어-brightblue" alt="한국어"></a>
  <a href="README.tr.md"><img src="https://img.shields.io/badge/🇹🇷-Türkçe-red" alt="Türkçe"></a>
  <a href="README.vi.md"><img src="https://img.shields.io/badge/🇻🇳-Tiếng Việt-brightgreen" alt="Tiếng Việt"></a>
  <a href="README.id.md"><img src="https://img.shields.io/badge/🇮🇩-Bahasa Indonesia-red" alt="Bahasa Indonesia"></a>
</p>

<p align="center">
  <a href="README.fr.md"><img src="https://img.shields.io/badge/🇫🇷-Français-blue" alt="Français"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/🇪🇸-Español-green" alt="Español"></a>
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

> Tenho 35 anos. Durante 10 anos geri uma empresa. Depois descobri a tecnologia.
>
> Não foi uma mudança de carreira. Foi uma revelação. A capacidade de construir, a partir do meu terminal, ferramentas que cruzam fronteiras.
>
> Subvox nasceu desta obsessão: e se pudesses pegar em qualquer vídeo, um discurso político coreano, um tutorial alemão, uma conferência árabe, e torná-lo acessível na tua língua materna, em minutos, sem perder a voz, o tom, a intenção?
>
> Subvox é também sobre contribuir como comunidade para tornar a tradução de vídeo acessível a todos. Ao contrário do **Veed.io**, **Kapwing**, **Descript** ou **Opus Clip**, gigantes que cobram uma fortuna pelo que deveria ser gratuito e que limitam muito. Subvox é aberto, transparente e construído por quem o utiliza.
>
> É um projeto a solo, construído commit a commit, porque acredito que a tecnologia deve pertencer a todos. Não apenas a quem fala inglês.
>
> Este pipeline é o coração técnico. O resto, wallets, tokens, economia, vive noutro lugar. Aqui está a máquina de traduzir o mundo. Livre. Aberto. Teu.
>
> *Nansou*

---

## 🎯 Features

| Step | Description |
|---|---|
| **⬇️ Download** | Obtém vídeo do X/Twitter, YouTube ou URL direta |
| **🎙️ Transcribe** | Transcrição de áudio via Groq (Whisper), 20+ idiomas |
| **🌐 Translate** | Tradução LLM (DeepSeek / OpenAI) para o idioma de destino |
| **🎬 Burn** | Incrustação de legendas no vídeo (ffmpeg/libass) |
| **☁️ Upload** | Armazenamento local ou S3 do resultado final |

**Bónus:** Exportação VTT/SRT, watermark automático, deteção de cenas, análise de conteúdo.

---

## 🎬 O pipeline visto pelo utilizador

```
1. Colas um link de vídeo
   │  YouTube, X/Twitter, TikTok, Instagram, Facebook...
   │  O validador verifica em 2 segundos se é acessível
   ▼
2. Download
   │  yt-dlp obtém o vídeo (até 4K)
   ▼
3. Transcrição de áudio
   │  Groq Whisper converte áudio em texto
   │  Suporta 20+ idiomas
   ▼
4. Tradução
   │  DeepSeek / OpenAI traduz as legendas
   │  No idioma à tua escolha
   ▼
5. Incrustação
   │  ffmpeg + libass incrustam as legendas no vídeo
   │  Watermark automático, estilo personalizável
   ▼
6. Resultado
   │  Vídeo legendado, pronto para partilhar
   │  Exportação SRT/VTT disponível
```

**Tempo total:** 2-5 minutos para um vídeo de 3 minutos.
**Sem necessidade de programar.** Cola um link, escolhe um idioma, obtém um vídeo traduzido.

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

### Com Docker (recomendado)

```bash
# 1. Clone
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline

# 2. Iniciar todo o stack
export GROQ_API_KEY="tua_chave_groq"
export DEEPSEEK_API_KEY="tua_chave_deepseek"
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

| Rota | Método | Descrição |
|---|---|---|
| `/jobs/feed` | GET | Últimas traduções públicas |
| `/jobs/{id}/status` | GET | Estado do trabalho |
| `/jobs/{id}/subtitles` | GET | Legendas geradas |
| `/health` | GET | Health check |

A autenticação e gestão de tokens são tratadas por um serviço dedicado (privado).

---

## 🧩 Stack

| Componente | Tecnologia |
|---|---|
| API | Python 3.14 / FastAPI |
| Queue | Celery + Redis |
| Video | FFmpeg 7 |
| Transcription | Groq (Whisper) |
> **Nota:** A Groq oferece 2 horas de transcrição gratuita por dia. Perfeito para desenvolvimento e pequenos projetos.
| Tradução | DeepSeek / OpenAI |
| DB | PostgreSQL 16 |

---

## 🤝 Contributing

Este projeto é jovem e construído por uma só pessoa. Toda a contribuição é bem-vinda:

- **Issues**: reporta um erro, sugere uma funcionalidade
- **PRs**: código, docs, testes, tudo ajuda
- **Discussões**: partilha o teu caso de uso

O pipeline é **100% open-source** (MIT). A camada económica (wallets, tokens) permanece privada por razões de segurança.

---

## 🙏 Agradecimentos

Subvox Pipeline baseia-se em projetos open-source essenciais:

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Groq](https://groq.com) · [DeepSeek](https://deepseek.com) · [OpenAI](https://openai.com) · [FFmpeg](https://ffmpeg.org) · [FastAPI](https://fastapi.tiangolo.com) · [Celery](https://docs.celeryq.dev) · [Redis](https://redis.io) · [PostgreSQL](https://postgresql.org)

---

## 📄 License

MIT,  feito com ❤️ por [Nansou](https://github.com/Nansouoouu)
