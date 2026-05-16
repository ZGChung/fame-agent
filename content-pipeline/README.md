# Content Pipeline

Jayson 的多平台社交媒体内容自动化发布管道。

## 架构概览

```
内容输入 → 草稿生成 → 平台适配 → 审核 → 发布
                                               ↓
                                   小红书 | Twitter | LinkedIn | 知乎
```

每个阶段独立、可插拔。每个发布器完全解耦。

## 快速开始

```bash
# 安装
pip install -e ".[dev]"
playwright install chromium

# 配置
cp .env.example .env
# 编辑 .env 填入 API Key

# 查看状态
pipeline status

# 发布内容
pipeline publish <content_id> --platform xiaohongshu

# 生成视频
pipeline video generate <content_id>
```

## 项目结构

```
content-pipeline/
├── src/content_pipeline/    # 核心包
│   ├── models.py            # 数据模型
│   ├── config.py            # 配置管理
│   ├── pipeline.py          # 流程编排
│   ├── stages.py            # 处理阶段
│   ├── publishers/          # 平台发布器（完全解耦）
│   ├── media/               # 媒体生成（图片/视频）
│   └── cli.py               # 命令行入口
├── content/                 # 内容存储（不走 git）
│   ├── input/               # 新内容
│   ├── processing/          # 处理中
│   ├── queue/               # 待发布
│   └── published/           # 已发布
├── blog/                    # 长文草稿
├── published/               # 已发布存档
├── onhold/                  # 暂缓内容
└── tests/                   # 测试
```

## 平台支持

| 平台 | 状态 | 方式 |
|------|------|------|
| 小红书 | ✅ 可用 | Playwright 浏览器自动化 |
| Twitter/X | ⚠️ 待接入 | API v2 (OAuth 2.0) |
| LinkedIn | ⚠️ 待接入 | API v2 |
| 知乎 | ⚠️ 待接入 | 需 Cookie |
