# 📋 内容追踪表

| ID | 想法 | 状态 | 平台 | 创建时间 | 发布时间 |
|----|------|------|------|----------|----------|
| 001 | RL + LLM 思考 | published | Twitter | 2026-02-15 | - |
| 002 | Apple 面试经验 | reviewing | LinkedIn | 2026-02-15 | - |
| 003 | 5 个 AI 工具推荐 | drafted | Twitter+知乎 | 2026-02-15 | - |
| 004 | 测试内容 - Hello Fame | reviewing | Twitter | 2026-02-25 | - |

---

## 🔄 工作流

```
1. IDEA（想法）
   ↓
2. DRAFTING（撰写中）← 我在写
   ↓  
3. REVIEWING（待确认）← 你在审核
   ↓
4. SCHEDULED（待发布）
   ↓
5. PUBLISHED（已发布）
   ↓
6. ARCHIVED（存档）
```

---

## 🚧 开发进度

### 已完成 (2026-03-03)
- [x] Pipeline 核心架构 (`pipeline.py`)
- [x] 小红书自动化发布模块 (`publishers/xiaohongshu.py`)
- [x] Twitter/LinkedIn/知乎发布器框架 (`publishers/__init__.py`)
- [x] 配置文件 (`config.json`)
- [x] 视频生成管道 (`publishers/video.py`)
- [x] FFmpeg 幻灯片视频生成
- [x] Ken Burns 特效 (zoom in/out/pan)
- [x] TTS 音频支持 (ElevenLabs + macOS say)
- [x] 背景音乐添加
- [x] 9:16 竖屏格式 (1080x1920)
- [x] 小红书 Cookie 登录配置 ✅
- [x] Playwright 浏览器自动化集成

### 已完成 (2026-03-04)
- [x] Pipeline 核心架构 (`pipeline.py`)
- [x] 小红书自动化发布模块 (`publishers/xiaohongshu.py`)
- [x] Twitter/LinkedIn/知乎发布器框架 (`publishers/__init__.py`)
- [x] 配置文件 (`config.json`)
- [x] 视频生成管道 (`publishers/video.py`)
- [x] FFmpeg 幻灯片视频生成
- [x] Ken Burns 特效 (zoom in/out/pan)
- [x] TTS 音频支持 (ElevenLabs + macOS say)
- [x] 背景音乐添加
- [x] 9:16 竖屏格式 (1080x1920)
- [x] 小红书 Cookie 登录配置 ✅
- [x] Playwright 浏览器自动化集成
- [x] **Scheduler 定时调度器** ✅ 运行中
- [x] **图片自动生成** ✅ (20+ 封面)
- [x] **视频自动生成** ✅ (15+ 视频)

### 进行中 (2026-03-05)
- [ ] Twitter/LinkedIn API 密钥配置
- [ ] 小红书自动发布测试
- [ ] 内容效果追踪

---

## 📊 当前状态

| 指标 | 数量 |
|------|------|
| 生成图片 | 40+ |
| 生成视频 | 20+ |
| 内容创意 | 5 |

---

## 🔧 配置状态

| 平台 | 状态 | 说明 |
|------|------|------|
| Twitter | ⚠️ | 需要 API Key |
| LinkedIn | ⚠️ | 需要 Access Token |
| 知乎 | ⚠️ | 需要登录 Cookie |
| 小红书 | ✅ | 已配置 Cookie + Playwright |
| 视频生成 | ✅ | FFmpeg 本地生成 |
| TTS | ✅ | ElevenLabs API |

---

## 📁 项目结构

```
content-pipeline/
├── config.json          # 配置文件
├── pipeline.py          # 核心模块
├── STATUS.md            # 状态追踪
├── scheduler.py         # 定时任务调度
├── input/               # 输入文件夹 (新想法)
├── processing/         # 处理中文件夹
├── output/              # 已完成内容
├── queue/               # 待发布队列
└── publishers/          # 各平台发布器
    ├── __init__.py      # Twitter/LinkedIn/知乎
    ├── xiaohongshu.py   # 小红书 (浏览器自动化)
    ├── video.py         # 视频生成
    ├── image_generator.py # 图片生成
    └── cookies/         # 登录 Cookie
        └── xiaohongshu.json
```

---

## 📝 开发备注

### 小红书发布方案
- **方案**: Playwright 浏览器自动化
- **优点**: 无需官方 API，使用真实浏览器登录
- **流程**: Cookie 登录 → 打开发布页 → 上传图片 → 填写标题/正文 → 发布

### 定时发布
- 使用 scheduler.py 实现 cron 定时任务
- 支持多平台定时发布
