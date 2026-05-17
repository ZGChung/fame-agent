"""
Content Pipeline — 流程编排

定义内容从输入到发布的完整生命周期管理。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import BASE_DIR, PipelineConfig
from .models import Content, ContentStatus, Platform

logger = logging.getLogger(__name__)


class ContentStore:
    """
    内容存储 — 管理文件系统上的内容仓库。
    
    每个内容是一个 .md 文件，存放在不同状态对应的文件夹中。
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保所有内容目录存在"""
        for folder in ["input", "processing", "queue", "published", "output"]:
            path = self.config.resolve_path(self.config.content_root, folder)
            path.mkdir(parents=True, exist_ok=True)

    def _folder_path(self, folder: str) -> Path:
        """获取指定状态文件夹的路径"""
        folder_map = {
            "input": self.config.input_folder,
            "processing": self.config.processing_folder,
            "queue": self.config.queue_folder,
            "published": self.config.published_folder,
            "output": self.config.output_folder,
        }
        rel = folder_map.get(folder, folder)
        return self.config.resolve_path(self.config.content_root, rel)

    def list_content(self, folder: str) -> list[Content]:
        """列出指定文件夹中的所有内容"""
        path = self._folder_path(folder)
        contents = []

        if path.exists():
            for f in sorted(path.glob("*.md")):
                try:
                    contents.append(Content.from_markdown(f))
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", f.name, e)

        # 也搜索历史文件夹
        legacy_name = {"published": "published", "processing": "blog", "input": "blog"}.get(folder)
        if not legacy_name:
            legacy_name = folder
        if hasattr(self.config, '_legacy_folders') and legacy_name in self.config._legacy_folders:
            legacy_path = Path(self.config._legacy_folders[legacy_name])
            if legacy_path.exists():
                for f in sorted(legacy_path.glob("*.md")):
                    # 避免重复
                    if not any(c.id == f.stem for c in contents):
                        try:
                            contents.append(Content.from_markdown(f))
                        except Exception:
                            pass

        return contents

    def get_content(self, content_id: str) -> Optional[Content]:
        """在所有文件夹中查找指定 ID 的内容"""
        for folder in ["input", "processing", "queue", "published"]:
            path = self._folder_path(folder)
            for f in path.glob(f"{content_id}*.md"):
                try:
                    return Content.from_markdown(f)
                except Exception:
                    continue
        return None

    def save(self, content: Content, folder: str) -> Path:
        """保存内容到指定文件夹"""
        dir_path = self._folder_path(folder)
        dir_path.mkdir(parents=True, exist_ok=True)

        # 文件名：{id}_{title_slug}.md
        title_slug = content.title.replace(" ", "-")[:30]
        file_path = dir_path / f"{content.id}_{title_slug}.md"

        file_path.write_text(content.to_markdown(), encoding="utf-8")
        return file_path

    def move(self, content_id: str, from_folder: str, to_folder: str) -> bool:
        """移动内容到另一个文件夹"""
        content = self.get_content(content_id)
        if not content:
            return False

        # 保存到目标文件夹
        self.save(content, to_folder)

        # 从源文件夹删除
        src_path = self._folder_path(from_folder)
        for f in src_path.glob(f"{content_id}*.md"):
            f.unlink()

        return True

    def update_status(self, content_id: str, new_status: ContentStatus) -> bool:
        """更新内容状态"""
        content = self.get_content(content_id)
        if not content:
            return False

        content.status = new_status
        content.updated = datetime.now().strftime("%Y-%m-%d")

        # 找到当前文件夹
        for folder in ["input", "processing", "queue", "published"]:
            path = self._folder_path(folder)
            for f in path.glob(f"{content_id}*.md"):
                f.unlink()
                break

        # 根据状态决定目标文件夹
        target = {
            ContentStatus.IDEA: "input",
            ContentStatus.DRAFTING: "processing",
            ContentStatus.REVIEWING: "processing",
            ContentStatus.SCHEDULED: "queue",
            ContentStatus.PUBLISHED: "published",
            ContentStatus.ARCHIVED: "published",
        }.get(new_status, "input")

        self.save(content, target)
        return True

    def get_next_id(self) -> str:
        """生成下一个内容 ID"""
        all_ids = []
        for folder in ["input", "processing", "queue", "published"]:
            path = self._folder_path(folder)
            if path.exists():
                for f in path.glob("*.md"):
                    stem = f.stem
                    # 提取前缀数字（如 "012_two_types" -> "012"）
                    parts = stem.split("_")
                    if parts and parts[0].isdigit():
                        all_ids.append(int(parts[0]))

        if not all_ids:
            return "001"
        return f"{max(all_ids) + 1:03d}"


class Pipeline:
    """
    Pipeline 主调度器 — 编排内容从创建到发布的完整流程。
    
    使用策略：
    - 每个 Stage 是一个独立的处理步骤
    - 状态转换由 Pipeline 控制
    - 各平台发布器通过注册表调用
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig.load()
        self.store = ContentStore(self.config)
        self._publishers: dict[str, object] = {}

    def register_publisher(self, platform: str, publisher: object):
        """注册平台发布器"""
        self._publishers[platform] = publisher

    def get_publisher(self, platform: str):
        """获取指定平台的发布器"""
        return self._publishers.get(platform)

    def create_content(self, title: str, body: str, platforms: list[str] | None = None) -> Content:
        """创建新内容"""
        content_id = self.store.get_next_id()
        platform_objs = []
        if platforms:
            for p in platforms:
                try:
                    platform_objs.append(Platform(p.lower()))
                except ValueError:
                    logger.warning("Unknown platform: %s", p)

        content = Content(
            id=content_id,
            title=title,
            body=body,
            platforms=platform_objs or [Platform.XIAOHONGSHU],
        )
        self.store.save(content, "input")
        return content

    def publish(self, content_id: str, platform: str | None = None) -> dict:
        """发布内容到指定平台（或所有配置的平台）"""
        from .models import PublishResult

        content = self.store.get_content(content_id)
        if not content:
            return {"error": f"Content {content_id} not found"}

        targets = [platform] if platform else [p.value for p in content.platforms]
        results = {}

        for p in targets:
            publisher = self._publishers.get(p)
            if not publisher:
                results[p] = PublishResult(
                    platform=Platform(p),
                    success=False,
                    error=f"No publisher registered for {p}",
                )
                continue

            try:
                result = publisher.publish(content)
                results[p] = result
                if result.success:
                    logger.info("Published %s to %s: %s", content_id, p, result.url)
                else:
                    logger.error("Failed to publish %s to %s: %s", content_id, p, result.error)
            except Exception as e:
                results[p] = PublishResult(
                    platform=Platform(p),
                    success=False,
                    error=str(e),
                )
                logger.exception("Error publishing %s to %s", content_id, p)

        # 如果至少一个平台发布成功，更新状态
        if any(r.success for r in results.values()):
            self.store.update_status(content_id, ContentStatus.PUBLISHED)

        return {
            k: {
                "success": v.success,
                "url": v.url,
                "post_id": v.post_id,
                "error": v.error,
            }
            for k, v in results.items()
        }

    def status(self) -> dict:
        """获取当前 pipeline 状态"""
        return {
            "input": len(self.store.list_content("input")),
            "processing": len(self.store.list_content("processing")),
            "queue": len(self.store.list_content("queue")),
            "published": len(self.store.list_content("published")),
            "platforms": {
                name: self._publishers.get(name) is not None
                for name in ["xiaohongshu", "twitter", "linkedin", "zhihu"]
            },
        }

    def run_once(self) -> dict:
        """
        运行一次自动处理：
        1. 处理 input → processing（自动生成草稿变体）
        2. 检查 queue 中待发布内容 → 自动发布
        """
        results = {"processed": [], "published": []}

        # 暂不自动处理，需要人类审核
        # 这里只做状态报告
        status = self.status()
        results["status"] = status
        return results
