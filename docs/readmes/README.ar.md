<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center" dir="rtl">
  <strong>محرك ترجمة الفيديو مفتوح المصدر.</strong><br/>
  تحميل. نسخ. ترجمة. حرق الترجمة. خط أنابيب واحد، أي لغة.
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
  <a href="../../README.md"><img src="https://img.shields.io/badge/🇬🇧-English-blue" alt="English"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/🇫🇷-Français-blue" alt="Français"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/🇪🇸-Español-green" alt="Español"></a>
  <a href="README.ja.md"><img src="https://img.shields.io/badge/🇯🇵-日本語-blue" alt="日本語"></a>
  <a href="README.zh.md"><img src="https://img.shields.io/badge/🇨🇳-中文-red" alt="中文"></a>
  <a href="README.de.md"><img src="https://img.shields.io/badge/🇩🇪-Deutsch-orange" alt="Deutsch"></a>
  <a href="README.it.md"><img src="https://img.shields.io/badge/🇮🇹-Italiano-blue" alt="Italiano"></a>
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

## ✨ القصة

> عمري 35 عامًا. لمدة 10 سنوات، أدرتُ شركة. ثم اكتشفت التكنولوجيا.
>
> لم يكن تحولًا مهنيًا. كان وحيًا. القدرة على بناء أدوات تعبر الحدود من جهازي الطرفي.
>
> وُلد Subvox من هذا الهوس: ماذا لو استطعت أخذ أي فيديو — خطاب سياسي كوري، درس تعليمي ألماني، مؤتمر بالعربية — وجعله متاحًا بلغتك الأم، في دقائق، دون فقدان الصوت، النبرة، القصد؟
>
> Subvox هو أيضًا عن المساهمة كمجتمع لجعل ترجمة الفيديو متاحة للجميع. على عكس **Veed.io** و**Kapwing** و**Descript** و**Opus Clip**، عمالقة يفرضون ثروة على ما يجب أن يكون مجانيًا، ويحدون من تصديرك، ويحبسونك في اشتراكات. Subvox مفتوح وشفاف، بناه الذين يستخدمونه.
>
> هذا مشروع فردي، بُني commit بعد commit، لأنني أؤمن بأن التكنولوجيا يجب أن تكون للجميع. ليس فقط لمن يتحدثون الإنجليزية.
>
> هذا الخط هو القلب التقني. الباقي — المحافظ، الرموز، الاقتصاد — يعيش في مكان آخر. هنا، الآلة لترجمة العالم. مجاني. مفتوح. ملكك.
>
> *Nansou*

---

## 🎯 الميزات

| الخطوة | الوصف |
|---|---|
| **⬇️ تحميل** | جلب الفيديو من X/Twitter أو YouTube أو رابط مباشر |
| **🎙️ نسخ** | نسخ صوتي عبر Groq (Whisper)، 20+ لغة |
| **🌐 ترجمة** | ترجمة LLM (DeepSeek / OpenAI) إلى اللغة الهدف |
| **🎬 حرق** | تراكب الترجمة داخل الفيديو (ffmpeg/libass) |
| **☁️ رفع** | تخزين محلي أو S3 للنتيجة النهائية |

**إضافات:** تصدير VTT/SRT، علامة مائية تلقائية، كشف المشاهد، تحليل المحتوى.

---

## 🎬 نظرة عامة على خط الأنابيب

```
1. ألصق رابط فيديو
   │  YouTube، X/Twitter، TikTok، Instagram، Facebook...
   │  أداة التحقق تفحص الوصول في ثانيتين
   ▼
2. تحميل
   │  yt-dlp يجلب الفيديو (حتى 4K)
   ▼
3. نسخ الصوت
   │  Groq Whisper يحول الصوت إلى نص
   │  يدعم 20+ لغة
   ▼
4. ترجمة
   │  DeepSeek / OpenAI يترجم الترجمة
   │  باللغة التي تختارها
   ▼
5. حرق
   │  ffmpeg + libass يحرقان الترجمة في الفيديو
   │  علامة مائية تلقائية، نمط قابل للتخصيص
   ▼
6. النتيجة
   │  فيديو مترجم، جاهز للمشاركة
   │  تصدير SRT/VTT متاح
```

**الوقت الإجمالي:** 2-5 دقائق لفيديو مدته 3 دقائق.
**لا حاجة للبرمجة.** ألصق رابطًا، اختر لغة، احصل على فيديو مترجم.

---

## 🏗 الهيكلة

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

**Pipeline** = تقنية خالصة (هذا المستودع). يستدعي **Economy** عبر HTTP للمصادقة.

---

## 🚀 بداية سريعة

### باستخدام Docker (موصى به)

```bash
# 1. استنساخ
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline

# 2. تشغيل المجموعة الكاملة
export GROQ_API_KEY="your_groq_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
docker compose up -d

# 3. التحقق
curl http://localhost:8000/health
```

### بدون Docker (تطوير محلي)

```bash
# 1. الإعداد
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. التكوين
cp .env.example .env
# → تحرير DATABASE_URL, REDIS_URL

# 3. التشغيل
uvicorn backend.main:app --reload --port 8000
```

---

## 📡 API

| المسار | الطريقة | الوصف |
|---|---|---|
| `/jobs/feed` | GET | أحدث الترجمات العامة |
| `/jobs/{id}/status` | GET | حالة المهمة |
| `/jobs/{id}/subtitles` | GET | الترجمة المولدة |
| `/health` | GET | التحقق من الصحة |

المصادقة وإدارة الرموز تتم بواسطة خدمة مخصصة (خاصة).

---

## 🧩 التقنيات

| المكون | التقنية |
|---|---|
| API | Python 3.14 / FastAPI |
| قائمة الانتظار | Celery + Redis |
| فيديو | FFmpeg 7 |
| نسخ | Groq (Whisper) |
> **ملاحظة:** Groq يقدم ساعتين من النسخ المجاني يوميًا. مثالي للتطوير والمشاريع الصغيرة.
| ترجمة | DeepSeek / OpenAI |
| قاعدة بيانات | PostgreSQL 16 |

---

## 🤝 المساهمة

هذا المشروع صغير ويبنيه شخص واحد. كل مساهمة مرحب بها:

- **Issues**: أبلغ عن خطأ، اقترح ميزة
- **PRs**: كود، وثائق، اختبارات — كل شيء يساعد
- **مناقشات**: شارك حالة استخدامك

خط الأنابيب **مفتوح المصدر 100%** (MIT). الطبقة الاقتصادية (المحافظ، الرموز) تبقى خاصة لأسباب أمنية.

---

## 🙏 شكر وتقدير

Subvox Pipeline يعتمد على مشاريع مفتوحة المصدر أساسية:

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Groq](https://groq.com) · [DeepSeek](https://deepseek.com) · [OpenAI](https://openai.com) · [FFmpeg](https://ffmpeg.org) · [FastAPI](https://fastapi.tiangolo.com) · [Celery](https://docs.celeryq.dev) · [Redis](https://redis.io) · [PostgreSQL](https://postgresql.org)

---

## 📄 الترخيص

MIT، صنع بـ ❤️ بواسطة [Nansou](https://github.com/Nansouoouu)
