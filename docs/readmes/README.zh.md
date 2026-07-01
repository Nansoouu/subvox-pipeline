<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white">
    <img alt="Subvox" src="https://img.shields.io/badge/Subvox-00A86B?style=for-the-badge&logo=github&logoColor=white" width="200">
  </picture>
</p>

<h1 align="center">Subvox Pipeline</h1>

<p align="center">
  <strong>开源视频翻译引擎。</strong><br/>
  下载。转录。翻译。嵌入字幕。一条流水线，任意语言。
</p>

<p align="center">
  <a href="../../README.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇬🇧-English-white" alt="English"></a>
  <a href="README.fr.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇫🇷-Français-blue" alt="Français"></a>
  <a href="README.es.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇪🇸-Español-green" alt="Español"></a>
  <a href="README.pt.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇵🇹-Português-brightgreen" alt="Português"></a>
  <a href="README.de.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇩🇪-Deutsch-orange" alt="Deutsch"></a>
  <a href="README.it.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇮🇹-Italiano-red" alt="Italiano"></a>
  <a href="README.ja.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇯🇵-日本語-blueviolet" alt="日本語"></a>
  <a href="README.ar.md" style="text-decoration:none"><img src="https://img.shields.io/badge/🇸🇦-العربية-lightgrey" alt="العربية"></a>
</p>

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🇬🇧-English-blue" alt="English"></a>
  <a href="README.fr.md"><img src="https://img.shields.io/badge/🇫🇷-Français-blue" alt="Français"></a>
  <a href="README.es.md"><img src="https://img.shields.io/badge/🇪🇸-Español-green" alt="Español"></a>
  <a href="README.ja.md"><img src="https://img.shields.io/badge/🇯🇵-日本語-blue" alt="日本語"></a>
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

## ✨ 故事

> 我35岁。过去10年，我经营着一家企业。然后我发现了技术。
>
> 这不是职业转型。这是一种启示。从我的终端，构建跨越国界的工具的能力。
>
> Subvox诞生于这种执着：如果你能任意获取一段视频——一段韩语政治演讲、一篇德语教程、一场阿拉伯语会议——在几分钟内让它以你的母语呈现，且不丢失声音、语调和意图，会怎样？
>
> Subvox也是关于作为社区贡献，让视频翻译对每个人都可及。与 **Veed.io**、**Kapwing**、**Descript** 或 **Opus Clip** 不同，这些巨头对本来应该免费的东西收取高昂费用，限制你的导出，将你锁在订阅中。Subvox是开放的、透明的，由使用它的人构建。
>
> 这是一个单人项目，一次提交一次提交地构建，因为我相信技术应该属于每个人——而不仅仅属于说英语的人。
>
> 这条流水线是技术核心。其余部分——钱包、代币、经济——存在于别处。在这里，是翻译世界的机器。自由。开放。属于你。
>
> *Nansou*

---

## 🎯 功能

| 步骤 | 描述 |
|---|---|
| **⬇️ 下载** | 从X/Twitter、YouTube或直接URL获取视频 |
| **🎙️ 转录** | 通过Groq（Whisper）进行音频转录，支持20+种语言 |
| **🌐 翻译** | LLM翻译（DeepSeek / OpenAI）到目标语言 |
| **🎬 嵌入** | 将字幕叠加到视频中（ffmpeg/libass） |
| **☁️ 上传** | 本地或S3存储最终结果 |

**附加功能：** VTT/SRT导出、自动水印、场景检测、内容分析。

---

## 🎬 流水线流程

```
1. 粘贴视频链接
   │  YouTube、X/Twitter、TikTok、Instagram、Facebook...
   │  验证器在2秒内检查可访问性
   ▼
2. 下载
   │  yt-dlp获取视频（最高4K）
   ▼
3. 音频转录
   │  Groq Whisper将音频转换为文本
   │  支持20+种语言
   ▼
4. 翻译
   │  DeepSeek / OpenAI翻译字幕
   │  选择你需要的语言
   ▼
5. 嵌入
   │  ffmpeg + libass将字幕嵌入视频
   │  自动水印，可自定义样式
   ▼
6. 结果
   │  带字幕的视频，随时分享
   │  支持SRT/VTT导出
```

**总耗时：** 3分钟的视频约需2-5分钟。
**无需编码。** 粘贴链接，选择语言，获得翻译后的视频。

---

## 🏗 架构

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

**Pipeline** = 纯技术（本仓库）。通过HTTP调用 **Economy** 进行身份验证。

---

## 🚀 快速开始

### 使用Docker（推荐）

```bash
# 1. 克隆
git clone https://github.com/Nansouoouu/subvox-pipeline.git
cd subvox-pipeline

# 2. 启动完整堆栈
export GROQ_API_KEY="your_groq_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
docker compose up -d

# 3. 检查
curl http://localhost:8000/health
```

### 不使用Docker（本地开发）

```bash
# 1. 设置
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置
cp .env.example .env
# → 编辑 DATABASE_URL, REDIS_URL

# 3. 运行
uvicorn backend.main:app --reload --port 8000
```

---

## 📡 API

| 路由 | 方法 | 描述 |
|---|---|---|
| `/jobs/feed` | GET | 最新的公开翻译 |
| `/jobs/{id}/status` | GET | 任务状态 |
| `/jobs/{id}/subtitles` | GET | 生成的字幕 |
| `/health` | GET | 健康检查 |

认证和令牌管理由专用服务（私有）处理。

---

## 🧩 技术栈

| 组件 | 技术 |
|---|---|
| API | Python 3.14 / FastAPI |
| 队列 | Celery + Redis |
| 视频 | FFmpeg 7 |
| 转录 | Groq（Whisper） |
> **注意：** Groq每天提供2小时的免费转录。非常适合开发和小型项目。
| 翻译 | DeepSeek / OpenAI |
| 数据库 | PostgreSQL 16 |

---

## 🤝 贡献

这个项目还很年轻，由一个人构建。欢迎所有贡献：

- **Issues**：报告错误，建议功能
- **PRs**：代码、文档、测试 — 一切都有帮助
- **讨论**：分享你的使用案例

流水线是 **100% 开源的**（MIT）。经济层（钱包、代币）出于安全原因保持私有。

---

## 🙏 致谢

Subvox Pipeline依赖于以下重要的开源项目：

[yt-dlp](https://github.com/yt-dlp/yt-dlp) · [Groq](https://groq.com) · [DeepSeek](https://deepseek.com) · [OpenAI](https://openai.com) · [FFmpeg](https://ffmpeg.org) · [FastAPI](https://fastapi.tiangolo.com) · [Celery](https://docs.celeryq.dev) · [Redis](https://redis.io) · [PostgreSQL](https://postgresql.org)

---

## 📄 许可证

MIT，由 [Nansou](https://github.com/Nansouoouu) 用 ❤️ 制作
