"""
Content Pipeline — 数据模型

核心实体定义，不依赖任何外部服务。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class ContentStatus(Enum):
    """内容生命周期状态"""
    IDEA = "idea"
    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Platform(Enum):
    """支持的发布平台（完全解耦，互不依赖）"""
    XIAOHONGSHU = "xiaohongshu"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    ZHIHU = "zhihu"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"


PLATFORM_EMOJI = {
    Platform.XIAOHONGSHU: "📕",
    Platform.TWITTER: "🐦",
    Platform.LINKEDIN: "💼",
    Platform.ZHIHU: "📖",
    Platform.YOUTUBE: "🎬",
    Platform.TIKTOK: "🎵",
}

PLATFORM_MAX_CHARS = {
    Platform.XIAOHONGSHU: 1000,
    Platform.TWITTER: 280,
    Platform.LINKEDIN: 3000,
    Platform.ZHIHU: 10000,
    Platform.YOUTUBE: 5000,
    Platform.TIKTOK: 2200,
}


@dataclass
class Content:
    """一条内容的完整表示"""
    id: str
    title: str
    body: str
    status: ContentStatus = ContentStatus.IDEA
    platforms: list[Platform] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    updated: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    published_at: Optional[str] = None
    source_url: Optional[str] = None
    images: list[str] = field(default_factory=list)
    video_path: Optional[str] = None
    platform_variants: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_markdown(cls, file_path: str | Path) -> Content:
        """
        从 Markdown 文件解析 Content。
        支持 YAML frontmatter（--- 开头和结尾）或简单标题格式。
        """
        path = Path(file_path)
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")

        meta: dict = {}
        body_start = 0

        # 尝试解析 YAML frontmatter
        if lines and lines[0].strip() == "---":
            fm_end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    fm_end = i
                    break
            if fm_end:
                for line in lines[1:fm_end]:
                    if ":" in line:
                        key, _, val = line.partition(":")
                        meta[key.strip()] = val.strip().strip('"').strip("'")
                body_start = fm_end + 1

        # 提取正文
        raw_body = "\n".join(lines[body_start:]).strip()
        body = raw_body

        # 从 frontmatter 或第一行标题提取 title
        title = meta.get("title", "")
        if not title:
            for line in lines[body_start:]:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

        # 解析 platforms
        platforms_raw = meta.get("platforms", "[]")
        if isinstance(platforms_raw, str):
            import json
            try:
                platforms_raw = json.loads(platforms_raw)
            except json.JSONDecodeError:
                platforms_raw = [p.strip() for p in platforms_raw.split(",") if p.strip()]
        platforms = []
        for p in platforms_raw:
            try:
                platforms.append(Platform(p.lower()))
            except ValueError:
                pass

        # 解析 status
        status = ContentStatus.IDEA
        status_raw = meta.get("status", "idea")
        try:
            status = ContentStatus(status_raw.lower())
        except ValueError:
            pass

        content_id = meta.get("id", path.stem)

        # 解析 tags
        tags_raw = meta.get("tags", "")
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        else:
            tags = list(tags_raw)

        return cls(
            id=content_id,
            title=title,
            body=body,
            status=status,
            platforms=platforms,
            tags=tags,
            created=meta.get("created", datetime.now().strftime("%Y-%m-%d")),
            updated=meta.get("updated", ""),
            published_at=meta.get("published_at"),
            source_url=meta.get("source_url"),
        )

    def to_markdown(self) -> str:
        """序列化为 Markdown 文件（带 frontmatter）"""
        import json

        lines = ["---"]
        lines.append(f"id: {self.id}")
        lines.append(f'title: "{self.title}"')
        lines.append(f"status: {self.status.value}")
        lines.append(f"platforms: {json.dumps([p.value for p in self.platforms])}")
        lines.append(f"tags: {json.dumps(self.tags)}")
        lines.append(f'created: "{self.created}"')
        if self.updated:
            lines.append(f'updated: "{self.updated}"')
        if self.published_at:
            lines.append(f'published_at: "{self.published_at}"')
        if self.source_url:
            lines.append(f"source_url: {self.source_url}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(self.body)
        lines.append("")
        return "\n".join(lines)

    @property
    def emoji(self) -> str:
        """返回第一个平台的 emoji"""
        for p in self.platforms:
            return PLATFORM_EMOJI.get(p, "📄")
        return "📄"

    @property
    def summary(self) -> str:
        """简短摘要（前 80 字）"""
        clean = re.sub(r"\s+", " ", self.body).strip()
        return clean[:80] + ("..." if len(clean) > 80 else "")


@dataclass
class PublishResult:
    """发布结果"""
    platform: Platform
    success: bool
    url: Optional[str] = None
    post_id: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
