<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>Công cụ dịch video mã nguồn mở.</strong><br/>
  Tải xuong. Phien âm. Dịch. Ghi phụ đe. Một đương ống, bat kỳ ngôn ngữ nào.
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



## Tính năng

| Bước | Mô tả |
|------|-------|
| **⬇️ Tải xuống** | Lấy video từ X/Twitter, YouTube hoặc URL trực tiếp |
| **🎙️ Phiên âm** | Phiên âm âm thanh qua Groq (Whisper), 20+ ngôn ngữ |
| **🌐 Dịch** | Dịch LLM (DeepSeek / OpenAI) sang ngôn ngữ đích |
| **🎬 Ghi** | Ghi phụ đề vào video (ffmpeg/libass) |
| **☁️ Tải lên** | Lưu trữ cục bộ hoặc S3 kết quả cuối cùng |

**Bonus:** Xuất VTT/SRT, hình mờ tự động, phát hiện cảnh, phân tích nội dung.

---

## Bắt đầu nhanh

### Với Docker (khuyên dùng)

```bash
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline
export GROQ_API_KEY="your_groq_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
docker compose up -d
curl http://localhost:8000/health
```

### Phát triển cục bộ

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
| `/jobs/feed` | GET | Bản dịch công khai mới nhất |
| `/jobs/{id}/status` | GET | Trạng thái công việc |
| `/jobs/{id}/subtitles` | GET | Phụ đề đã tạo |
| `/health` | GET | Kiểm tra sức khỏe |

---

## Công nghệ

| Bileşen | Teknoloji |
|---------|-----------|
| API | Python 3.14 / FastAPI |
| Kuyruk | Celery + Redis |
| Video | FFmpeg 7 |
| Transkripsiyon | Groq (Whisper) |
| Çeviri | DeepSeek / OpenAI |
| DB | PostgreSQL 16 |

---

## Đóng góp

Dự án này còn non trẻ và được xây dựng bởi một người. Mọi đóng góp đều được hoan nghênh:

- **Issues**: báo lỗi, đề xuất tính năng
- **PRs**: mã, tài liệu, kiểm thử, mọi thứ đều có ích
- **Discussions**: chia sẻ trường hợp sử dụng của bạn

Pipeline **100% mã nguồn mở** (MIT). Ekonomi katmanı (cüzdanlar, tokenler) güvenlik nedeniyle özel kalır.

---

## 📄 License

MIT, made with ❤️ by [Nansou](https://github.com/Nansouoouu)
