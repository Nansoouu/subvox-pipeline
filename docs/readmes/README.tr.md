<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>Açık kaynaklı video çeviri motoru.</strong><br/>
  İndir. Yazıya dök. Çevir. Altyazıları yak. Tek boru hattı, her dil.
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
  <a href="https://github.com/Nansoouu/subvox"><img src="https://img.shields.io/badge/Subvox%20Ecosystem-00A86B?style=for-the-badge&logo=github&logoColor=white" alt="Subvox Ecosystem"></a>
  <a href="https://github.com/Nansoouu/subvox-pipeline"><img src="https://img.shields.io/badge/Pipeline%20Engine-00A86B?style=for-the-badge&logo=github&logoColor=white" alt="Pipeline Engine"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/python-3.14-blue" alt="Python">
  <img src="https://img.shields.io/badge/FFmpeg-required-orange" alt="FFmpeg">
</p>

---



## Özellikler

| Adım | Açıklama |
|------|----------|
| **⬇️ İndir** | X/Twitter, YouTube veya doğrudan URL'den video alır |
| **🎙️ Yazıya dök** | Groq (Whisper) ile ses yazıya dökme, 20+ dil |
| **🌐 Çevir** | Hedef dile LLM çevirisi (DeepSeek / OpenAI) |
| **🎬 Yak** | Videoya altyazı yakma (ffmpeg/libass) |
| **☁️ Yükle** | Sonucun yerel veya S3 depolaması |

**Bonus:** VTT/SRT dışa aktarımı, otomatik filigran, sahne algılama, içerik analizi.

---

## Hızlı Başlangıç

### Docker ile (önerilen)

```bash
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline
export GROQ_API_KEY="your_groq_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
docker compose up -d
curl http://localhost:8000/health
```

### Yerel geliştirme

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
| `/jobs/feed` | GET | Son herkese açık çeviriler |
| `/jobs/{id}/status` | GET | İş durumu |
| `/jobs/{id}/subtitles` | GET | Oluşturulan altyazılar |
| `/health` | GET | Sağlık kontrolü |

---

## Teknoloji Yığını

| Bileşen | Teknoloji |
|---------|-----------|
| API | Python 3.14 / FastAPI |
| Kuyruk | Celery + Redis |
| Video | FFmpeg 7 |
| Transkripsiyon | Groq (Whisper) |
| Çeviri | DeepSeek / OpenAI |
| DB | PostgreSQL 16 |

---

## Katkıda Bulunma

Bu proje genç ve tek bir kişi tarafından inşa ediliyor. Her katkı hoş karşılanır:

- **Issues**: hata bildirimi, özellik önerisi
- **PRs**: kod, dokümantasyon, testler, her şey yardımcı olur
- **Discussions**: kullanım senaryonuzu paylaşın

Pipeline **tamamen açık kaynaktır** (MIT). Ekonomi katmanı (cüzdanlar, tokenler) güvenlik nedeniyle özel kalır.

---

## 📄 License

MIT, made with ❤️ by [Nansou](https://github.com/Nansouoouu)
