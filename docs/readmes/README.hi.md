<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>ओपन-सोर्स वीडियो अनुवाद इंजन।</strong><br/>
  डाउनलोड करें। ट्रांसक्राइब करें। अनुवाद करें। उपशीर्षक जलाएं। एक पाइपलाइन, कोई भी भाषा।
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


## कहानी

> मैं 35 साल का हूँ। 10 सालों तक मैंने व्यवसाय चलाया। फिर मैंने तकनीक की खोज की।

यह करियर परिवर्तन नहीं था। यह एक रहस्योद्घाटन था। अपने टर्मिनल से ऐसे उपकरण बनाने की क्षमता जो सीमाओं को पार करते हैं।

Subvox इस जुनून से पैदा हुआ: क्या हो अगर आप कोई भी वीडियो ले सकें, एक कोरियाई राजनीतिक भाषण, एक जर्मन ट्यूटोरियल, एक अरबी सम्मेलन, और इसे आपकी मातृभाषा में, मिनटों में, आवाज, लहजा, इरादा खोए बिना सुलभ बना सकें?

Subvox समुदाय के योगदान के बारे में भी है ताकि वीडियो अनुवाद सभी के लिए सुलभ हो सके। **Veed.io**, **Kapwing**, **Descript** या **Opus Clip** के विपरीत, दिग्गज जो मुफ्त होनी चाहिए उसके लिए भारी कीमत वसूलते हैं, जो आपके निर्यात को सीमित करते हैं, जो आपको सदस्यताओं में बंद करते हैं। Subvox खुला, पारदर्शी और इसे उपयोग करने वाले लोगों द्वारा बनाया गया है।

यह एक एकल परियोजना है, कमिट दर कमिट बनाई गई, क्योंकि मेरा मानना है कि तकनीक सभी की होनी चाहिए। सिर्फ अंग्रेजी बोलने वालों की नहीं।

यह पाइपलाइन तकनीकी हृदय है। बाकी, वॉलेट, टोकन, अर्थव्यवस्था, कहीं और रहता है। यहाँ, यह दुनिया का अनुवाद करने की मशीन है। मुफ्त। खुला। आपका।

---



## विशेषताएँ

| चरण | विवरण |
|-----|-------|
| **⬇️ डाउनलोड** | X/Twitter, YouTube या सीधे URL से वीडियो लाता है |
| **🎙️ ट्रांसक्राइब** | Groq (Whisper) के माध्यम से ऑडियो ट्रांसक्रिप्शन, 20+ भाषाएँ |
| **🌐 अनुवाद** | लक्ष्य भाषा में LLM अनुवाद (DeepSeek / OpenAI) |
| **🎬 बर्न** | वीडियो में उपशीर्षक जलाना (ffmpeg/libass) |
| **☁️ अपलोड** | अंतिम परिणाम का स्थानीय या S3 भंडारण |

**बोनस:** VTT/SRT निर्यात, स्वचालित वॉटरमार्क, दृश्य पहचान, सामग्री विश्लेषण।

---

## त्वरित शुरुआत

### Docker के साथ (अनुशंसित)

```bash
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline
export GROQ_API_KEY="your_groq_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
docker compose up -d
curl http://localhost:8000/health
```

### स्थानीय विकास

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
| `/jobs/feed` | GET | नवीनतम सार्वजनिक अनुवाद |
| `/jobs/{id}/status` | GET | कार्य स्थिति |
| `/jobs/{id}/subtitles` | GET | उत्पन्न उपशीर्षक |
| `/health` | GET | स्वास्थ्य जाँच |

---

## स्टैक

| Bileşen | Teknoloji |
|---------|-----------|
| API | Python 3.14 / FastAPI |
| Kuyruk | Celery + Redis |
| Video | FFmpeg 7 |
| Transkripsiyon | Groq (Whisper) |
| Çeviri | DeepSeek / OpenAI |
| DB | PostgreSQL 16 |

---

## योगदान

यह परियोजना युवा है और एक व्यक्ति द्वारा बनाई गई है। हर योगदान का स्वागत है:

- **Issues**: बग रिपोर्ट करें, सुविधा सुझाएं
- **PRs**: कोड, दस्तावेज़ीकरण, परीक्षण, सब कुछ मददगार है
- **Discussions**: अपना उपयोग मामला साझा करें

Pipeline **100% ओपन-सोर्स** (MIT) है। Ekonomi katmanı (cüzdanlar, tokenler) güvenlik nedeniyle özel kalır.

---

## 📄 License

MIT, made with ❤️ by [Nansou](https://github.com/Nansouoouu)
