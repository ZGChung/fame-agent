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

### 已完成
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

### 进行中
- [ ] 小红书 Cookie 登录配置 ✅ 已完成
- [ ] Twitter/LinkedIn API 密钥配置
- [ ] 定时发布功能

### 待完成
- [ ] 浏览器自动化测试（小红书）
- [ ] 定时发布功能
- [ ] 内容效果追踪

---

## 🔧 配置状态

| 平台 | 状态 | 说明 |
|------|------|------|
| Twitter | ❌ | 需要 API Key |
| LinkedIn | ❌ | 需要 Access Token |
| 知乎 | ❌ | 需要登录 Cookie |
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
├── input/               # 输入文件夹 (新想法)
├── processing/          # 处理中文件夹
├── output/              # 已完成内容
├── queue/               # 待发布队列
└── publishers/          # 各平台发布器
    ├── __init__.py      # Twitter/LinkedIn/知乎
    └── xiaohongshu.py   # 小红书 (浏览器自动化)
```
