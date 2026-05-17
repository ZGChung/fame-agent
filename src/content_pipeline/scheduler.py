"""
Content Pipeline — 发布调度器

定时发布、队列管理、频率控制、重试机制、幂等保证。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import BASE_DIR, PipelineConfig
from .models import Content, ContentStatus, Platform, PublishResult
from .pipeline import Pipeline
from .publishers.base import PublisherRegistry

logger = logging.getLogger(__name__)

# ── Data Structures ───────────────────────────────────────────────────────────


@dataclass
class QueueItem:
    """队列中的一条待发布项"""

    id: str
    content_id: str
    platform: str  # Platform.value
    scheduled_at: str  # ISO datetime
    priority: int = 0  # 越高越优先, default 0
    created_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    retry_count: int = 0
    max_retries: int = 3
    last_attempt_at: Optional[str] = None
    last_error: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, failed

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content_id": self.content_id,
            "platform": self.platform,
            "scheduled_at": self.scheduled_at,
            "priority": self.priority,
            "created_at": self.created_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "last_attempt_at": self.last_attempt_at,
            "last_error": self.last_error,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> QueueItem:
        return cls(
            id=d["id"],
            content_id=d["content_id"],
            platform=d["platform"],
            scheduled_at=d["scheduled_at"],
            priority=d.get("priority", 0),
            created_at=d.get("created_at", ""),
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 3),
            last_attempt_at=d.get("last_attempt_at"),
            last_error=d.get("last_error"),
            status=d.get("status", "pending"),
        )


@dataclass
class PlatformRateLimit:
    """平台频率限制配置"""

    max_per_day: int = 3
    max_per_week: int = 21


@dataclass
class ScheduleState:
    """调度器完整状态（可序列化到 JSON）"""

    queue: list[QueueItem] = field(default_factory=list)
    platform_counters: dict[str, dict] = field(default_factory=dict)
    # {"xiaohongshu": {"2024-01-01": 3, "2024-W01": 12}}
    version: str = "1.0"

    def to_dict(self) -> dict:
        return {
            "queue": [item.to_dict() for item in self.queue],
            "platform_counters": self.platform_counters,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ScheduleState:
        return cls(
            queue=[QueueItem.from_dict(it) for it in d.get("queue", [])],
            platform_counters=d.get("platform_counters", {}),
            version=d.get("version", "1.0"),
        )


# ── Scheduler ─────────────────────────────────────────────────────────────────


class PipelineScheduler:
    """发布调度器 — 管理定时发布队列、频率控制与重试逻辑"""

    DEFAULT_RATE_LIMITS: dict[str, PlatformRateLimit] = {
        "xiaohongshu": PlatformRateLimit(max_per_day=3, max_per_week=21),
        "twitter": PlatformRateLimit(max_per_day=5, max_per_week=35),
        "linkedin": PlatformRateLimit(max_per_day=2, max_per_week=10),
        "zhihu": PlatformRateLimit(max_per_day=3, max_per_week=21),
        "bilibili": PlatformRateLimit(max_per_day=2, max_per_week=14),
        "youtube": PlatformRateLimit(max_per_day=1, max_per_week=7),
        "tiktok": PlatformRateLimit(max_per_day=2, max_per_week=14),
    }

    def __init__(
        self,
        config: PipelineConfig,
        pipeline: Pipeline,
        registry: PublisherRegistry | None = None,
        queue_path: str | Path | None = None,
        rate_limits: dict[str, PlatformRateLimit] | None = None,
    ):
        self.config = config
        self.pipeline = pipeline
        self.registry = registry or PublisherRegistry()
        self.rate_limits = rate_limits or dict(self.DEFAULT_RATE_LIMITS)

        # Queue persistence path
        if queue_path:
            self._queue_path = Path(queue_path)
        else:
            self._queue_path = BASE_DIR / "content" / "queue" / "schedule.json"

        self._state: ScheduleState = ScheduleState()
        self._next_item_id = 1

    # ── Persistence ───────────────────────────────────────────────────────

    @property
    def queue_path(self) -> Path:
        return self._queue_path

    def save_state(self) -> None:
        """将队列状态持久化到 JSON 文件"""
        self._queue_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._state.to_dict()
        self._queue_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug("Queue state saved to %s (%d items)", self._queue_path, len(self._state.queue))

    def load_state(self) -> None:
        """从 JSON 文件恢复队列状态"""
        if not self._queue_path.exists():
            logger.debug("No queue state file at %s, starting fresh", self._queue_path)
            return

        try:
            raw = self._queue_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._state = ScheduleState.from_dict(data)

            # Recover next_item_id
            if self._state.queue:
                max_id = max(
                    (int(it.id) for it in self._state.queue if it.id.isdigit()),
                    default=0,
                )
                self._next_item_id = max_id + 1

            logger.info("Loaded queue state: %d items", len(self._state.queue))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load queue state, starting fresh: %s", e)
            self._state = ScheduleState()

    # ── Queue Management ──────────────────────────────────────────────────

    def _generate_item_id(self) -> str:
        item_id = str(self._next_item_id)
        self._next_item_id += 1
        return item_id

    def _is_duplicate(self, content_id: str, platform: str) -> bool:
        """检查是否已存在相同内容和平台的待发布项"""
        for item in self._state.queue:
            if (
                item.content_id == content_id
                and item.platform == platform
                and item.status in ("pending", "processing")
            ):
                return True
        return False

    def enqueue(
        self,
        content_id: str,
        scheduled_at: str | None = None,
        priority: int = 0,
        platform: str | None = None,
    ) -> QueueItem | None:
        """
        将内容加入发布队列。

        Args:
            content_id: 内容 ID
            scheduled_at: 计划发布时间 (ISO 格式)，None 则立即发布
            priority: 优先级 (越高越靠前)，高优内容插队
            platform: 指定平台，None 则使用内容配置的所有平台

        Returns:
            QueueItem 或 None（如果内容不存在）
        """
        # Validate content exists
        content = self.pipeline.store.get_content(content_id)
        if not content:
            logger.warning("Cannot enqueue: content %s not found", content_id)
            return None

        # Determine platforms
        platforms = (
            [platform] if platform
            else [p.value for p in content.platforms]
        )

        # Determine scheduled time
        if scheduled_at is None:
            scheduled_at = datetime.now().isoformat()

        items = []
        for plat in platforms:
            # Duplicate prevention
            if self._is_duplicate(content_id, plat):
                logger.info(
                    "Skipping duplicate: content=%s platform=%s already queued",
                    content_id, plat,
                )
                continue

            item = QueueItem(
                id=self._generate_item_id(),
                content_id=content_id,
                platform=plat,
                scheduled_at=scheduled_at,
                priority=priority,
            )
            self._state.queue.append(item)
            items.append(item)
            logger.info("Enqueued %s → %s @ %s (priority=%d)", content_id, plat, scheduled_at, priority)

        if items:
            # Update content status to SCHEDULED
            self.pipeline.store.update_status(content_id, ContentStatus.SCHEDULED)
            self.save_state()

        return items[0] if items else None

    def dequeue(self, item_id: str) -> bool:
        """从队列中移除指定项（通常用于取消或完成）"""
        for i, item in enumerate(self._state.queue):
            if item.id == item_id:
                self._state.queue.pop(i)
                self.save_state()
                logger.info("Dequeued item %s", item_id)
                return True
        logger.warning("Item %s not found in queue", item_id)
        return False

    def list_queue(self, status: str | None = None) -> list[QueueItem]:
        """
        列出队列中的所有项，按优先级降序 + 计划时间升序排列。

        Args:
            status: 过滤状态 (pending, processing, completed, failed), None 返回全部
        """
        items = self._state.queue
        if status:
            items = [it for it in items if it.status == status]

        # Sort: higher priority first, then earlier scheduled time
        items.sort(key=lambda it: (-it.priority, it.scheduled_at))
        return items

    def upcoming_schedule(self, days: int = 7) -> list[QueueItem]:
        """
        Get upcoming publishing schedule for the next N days.
        Only includes pending items.
        """
        now = datetime.now()
        cutoff = now + timedelta(days=days)
        upcoming = []

        for item in self._state.queue:
            if item.status != "pending":
                continue
            try:
                sched = datetime.fromisoformat(item.scheduled_at)
            except ValueError:
                continue
            if now <= sched <= cutoff:
                upcoming.append(item)

        upcoming.sort(key=lambda it: (-it.priority, it.scheduled_at))
        return upcoming

    # ── Rate Limiting ─────────────────────────────────────────────────────

    def _get_day_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _get_week_key(self) -> str:
        now = datetime.now()
        iso = now.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    def _get_platform_counter(self, platform: str, key: str) -> int:
        return self._state.platform_counters.get(platform, {}).get(key, 0)

    def _increment_platform_counter(self, platform: str, key: str) -> None:
        if platform not in self._state.platform_counters:
            self._state.platform_counters[platform] = {}
        self._state.platform_counters[platform][key] = (
            self._state.platform_counters[platform].get(key, 0) + 1
        )

    def check_rate_limit(self, platform: str) -> tuple[bool, str]:
        """
        检查平台是否超过频率限制。

        Returns:
            (allowed, reason) — True if publishing is allowed
        """
        limit = self.rate_limits.get(platform)
        if not limit:
            return True, ""

        day_key = self._get_day_key()
        week_key = self._get_week_key()

        day_count = self._get_platform_counter(platform, day_key)
        week_count = self._get_platform_counter(platform, week_key)

        if limit.max_per_day > 0 and day_count >= limit.max_per_day:
            return False, f"Daily limit reached ({day_count}/{limit.max_per_day})"

        if limit.max_per_week > 0 and week_count >= limit.max_per_week:
            return False, f"Weekly limit reached ({week_count}/{limit.max_per_week})"

        return True, ""

    def get_platform_stats(self) -> dict:
        """获取各平台当前频率统计"""
        day_key = self._get_day_key()
        week_key = self._get_week_key()
        stats = {}

        for platform, limit in self.rate_limits.items():
            stats[platform] = {
                "daily_used": self._get_platform_counter(platform, day_key),
                "daily_limit": limit.max_per_day,
                "weekly_used": self._get_platform_counter(platform, week_key),
                "weekly_limit": limit.max_per_week,
            }
        return stats

    # ── Publishing & Retry ────────────────────────────────────────────────

    def _get_retry_delay(self, retry_count: int) -> float:
        """
        指数退避延迟（秒）。

        Attempt 1 (first retry): 60s
        Attempt 2: 300s (5 min)
        Attempt 3: 900s (15 min)
        """
        delays = [60, 300, 900]
        idx = min(retry_count, len(delays) - 1)
        return delays[idx]

    def _is_due(self, item: QueueItem) -> bool:
        """检查项是否到了发布时间"""
        if item.status != "pending":
            return False
        try:
            sched = datetime.fromisoformat(item.scheduled_at)
        except ValueError:
            return True  # Invalid datetime → publish immediately
        return datetime.now() >= sched

    def _is_ready_for_retry(self, item: QueueItem) -> bool:
        """检查失败的项是否到了重试时间"""
        if item.status != "failed":
            return False
        if item.retry_count >= item.max_retries:
            return False
        if not item.last_attempt_at:
            return True
        try:
            last = datetime.fromisoformat(item.last_attempt_at)
        except ValueError:
            return True

        delay = self._get_retry_delay(item.retry_count)
        return (datetime.now() - last).total_seconds() >= delay

    def process_queue(self, dry_run: bool = False) -> dict:
        """
        处理发布队列 — 发布所有到期项，处理重试。

        Returns:
            dict with results summary
        """
        results = {
            "published": [],
            "failed": [],
            "rate_limited": [],
            "retried": [],
        }

        self.load_state()

        # Collect items to process
        to_process = []
        for item in self._state.queue:
            if item.status == "pending" and self._is_due(item):
                to_process.append(item)
            elif item.status == "failed" and self._is_ready_for_retry(item):
                to_process.append(item)

        # Sort by priority (desc) then scheduled_at (asc)
        to_process.sort(key=lambda it: (-it.priority, it.scheduled_at))

        for item in to_process:
            # Rate limit check
            allowed, reason = self.check_rate_limit(item.platform)
            if not allowed:
                results["rate_limited"].append({
                    "item_id": item.id,
                    "content_id": item.content_id,
                    "platform": item.platform,
                    "reason": reason,
                })
                logger.info("Rate limited: %s on %s — %s", item.content_id, item.platform, reason)
                continue

            if dry_run:
                results["published"].append({
                    "item_id": item.id,
                    "content_id": item.content_id,
                    "platform": item.platform,
                    "dry_run": True,
                })
                continue

            # Publish
            was_retry = item.status == "failed"
            item.status = "processing"
            item.last_attempt_at = datetime.now().isoformat()

            content = self.pipeline.store.get_content(item.content_id)
            if not content:
                item.status = "failed"
                item.last_error = f"Content {item.content_id} not found"
                results["failed"].append({
                    "item_id": item.id,
                    "content_id": item.content_id,
                    "platform": item.platform,
                    "error": item.last_error,
                })
                self.save_state()
                continue

            publisher = self.registry.get(item.platform)
            if not publisher:
                item.status = "failed"
                item.last_error = f"No publisher registered for {item.platform}"
                results["failed"].append({
                    "item_id": item.id,
                    "content_id": item.content_id,
                    "platform": item.platform,
                    "error": item.last_error,
                })
                self.save_state()
                continue

            try:
                result: PublishResult = publisher.publish(content)
            except Exception as e:
                result = PublishResult(
                    platform=Platform(item.platform),
                    success=False,
                    error=str(e),
                )

            if result.success:
                item.status = "completed"
                day_key = self._get_day_key()
                week_key = self._get_week_key()
                self._increment_platform_counter(item.platform, day_key)
                self._increment_platform_counter(item.platform, week_key)

                entry = {
                    "item_id": item.id,
                    "content_id": item.content_id,
                    "platform": item.platform,
                    "url": result.url,
                    "post_id": result.post_id,
                }
                if was_retry:
                    results["retried"].append(entry)
                else:
                    results["published"].append(entry)

                # Update content status
                self.pipeline.store.update_status(item.content_id, ContentStatus.PUBLISHED)
                logger.info("Published %s → %s (%s)", item.content_id, item.platform, result.url)

            else:
                item.retry_count += 1
                if item.retry_count >= item.max_retries:
                    item.status = "failed"
                    item.last_error = result.error or "Unknown error"
                else:
                    # Keep as failed, ready for retry
                    item.status = "failed"
                    item.last_error = result.error or "Unknown error"

                results["failed"].append({
                    "item_id": item.id,
                    "content_id": item.content_id,
                    "platform": item.platform,
                    "error": item.last_error,
                    "retry_count": item.retry_count,
                    "will_retry": item.retry_count < item.max_retries,
                })
                logger.warning(
                    "Failed to publish %s → %s (retry %d/%d): %s",
                    item.content_id, item.platform, item.retry_count, item.max_retries, item.last_error,
                )

        self.save_state()
        return results

    # ── Queue Cleanup ─────────────────────────────────────────────────────

    def cleanup_completed(self) -> int:
        """Remove completed items from the queue. Returns count removed."""
        before = len(self._state.queue)
        self._state.queue = [
            it for it in self._state.queue if it.status != "completed"
        ]
        removed = before - len(self._state.queue)
        if removed:
            self.save_state()
            logger.info("Cleaned up %d completed items", removed)
        return removed
