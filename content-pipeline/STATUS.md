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

### 进行中 (2026-03-06)
- [x] 小红书自动发布测试 ✅ 成功！
- [x] TTS 文件清理 bug 修复
- [x] Pipeline 队列状态监控
- [ ] Twitter/LinkedIn API 密钥配置
- [ ] 内容效果追踪

---

## 📊 当前状态 (2026-03-06)

| 指标 | 数量 |
|------|------|
| input | 40 条 |
| processing | 21 条 |
| queue | 2 条 |
| output | 506 个视频 |

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



---

## 🚧 开发进度 (2026-05-19)

### 已完成 (Phase 2 部分功能)
- [x] **Twitter/X 发布器** (`publishers/twitter.py`) ✅
  - Twitter API v2 Bearer Token 认证
  - 超过 280 字自动拆分为推文串（reply chain）
  - 平台变体（platform_variant）支持
  - 12 项测试覆盖（配置检查、文本拆分、API 调用、错误处理）
- [x] 全部 43 项测试通过

### 待完成 (Phase 2 剩余)
- [ ] AI Review Panel (`reviewer.py`) — 5 维度 AI 审核
- [ ] 可编辑审核标准文件系统 (`criteria/`)
- [ ] 各平台优化目标系统 (`objectives/`)
- [ ] Bilibili 发布器
- [ ] LinkedIn 发布器
- [ ] 定时发布 / scheduling 集成到 src 包
- [ ] 结构化日志 (`log.py`)
- [ ] Pipeline 监控 (`monitor.py`)
- [ ] GitHub Actions CI/CD

### 待完成 (Phase 3-4)
- [ ] Analytics 反馈闭环（分析引擎 + 标准更新器）
- [ ] TikTok 发布器 / YouTube 发布器
- [ ] Curator Agent（自动选题策展）
- [ ] Threads 发布器
