# Content Pipeline — Product Requirements Document (PRD)

**版本**: v0.3
**日期**: 2026-05-16
**作者**: Fame Agent (on behalf of Jayson)

---

## 1. 执行摘要

Content Pipeline 是一个全自动、多平台、多模态的社交媒体内容发布系统。内容从"想法"进入管道，经过标准化处理、平台适配、媒体生成，最终自动发布到多个社交媒体平台并追踪效果。

**核心理念**: 内容生产自动化，不是半自动辅助工具，而是几乎可以无人值守的全自动管道。

---

## 2. 目标与非目标

### 目标

- **全自动**：内容从输入到发布几乎不需要人工干预
- **多平台**：一套内容，自动适配并发布到所有主流平台
- **多模态**：文本、图片、视频（含短视频）统一编排
- **可观测**：管道状态、发布结果、数据表现一目了然
- **可测试**：每个组件都有自动化测试保障
- **可扩展**：添加新平台或新模态不需要重写现有代码

### 非目标

- 不做社交平台的客户端（不读私信、不互动）
- 不做竞品分析或内容爬取
- 不取代人类创作（人类负责高层的选题和判断，管道负责执行）
- 不保证内容质量（质量由上游选题和审核环节控制）

---

## 3. 架构概览

### 3.1 整体流程

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Ingestion │ → │ Processing│ → │  Review  │ → │Scheduling│ → │Publishing│
│  内容摄入  │    │  内容处理  │    │ AI 审核  │    │  调度    │    │  发布    │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
      │               │               │               │               │
      ▼               ▼               ▼               ▼               ▼
  输入源:        每阶段:         AI 审核        定时队列:       目标平台:
  · 手动写作     · 平台适配      · 事实核查     · 指定时间      小红书
  · AI生成       · 媒体生成      · 质量评分     · 自动排期      Bilibili
  · 播客转写     · 多语言翻译    · 风格检查                          LinkedIn
  · API输入      · SEO优化       · 平台适配校验                      Twitter
                                                                   TikTok
                                                                   YouTube
                                                                   Threads

                                      ┌──────────────────────────────────┐
                                      │                                  │
                                      ▼                                  │
                              ┌──────────────┐                          │
                              │  Analytics    │  ← 发布后 N 天收集数据    │
                              │  效果分析     │    点赞/收藏/转发/评论    │
                              └──────┬───────┘                          │
                                     │ 学习 → 更新审核标准               │
                                     ▼                                  │
                              ┌──────────────┐                          │
                              │  Criteria    │  → AI 审核读取最新标准     │
                              │  审核标准库   │    (可编辑 Markdown 文件)  │
                              └──────────────┘──────────────────────────┘
```

### 3.2 模块依赖关系

```
                    ┌─────────────────────┐
                    │    Pipeline Orc     │   ← 编排器，不含平台/媒体逻辑
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
   │  Publishers  │    │  Media Gen   │    │  Stages      │
   │  发布器集群  │    │  媒体生成    │    │  处理阶段    │
   └─────────────┘    └──────────────┘    └──────────────┘
          │                    │                    │
          ▼                    ▼                    │
   ┌─────────────┐    ┌──────────────┐             │
   │ · 小红书     │    │ · 图片生成   │             │
   │ · Bilibili   │    │ · 视频生成   │             │
   │ · LinkedIn   │    │ · AI配乐    │             │
   │ · Twitter    │    │ · TTS配音   │             │
   │ · TikTok     │    │ · 字幕生成  │             │
   │ · YouTube    │    └──────────────┘             │
   │ · Threads    │                                  │
                                                    ▼
                                           ┌──────────────┐
                                           │ · 验证       │
                                           │ · 格式化     │
                                           │ · 审核       │
                                           └──────────────┘
```

**核心原则**: 每个模块只对自己的领域负责。
- Pipeline Orc 不知道任何平台细节
- 发布器不知道其他平台的存在
- 媒体生成器不知道内容要去哪个平台
- Stages 是纯函数，输入内容 → 输出内容

---

## 4. 管道阶段详解

### 4.1 Ingestion（内容摄入）

内容进入管道的所有入口：

| 方式 | 说明 | 自动化程度 |
|------|------|-----------|
| 手动 Markdown | 直接写文件到 content/input/ | 手动 |
| AI 草稿生成 | LLM 根据选题生成初稿 | 全自动 |
| 语音转写 | 播客/口述 → 文字 → 内容 | 半自动 |
| API 导入 | 从 Notion/Obsidian 等同步 | 全自动 |
| RSS/News | 自动化搜集素材 → 选题建议 | 全自动 |

### 4.2 Processing（内容处理）

内容在管道中被处理的核心环节：

1. **平台适配（Multi-platform Adaptation）**
   - 同一份原始内容，为每个目标平台生成适配版本
   - 小红书：emoji 风格、短句、标签
   - Bilibili：视频标题 + 简介 + 标签 + 专栏长文
   - LinkedIn：正式风格、段落分明
   - Twitter：280 字以内、话题标签
   - TikTok：一句话钩子 + 描述
   - YouTube：标题 + 描述 + 标签
   - Threads：简洁短文

2. **媒体生成（Media Generation）**
   - 封面图片：AI 生成或模板 + 标题叠加
   - 信息图：关键数据可视化
   - 视频：图片幻灯片 → TTS 配音 → 背景音乐
   - 短视频：自动剪辑 + 字幕 + 特效

3. **多语言适配（可选）**
   - 中英文双语版本生成
   - 自动翻译 + 人工校对标记

### 4.3 Review（AI 审核 — 伪人工审核）{#ai-review}

Pipeline 在内容发布前设置审核关口，但**不需要 Jayson 亲自审核**。
审核工作由强大的 AI 模型完成，模拟人工审核的质量和判断力。

#### 4.3.1 设计理念：伪人工审核（Fake Human-in-the-Loop）

```
内容就绪
    │
    ▼
┌─────────────────────────────────────┐
│         AI Review Panel              │
│  ┌─────────┐ ┌─────────┐ ┌────────┐ │
│  │事实核查  │ │质量评分  │ │风格检查 │ │
│  │ AI Agent │ │ AI Agent│ │ AI Agent│ │
│  └─────────┘ └─────────┘ └────────┘ │
│                                     │
│  综合决策：通过 / 需修改 / 拒绝      │
└─────────────────────────────────────┘
    │         │            │
    ▼         ▼            ▼
  自动发布   打回修改    人工介入
                        (Jayson 可选)
```

**核心思路**：
- 管道在「发布前」和「发布后」都设置检查点
- 检查点本身是预留的位置（gate），由 AI 模型接管
- Jayson 不需要亲自审核，但保留随时查看和覆盖的权利
- AI 审核结果与内容一起存储，方便事后审计

#### 4.3.2 AI 审核维度

每个审核 Agent 负责一个维度，各自独立运行，结果汇总：

| 审核维度 | AI Agent 负责内容 | 判定结果 |
|---------|-----------------|---------|
| **事实核查** | 确认内容中的事实性陈述、数据、引用是否合理 | pass / flag / fail |
| **质量评分** | 内容完整性、逻辑连贯性、信息密度、原创性 | 1-10 分 |
| **风格检查** | 是否符合平台调性、语气是否一致、格式是否正确 | pass / flag |
| **安全审查** | 政治敏感、违规内容、版权风险 | pass / flag / fail |
| **平台适配** | 各平台版本是否满足字数、格式、标签要求 | pass / flag |

#### 4.3.3 审核决策逻辑

```
各 Agent 返回结果 → 汇总评分器 → 最终决策

通过条件（可配置）:
  · 所有维度 pass → auto 通过
  · 质量分 ≥ 7, 无 fail → auto 通过
  · 存在 flag 但无 fail → 标记后自动通过（可配置为需确认）
  · 存在任一 fail → 打回修改或标记为需人工审核

人工介入触发条件:
  · AI 置信度 < 阈值（可配置）
  · 内容属于"高优先级"类别
  · 连续 N 条内容 flag 同一问题
  · Jayson 主动标记某条内容为需审核
```

#### 4.3.4 AI 审核配置

```yaml
review:
  enabled: true
  provider: "openai"           # 审核模型提供商
  model: "gpt-4o"              # 审核模型
  fallback_model: "claude-3-haiku"
  
  # 各审核维度的权重和阈值
  dimensions:
    fact_check:
      enabled: true
      min_score: 0.7           # 低于此值标记
    quality:
      enabled: true
      min_score: 6.0           # 质量分低于此打回
      dimensions:              # 质量分的子维度权重
        completeness: 0.3
        coherence: 0.3
        originality: 0.2
        information_density: 0.2
    style:
      enabled: true
    safety:
      enabled: true
      strictness: "normal"     # low / normal / high
    platform_compliance:
      enabled: true
  
  # 决策规则
  auto_approve_threshold: 0.8  # AI 置信度 ≥ 此值自动通过
  max_flags_before_block: 3    # 连续 N 条 flag 同一问题则全局暂停
  
  # 人工介入
  human_fallback:
    enabled: true
    notify_on: ["fail", "low_confidence"]
    notify_channel: "telegram"  # 可选 telegram / email / feishu
```

#### 4.3.5 审核结果存储

每条内容审核后，结果与内容一起存储：

```json
{
  "content_id": "042",
  "review_status": "approved",
  "reviewed_at": "2026-05-16T14:30:00Z",
  "reviewer": "ai:gpt-4o",
  "confidence": 0.92,
  "dimensions": {
    "fact_check": {"score": 0.85, "status": "pass", "notes": []},
    "quality": {"score": 8.2, "status": "pass", "notes": ["逻辑清晰，论据充分"]},
    "style": {"score": 0.9, "status": "pass", "notes": []},
    "safety": {"score": 0.95, "status": "pass", "notes": []},
    "platform_compliance": {"score": 1.0, "status": "pass", "notes": []}
  },
  "human_overridden": false
}
```

#### 4.3.6 与传统 human-in-the-loop 的区别

| 特性 | 传统 Human-in-the-Loop | 本系统（AI 伪审核） |
|------|----------------------|-------------------|
| 执行者 | 人类逐条审核 | AI Agent 集群 |
| 延迟 | 小时/天级别 | 秒级别 |
| 容量 | 受限于人力 | 无限扩展 |
| 一致性 | 依赖个人状态 | 一致的审核标准 |
| 审计 | 难以回溯 | 每条都有详细的审核日志 |
| 兜底 | 人类最后把关 | AI 低置信度时通知人类 |

#### 4.3.7 可编辑的审核标准文件（Review Criteria as Markdown）

审核标准不写死在代码里，而是以 **Markdown 文件** 的形式存储在 `criteria/` 目录中。
修改审核标准 = 编辑一个 Markdown 文件，不需要改任何代码。

**目录结构：**

```
criteria/
├── default.md                   # 全局默认标准
├── xiaohongshu.md               # 小红书专属标准
├── bilibili.md                  # Bilibili 专属标准
├── linkedin.md                  # LinkedIn 专属标准
├── twitter.md                   # Twitter 专属标准
├── knowledge_base.md            # 知识库：Jayson 的风格偏好、常用术语
└── metrics/                     # 自动生成的指标数据（系统写入）
    ├── xiaohongshu_performance.md  # 小红书历史表现总结
    └── ...                        # 每个平台一个
```

**文件格式示例（`criteria/xiaohongshu.md`）：**

```markdown
# 小红书审核标准

## 风格要求
- 语气：亲近、口语化，像朋友在分享
- 长度：300-800 字为佳
- 段落：短段落，每段不超过 3 行
- 表情符号：适当使用 emoji，每段 1-2 个
- Hashtag：2-5 个相关标签，放在末尾

## 内容要求
- 开头要有钩子（Hook），前 2 行抓住注意力
- 提供具体可操作的见解，避免空泛
- 最好有个人经历或故事作为支撑

## 视觉要求
- 封面图要吸引眼球，文字叠加在图片上
- 图片数量：3-6 张为佳

## 避坑
- 不要硬广，小红书对营销内容限流
- 不要使用外部链接
- 不要过长（超过 1000 字会被截断）

## 历史表现（自动更新）
<!-- 以下内容由系统根据实际数据自动更新 -->
- 最近 30 天平均点赞：245
- 最近 30 天平均收藏：89
- 表现最好的标题模式：疑问句 / 数字列表
- 表现最好的内容主题：AI 工具测评、效率方法
```

**更新流程：**

```
1. 系统分析器查看最近 N 天的发布数据
2. 发现"疑问句标题"的点赞率比陈述句高 40%
3. 自动在 criteria/xiaohongshu.md 中添加一条：
   "标题建议：优先使用疑问句或数字列表"
4. 下次 AI 审核读取该文件时，自动采用新标准
```

**权限设计：**
- `criteria/*.md` — Jayson / AI 均可编辑（双向）  
- `criteria/metrics/*.md` — 仅系统自动写入
- 所有修改通过 Git 跟踪，可查看历史变更

### 4.4 Scheduling（调度）

内容从"就绪"到"发布"的排队和定时：

- **定时发布**：指定日期时间发布
- **自动排期**：根据内容量和最佳发布时间自动排入队列
- **频率控制**：每个平台每天/每周最大发布量
- **优先级**：高优内容插队
- **队列可视化**：查看未来 N 天的发布计划

### 4.5 Publishing（发布）

发布到目标平台，包括失败处理：

- **同步发布**：立即发布（CLI 模式）
- **异步发布**：后台队列，轮询执行
- **重试机制**：失败自动重试 3 次，指数退避
- **降级策略**：某平台不可用 → 跳过 / 排队重试 / 通知人工
- **幂等保证**：同一条内容不会重复发布

### 4.6 Analytics（效果追踪）

发布后的基础记录：

- **发布记录**：时间、平台、URL、状态
- **基础存储**：每条内容的发布结果持久化

### 4.7 效果反馈回路（Analytics Feedback Loop）{#feedback-loop}

这是整个系统最核心的**学习机制**。发布不是终点，效果数据会回流修改审核标准，形成闭环：

```
发布 → 等待 N 天 → 收集观众数据 → 分析 → 更新审核标准 → 更好的未来内容
  │                                                                  │
  └────────────────────────── 闭环 ──────────────────────────────────┘
```

#### 4.7.1 数据收集（每篇内容发布后）

每篇内容发布后，在经过一个「等待期」后自动收集以下数据：

| 数据类型 | 小红书 | Bilibili | LinkedIn | Twitter |
|---------|--------|----------|----------|---------|
| 曝光量/阅读 | ✅ | ✅ | ✅ | ✅ |
| 点赞 | ✅ | ✅ | ✅ | ✅ |
| 收藏 | ✅ | ❌（点赞替代） | ❌ | ❌（书签） |
| 转发/分享 | ✅ | ✅ | ✅ | ✅ |
| 评论数 | ✅ | ✅ | ✅ | ✅ |
| 完播率（视频） | ✅ | ✅ | ❌ | ❌ |
| 关注转化 | ❌ | ✅ | ✅ | ✅ |

**等待期配置**（不同平台观众响应速度不同）：

```yaml
feedback:
  collection_window:
    xiaohongshu: "7d"        # 小红书：7 天
    bilibili: "14d"          # Bilibili：14 天（视频内容反馈更慢）
    linkedin: "3d"           # LinkedIn：3 天
    twitter: "1d"            # Twitter：1 天（流速快）
    tiktok: "2d"             # TikTok：2 天
    youtube: "14d"           # YouTube：14 天
```

#### 4.7.2 分析引擎（Insight Engine）

收集到的原始数据经过分析引擎处理，提炼出可操作的洞察：

**量化分析：**
```
每条内容的评分 = w1 × 点赞率 + w2 × 收藏率 + w3 × 转发率 + w4 × 评论率

按维度分组分析：
- 按标题模式分组：疑问句 vs 陈述句 vs 数字列表
- 按内容主题分组：AI 测评 vs 效率方法 vs 行业观点
- 按长度分组：短 (<300) vs 中 (300-800) vs 长 (>800)
- 按情感基调分组：乐观 vs 批判 vs 中立
- 按发布时间分组：早 (6-9) vs 中 (12-14) vs 晚 (18-22)
```

**输出洞察示例：**

```json
{
  "platform": "xiaohongshu",
  "period": "2026-05-09_to_2026-05-16",
  "total_posts": 12,
  "insights": [
    {
      "dimension": "title_pattern",
      "finding": "疑问句标题的平均点赞率比陈述句高 42%",
      "confidence": 0.85,
      "sample_count": 8,
      "recommendation": "优先使用疑问句作为标题开头"
    },
    {
      "dimension": "content_length",
      "finding": "600-800 字的内容收藏率是 <300 字的 2.3 倍",
      "confidence": 0.78,
      "sample_count": 6,
      "recommendation": "目标字数保持在 600-800 字区间"
    },
    {
      "dimension": "topic",
      "finding": "\"AI 工具测评\"主题的互动率是全站平均的 3.1 倍",
      "confidence": 0.92,
      "sample_count": 4,
      "recommendation": "增加 AI 工具测评类内容的发布频率"
    }
  ]
}
```

#### 4.7.3 标准更新器（Criteria Updater）

分析引擎的洞察 → 自动写入 `criteria/` 目录的 Markdown 文件：

```
分析引擎发现：
  疑问句标题效果好 (+42%)
  ↓
标准更新器执行：
  读取 criteria/xiaohongshu.md
  在 ## 内容要求 下追加一行：
  "标题建议：优先使用疑问句（如'你是不是也...'）"
  ↓
下次 AI 审核读取文件时自动采用新标准
  ↓
未来内容质量提升 → 更好的数据 → 更多洞察 → 持续迭代
```

**更新规则：**

- **高置信度洞察（≥ 0.8）** → 自动写入 criteria 文件
- **中置信度（0.6-0.8）** → 写入但标记为"实验性建议"
- **低置信度（< 0.6）** → 仅记录，不修改标准
- **Jayson 可随时手动覆盖或回滚任何自动修改**（通过 Git）

#### 4.7.4 平台感知差异化

不同平台的观众偏好天然不同，系统通过**独立的数据管道 + 独立的 criteria 文件**来捕捉这种差异：

```
同一篇内容发布到不同平台：

小红书:  点赞 520, 收藏 180    → 分析 → 更新 xiaohongshu.md
                               结论：深度干货型内容在小红书表现好
LinkedIn: 点赞 89, 评论 23     → 分析 → 更新 linkedin.md
                               结论：行业观点型内容在 LinkedIn 表现好
```

这意味着即便同一篇原文，在不同平台上被分析器"看到"的价值维度也不同。
系统不会假设"好内容在所有平台都好"，而是让每个平台独立学习。

#### 4.7.5 渐进式生效

feedback loop 的效果是**渐进累加**的：

| 阶段 | 数据量 | 效果 |
|------|--------|------|
| 第 1 周 | 5-10 篇 | 基础模式识别（标题/长度） |
| 第 1 个月 | 30-50 篇 | 主题偏好识别 |
| 第 3 个月 | 100+ 篇 | 精细调整（语气/结构/视觉） |
| 第 6 个月 | 200+ 篇 | 跨平台差异化成熟 |

#### 4.7.6 人工介入点

Jayson 在任何时候都可以：

- **查看洞察报告**：`pipeline insights --platform xiaohongshu`
- **审核自动修改**：`git diff criteria/` 查看本周自动变更
- **回滚**：`git checkout -- criteria/xiaohongshu.md`
- **手动添加标准**：直接编辑 `criteria/*.md`，AI 下次读取即生效

---

## 5. 平台支持矩阵

### 5.1 最终目标平台

| 平台 | 类型 | 文本 | 图片 | 视频 | 认证方式 | 优先级 |
|------|------|------|------|------|---------|--------|
| 小红书 | 图文/视频 | ✅ | ✅ | ✅ | Cookie (Playwright) | P0 |
| Bilibili | 视频/专栏 | ✅ | ✅ | ✅ | Cookie/API | P1 |
| LinkedIn | 专业长文 | ✅ | ✅ | ✅ | API v2 | P1 |
| Twitter/X | 短文 | ✅ | ✅ | ✅ | API v2 (OAuth 2.0) | P1 |
| TikTok | 短视频 | ✅ | ❌ | ✅ | API / Cookie | P2 |
| YouTube | 视频 | ✅ | ❌ | ✅ | API v3 (OAuth) | P2 |
| Threads | 短文 | ✅ | ✅ | ❌ | API (待发布) | P3 |

### 5.2 平台约束汇总

| 平台 | 最大字数 | 图片上限 | 视频上限 | 最佳发帖时间 |
|------|---------|---------|---------|------------|
| 小红书 | 1000 | 18 | 5min | 07:00-09:00, 18:00-22:00 |
| Bilibili | 5000+ | 不限 | 不限 | 12:00-14:00, 18:00-22:00 |
| LinkedIn | 3000 | 20 | 10min | 08:00-10:00, 17:00-18:00 |
| Twitter | 280 (付费 4000) | 4 | 2min 20s | 08:00-10:00, 17:00-19:00 |
| TikTok | 2200 | 不适用 | 10min | 11:00-13:00, 19:00-22:00 |
| YouTube | 5000 | 1 (thumbnail) | 不限 | 14:00-16:00 |

---

## 6. 多模态支持

### 6.1 文本（已实现）

- 标准 Markdown 格式输入
- 平台自动适配（长度、风格、标签）
- 多版本管理（一条内容不同平台的版本独立存储）

### 6.2 图片（部分实现）

**当前**:
- DALL-E 3 AI 生成（需 API Key）
- FFmpeg 文字封面（备选）

**未来**:
- 多模型支持（DALL-E / Midjourney / Stable Diffusion）
- 模板库：预设的视觉模板 + 内容填充
- 信息图：数据 → 图表 → 导出图片
- 图片风格化：统一视觉风格

### 6.3 视频（部分实现）

**当前**:
- FFmpeg 幻灯片生成
- Ken Burns 效果
- TTS 配音（ElevenLabs / macOS say）
- 背景音乐叠加

**未来**:
- AI 视频模型（Runway / Pika / Luma / Seedance 2.0）
- 自动剪辑：根据内容自动选择镜头和转场
- 字幕生成：语音 → 字幕 → 嵌入视频
- 短视频模板：适合 TikTok/Reels 的自动生成
- 视频缩略图生成

### 6.4 跨模态组合

内容可以指定使用多种模态的组合发布到不同平台：

```
一条内容 = {
  text: "原始长文",
  images: [...],
  video: "...",
  platform_variants: {
    小红书: { text: "...", images: [...] },
    Twitter: { text: "..." },
    YouTube: { text: "...", video: "..." },
  }
}
```

---

## 7. 自动化级别

每条内容/每个平台可以独立配置自动化级别。默认由 AI 审核决定。

| 级别 | 说明 | 适用场景 |
|------|------|---------|
| `auto` | AI 审核 → 通过 → 直接发布，无需人工 | 常规内容，AI 置信度高 |
| `review_auto` | AI 审核 → 低置信度时通知人，其余自动 | 新类型内容、实验性内容 |
| `manual` | AI 做格式处理和生成，不自动发布，等待 Jayson 指令 | 重要声明、敏感话题 |

自动化级别的决定权可以交给 AI Review Panel：

```yaml
# 自动决定每条内容使用哪个级别
auto_level_selection:
  enabled: true
  rules:
    - if: "review.confidence >= 0.85 and no flags → auto"
    - if: "review.confidence >= 0.7 or minor flags → review_auto"
    - else: "manual"
```

人类可以通过 CLI 覆盖任何内容的自动化级别：`pipeline override <id> --level auto`

---

## 8. 质量标准与测试

### 8.1 测试策略

- **单元测试**：每个模块的独立测试（pytest）
- **集成测试**：多模块联合测试（mock 外部服务）
- **E2E 测试**：完整流程测试（可选，需要真实凭证）
- **CI/CD**：GitHub Actions，push/PR 自动运行

### 8.2 测试覆盖率目标

| 模块 | 覆盖率目标 |
|------|-----------|
| Models | 100% |
| Config | 100% |
| Pipeline | 90%+ |
| Publishers (base) | 90%+ |
| Publishers (per platform) | 80%+ |
| Media | 80%+ |
| CLI | 70%+ |

### 8.3 发布前检查清单

- [ ] 所有测试通过
- [ ] lint 无错误（ruff）
- [ ] 配置验证通过
- [ ] CLIs 测试用例通过
- [ ] 不涉及敏感信息泄露

---

## 9. 运维与可观测

### 9.1 日志

- 结构化日志（JSON 格式）
- 每个发布操作记录：content_id, platform, status, duration, error
- 日志级别可配置（DEBUG / INFO / WARNING / ERROR）

### 9.2 监控

- **Pipeline 心跳**：定时报告管道状态
- **发布成功率**：每个平台的成功率统计
- **队列长度**：待处理、待发布的内容数量
- **错误告警**：连续失败超过阈值时通知

### 9.3 CLI 命令一览

| 命令 | 功能 | 状态 |
|------|------|------|
| `pipeline status` | 管道状态总览 | ✅ |
| `pipeline list <folder>` | 列出内容 | ✅ |
| `pipeline create` | 创建新内容 | ✅ |
| `pipeline publish <id>` | 发布内容 | ✅ |
| `pipeline video generate` | 视频生成 | ✅ |
| `pipeline image generate` | 图片生成 | ✅ |
| `pipeline auth <platform>` | 平台登录 | ✅ |
| `pipeline review <id>` | 触发 AI 审核 | ❌ |
| `pipeline override <id>` | 覆盖审核/自动化级别 | ❌ |
| `pipeline schedule <id> <time>` | 定时发布 | ❌ |
| `pipeline queue` | 查看发布队列 | ❌ |
| `pipeline insights` | 查看效果洞察报告 | ❌ |
| `pipeline criteria list` | 列出审核标准文件 | ❌ |
| `pipeline criteria edit <platform>` | 编辑指定平台审核标准 | ❌ |
| `pipeline log` | 查看日志 | ❌ |

---

## 10. 实施路线图

### Phase 1 ✅ 已完成
- 规范化项目结构为 Python package
- 发布到 GitHub repo
- 31 项基础测试
- CLI 入口

### Phase 2 🔜 下一阶段
- GitHub Actions CI/CD
- AI Review Panel 实现（AI 伪人工审核）
- 可编辑的审核标准文件系统（criteria/）
- Bilibili 发布器
- LinkedIn 发布器
- Twitter 发布器
- 定时发布 / scheduling
- 扩展测试套件

### Phase 3
- 效果反馈回路（Analytics Feedback Loop）
  - 发布后数据收集器（各平台 API）
  - 分析引擎（Insight Engine）
  - 标准更新器（Criteria Updater）
- TikTok 发布器
- YouTube 发布器
- Seedance 2.0 视频 API 集成
- 图片自动生成 + 发布集成

### Phase 4
- Threads 发布器
- Analytics / 效果追踪
- 内容模板库
- Notion / 外部数据源同步
- Web UI（可选）

---

## 11. 附录

### A. 数据模型参照

```python
@dataclass
class Content:
    id: str                    # 唯一 ID
    title: str                 # 标题
    body: str                  # 正文（原始长文）
    status: ContentStatus      # 生命周期状态
    platforms: list[Platform]  # 目标平台
    tags: list[str]            # 标签
    created: str               # 创建时间
    updated: str               # 更新时间
    published_at: str          # 发布时间
    source_url: str            # 原文链接
    images: list[str]          # 图片路径
    video_path: str            # 视频路径
    platform_variants: dict    # 各平台适配版本
    review_result: dict | None # AI 审核结果（详见 4.3.5）
    review_level: str          # 自动化级别: auto / review_auto / manual
```

### B. 文件夹结构（最终）

```
content-pipeline/
├── src/content_pipeline/      # 核心包
│   ├── models.py              # 数据模型
│   ├── config.py              # 配置管理
│   ├── pipeline.py            # 流程编排 + ContentStore
│   ├── stages.py              # 处理阶段
│   ├── reviewer.py            # AI 审核引擎
│   ├── analyzer.py            # 效果分析引擎
│   ├── criteria_updater.py    # 审核标准自动更新器
│   ├── cli.py                 # CLI
│   ├── publishers/            # 发布器（每个平台独立文件）
│   │   ├── base.py            # BasePublisher
│   │   ├── xiaohongshu.py
│   │   ├── bilibili.py
│   │   ├── linkedin.py
│   │   ├── twitter.py
│   │   ├── tiktok.py
│   │   ├── youtube.py
│   │   └── threads.py
│   └── media/                 # 媒体生成（独立模块）
│       ├── image.py
│       ├── video.py
│       └── audio.py
├── criteria/                  # 审核标准（可编辑 Markdown）
│   ├── default.md
│   ├── xiaohongshu.md
│   ├── bilibili.md
│   ├── linkedin.md
│   ├── twitter.md
│   └── metrics/               # 历史指标（系统自动写入）
│       ├── xiaohongshu_performance.md
│       └── ...
├── tests/                     # 测试
├── content/                   # 内容存储
│   ├── input/                 # 新内容
│   ├── processing/            # 处理中
│   ├── queue/                 # 待发布
│   ├── published/             # 已发布
│   └── output/                # 生成的文件
├── .github/workflows/         # CI/CD
├── pyproject.toml
└── README.md
```
