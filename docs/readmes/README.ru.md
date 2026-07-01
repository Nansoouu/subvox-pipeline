<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>Движок перевода видео с открытым исходным кодом.</strong><br/>
  Загрузить. Расшифровать. Перевести. Встроить субтитры. Один конвейер, любой язык.
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
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#api">API</a> •
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/python-3.14-blue" alt="Python">
  <img src="https://img.shields.io/badge/FFmpeg-required-orange" alt="FFmpeg">
</p>

---


## История

> Мне 35 лет. 10 лет я вел бизнес. Затем я открыл для себя технологии.

Это не было сменой карьеры. Это было откровение. Возможность создавать, из моего терминала, инструменты, которые пересекают границы.

Subvox родился из этой одержимости: что если вы можете взять любое видео, корейскую политическую речь, немецкий учебник, арабскую конференцию, и сделать его доступным на вашем родном языке, за минуты, не теряя голос, тон, намерение?

Subvox также о вкладе сообщества в то, чтобы сделать перевод видео доступным для всех. В отличие от **Veed.io**, **Kapwing**, **Descript** или **Opus Clip**, гигантов, которые берут целое состояние за то, что должно быть бесплатным, которые ограничивают ваш экспорт, которые запирают вас в подписки. Subvox открыт, прозрачен и создан людьми, которые его используют.

Это сольный проект, построенный коммит за коммитом, потому что я верю, что технологии должны принадлежать всем. Не только тем, кто говорит по-английски.

Этот конвейер — техническое сердце. Остальное, кошельки, токены, экономика, живет в другом месте. Здесь — машина для перевода мира. Бесплатно. Открыто. Ваше.

---



## Возможности

| Шаг | Описание |
|-----|----------|
| **⬇️ Загрузка** | Загружает видео с X/Twitter, YouTube или прямого URL |
| **🎙️ Расшифровка** | Аудио транскрипция через Groq (Whisper), 20+ языков |
| **🌐 Перевод** | LLM перевод (DeepSeek / OpenAI) на целевой язык |
| **🎬 Встраивание** | Встраивание субтитров в видео (ffmpeg/libass) |
| **☁️ Загрузка** | Локальное или S3 хранение результата |

**Бонус:** Экспорт VTT/SRT, автоматический водяной знак, обнаружение сцен, анализ контента.

---

## Быстрый старт

### С Docker (рекомендуется)

```bash
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline
export GROQ_API_KEY="your_groq_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
docker compose up -d
curl http://localhost:8000/health
```

### Локальная разработка

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# → DATABASE_URL, REDIS_URL düzenleyin
uvicorn backend.main:app --reload --port 8000
```

---

## API

| Route | Method | Açıklama |
|-------|--------|----------|
| `/jobs/feed` | GET | Последние публичные переводы |
| `/jobs/{id}/status` | GET | Статус задачи |
| `/jobs/{id}/subtitles` | GET | Сгенерированные субтитры |
| `/health` | GET | Проверка здоровья |

---

## Стек

| Bileşen | Teknoloji |
|---------|-----------|
| API | Python 3.14 / FastAPI |
| Kuyruk | Celery + Redis |
| Video | FFmpeg 7 |
| Transkripsiyon | Groq (Whisper) |
| Çeviri | DeepSeek / OpenAI |
| DB | PostgreSQL 16 |

---

## Участие

Этот проект молодой и создается одним человеком. Любой вклад приветствуется:

- **Issues**: сообщите об ошибке, предложите функцию
- **PRs**: код, документация, тесты, всё помогает
- **Discussions**: поделитесь своим用例

Pipeline **полностью с открытым исходным кодом** (MIT). Ekonomi katmanı (cüzdanlar, tokenler) güvenlik nedeniyle özel kalır.

---

## 📄 License

MIT, made with ❤️ by [Nansou](https://github.com/Nansouoouu)
