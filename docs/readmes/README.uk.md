<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>Рушій перекладу відео з відкритим кодом.</strong><br/>
  Завантажити. Розшифрувати. Перекласти. Вбудувати субтитри. Один конвеєр, будь-яка мова.
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


## Історія

> Мені 35 років. 10 років я вів бізнес. Потім я відкрив для себе технології.

Це не було зміною кар'єри. Це було одкровення. Можливість створювати, з мого терміналу, інструменти, які перетинають кордони.

Subvox народився з цієї одержимості: що якщо ви можете взяти будь-яке відео, корейську політичну промову, німецький підручник, арабську конференцію, і зробити його доступним вашою рідною мовою, за хвилини, не втрачаючи голос, тон, намір?

Subvox також про внесок спільноти, щоб зробити переклад відео доступним для всіх. На відміну від **Veed.io**, **Kapwing**, **Descript** або **Opus Clip**, гігантів, які беруть цілий статок за те, що має бути безкоштовним, які обмежують експорт, які замикають вас у підписки. Subvox відкритий, прозорий і створений людьми, які його використовують.

Це сольний проект, побудований коміт за комітом, тому що я вірю, що технології повинні належати всім. Не лише тим, хто говорить англійською.

Цей конвеєр — технічне серце. Решта, гаманці, токени, економіка, живе в іншому місці. Тут — машина для перекладу світу. Безкоштовно. Відкрито. Ваше.

---



## Можливості

| Крок | Опис |
|------|------|
| **⬇️ Завантаження** | Завантажує відео з X/Twitter, YouTube або прямого URL |
| **🎙️ Розшифровка** | Аудіо транскрипція через Groq (Whisper), 20+ мов |
| **🌐 Переклад** | LLM переклад (DeepSeek / OpenAI) на цільову мову |
| **🎬 Вбудовування** | Вбудовування субтитрів у відео (ffmpeg/libass) |
| **☁️ Завантаження** | Локальне або S3 зберігання результату |

**Бонус:** Експорт VTT/SRT, автоматичний водяний знак, виявлення сцен, аналіз контенту.

---

## Швидкий старт

### З Docker (рекомендовано)

```bash
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline
export GROQ_API_KEY="your_groq_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
docker compose up -d
curl http://localhost:8000/health
```

### Локальна розробка

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
| `/jobs/feed` | GET | Останні публічні переклади |
| `/jobs/{id}/status` | GET | Статус завдання |
| `/jobs/{id}/subtitles` | GET | Згенеровані субтитри |
| `/health` | GET | Перевірка стану |

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

## Участь

Цей проект молодий і створюється однією людиною. Будь-який внесок вітається:

- **Issues**: повідомте про помилку, запропонуйте функцію
- **PRs**: код, документація, тести, все допомагає
- **Discussions**: поділіться своїм сценарієм використання

Pipeline **повністю з відкритим кодом** (MIT). Ekonomi katmanı (cüzdanlar, tokenler) güvenlik nedeniyle özel kalır.

---

## 📄 License

MIT, made with ❤️ by [Nansou](https://github.com/Nansouoouu)
