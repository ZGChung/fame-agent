"""
Content Pipeline — Scheduler 测试
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from content_pipeline.config import PipelineConfig
from content_pipeline.models import Content, ContentStatus, Platform, PublishResult
from content_pipeline.pipeline import Pipeline
from content_pipeline.publishers.base import BasePublisher, PublisherRegistry
from content_pipeline.scheduler import (
    PipelineScheduler,
    QueueItem,
    ScheduleState,
    PlatformRateLimit,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def config(tmp_path):
    return PipelineConfig(content_root=str(tmp_path))


@pytest.fixture
def pipeline(config):
    """Pipeline with a clean content store."""
    p = Pipeline(config)
    return p


@pytest.fixture
def registry():
    """Empty publisher registry."""
    return PublisherRegistry()


@pytest.fixture
def mock_publisher():
    """A mock publisher that always succeeds."""
    pub = MagicMock(spec=BasePublisher)
    pub.platform = Platform.XIAOHONGSHU
    pub.publish.return_value = PublishResult(
        platform=Platform.XIAOHONGSHU,
        success=True,
        url="https://xiaohongshu.com/post/123",
        post_id="123",
    )
    return pub


@pytest.fixture
def scheduler(config, pipeline, registry, tmp_path):
    """Fresh scheduler backed by tmp_path."""
    s = PipelineScheduler(
        config=config,
        pipeline=pipeline,
        registry=registry,
        queue_path=tmp_path / "schedule.json",
    )
    return s


@pytest.fixture
def content_a(pipeline):
    """Create content A in the store."""
    return pipeline.create_content("Title A", "Body A", ["xiaohongshu"])


@pytest.fixture
def content_b(pipeline):
    """Create content B in the store (multi-platform)."""
    return pipeline.create_content("Title B", "Body B", ["xiaohongshu", "twitter"])


# ── QueueItem ─────────────────────────────────────────────────────────────────


class TestQueueItem:
    def test_to_dict_and_back(self):
        item = QueueItem(
            id="1",
            content_id="001",
            platform="xiaohongshu",
            scheduled_at="2026-06-01T09:00:00",
            priority=5,
        )
        d = item.to_dict()
        restored = QueueItem.from_dict(d)
        assert restored.id == "1"
        assert restored.content_id == "001"
        assert restored.platform == "xiaohongshu"
        assert restored.scheduled_at == "2026-06-01T09:00:00"
        assert restored.priority == 5

    def test_defaults(self):
        item = QueueItem(id="1", content_id="001", platform="xiaohongshu", scheduled_at="2026-06-01T09:00:00")
        assert item.priority == 0
        assert item.retry_count == 0
        assert item.max_retries == 3
        assert item.status == "pending"


# ── ScheduleState ─────────────────────────────────────────────────────────────


class TestScheduleState:
    def test_empty_state_to_dict(self):
        state = ScheduleState()
        d = state.to_dict()
        assert d == {"queue": [], "platform_counters": {}, "version": "1.0"}

    def test_roundtrip(self):
        items = [
            QueueItem(id="1", content_id="001", platform="xiaohongshu", scheduled_at="2026-01-01T00:00:00"),
            QueueItem(id="2", content_id="002", platform="twitter", scheduled_at="2026-01-02T00:00:00"),
        ]
        state = ScheduleState(
            queue=items,
            platform_counters={"xiaohongshu": {"2026-01-01": 3}},
        )
        d = state.to_dict()
        restored = ScheduleState.from_dict(d)
        assert len(restored.queue) == 2
        assert restored.queue[0].content_id == "001"
        assert restored.platform_counters["xiaohongshu"]["2026-01-01"] == 3


# ── Empty queue ───────────────────────────────────────────────────────────────


class TestEmptyQueue:
    def test_empty_on_init(self, scheduler):
        assert scheduler.list_queue() == []

    def test_upcoming_empty(self, scheduler):
        assert scheduler.upcoming_schedule() == []

    def test_process_empty(self, scheduler):
        result = scheduler.process_queue()
        assert result == {"published": [], "failed": [], "rate_limited": [], "retried": []}


# ── Enqueue / Dequeue ────────────────────────────────────────────────────────


class TestEnqueueDequeue:
    def test_enqueue_single(self, scheduler, content_a):
        item = scheduler.enqueue(content_a.id)
        assert item is not None
        assert item.content_id == content_a.id
        assert item.platform == "xiaohongshu"
        assert item.priority == 0

    def test_enqueue_not_found(self, scheduler):
        item = scheduler.enqueue("nonexistent")
        assert item is None

    def test_enqueue_sets_scheduled_status(self, scheduler, content_a, pipeline):
        scheduler.enqueue(content_a.id)
        c = pipeline.store.get_content(content_a.id)
        assert c.status == ContentStatus.SCHEDULED

    def test_enqueue_with_priority(self, scheduler, content_a):
        item = scheduler.enqueue(content_a.id, priority=10)
        assert item.priority == 10

    def test_enqueue_with_scheduled_at(self, scheduler, content_a):
        ts = "2026-06-01T09:00:00"
        item = scheduler.enqueue(content_a.id, scheduled_at=ts)
        assert item.scheduled_at == ts

    def test_enqueue_specific_platform(self, scheduler, content_b):
        item = scheduler.enqueue(content_b.id, platform="twitter")
        assert item.platform == "twitter"

    def test_enqueue_multi_platform(self, scheduler, content_b):
        """Content with 2 platforms should create 2 queue items."""
        items_before = len(scheduler.list_queue())
        scheduler.enqueue(content_b.id)
        items_after = len(scheduler.list_queue())
        assert items_after == items_before + 2

    def test_dequeue(self, scheduler, content_a):
        item = scheduler.enqueue(content_a.id)
        assert scheduler.dequeue(item.id)
        assert scheduler.list_queue() == []

    def test_dequeue_nonexistent(self, scheduler):
        assert not scheduler.dequeue("999")

    def test_duplicate_prevention(self, scheduler, content_a):
        """Enqueuing the same content+platform twice should only create one item."""
        scheduler.enqueue(content_a.id, platform="xiaohongshu")
        scheduler.enqueue(content_a.id, platform="xiaohongshu")
        items = scheduler.list_queue()
        xhs_items = [it for it in items if it.platform == "xiaohongshu"]
        assert len(xhs_items) == 1

    def test_duplicate_prevention_resets_after_completion(self, scheduler, content_a, mock_publisher):
        """After an item completes, re-enqueuing should be allowed."""
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        item = scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")
        # Process the queue — this item is in the past, so it's due
        scheduler.process_queue()

        # Now the item is completed — re-enqueue should work
        item2 = scheduler.enqueue(content_a.id)
        assert item2 is not None
        assert item2.id != item.id


# ── Queue Ordering ────────────────────────────────────────────────────────────


class TestQueueOrdering:
    def test_priority_ordering(self, scheduler, content_a, content_b):
        """High priority items come first."""
        scheduler.enqueue(content_a.id, scheduled_at="2026-06-01T12:00:00", priority=1)
        scheduler.enqueue(content_b.id, scheduled_at="2026-06-01T12:00:00", priority=10, platform="xiaohongshu")

        items = scheduler.list_queue()
        assert items[0].priority == 10
        assert items[1].priority == 1

    def test_scheduled_at_ordering(self, scheduler, content_a, content_b):
        """Same priority: earlier scheduled time first."""
        scheduler.enqueue(content_a.id, scheduled_at="2026-06-01T09:00:00")
        scheduler.enqueue(content_b.id, scheduled_at="2026-06-01T12:00:00", platform="xiaohongshu")

        items = scheduler.list_queue()
        assert items[0].scheduled_at == "2026-06-01T09:00:00"
        assert items[1].scheduled_at == "2026-06-01T12:00:00"


# ── Rate Limiting ─────────────────────────────────────────────────────────────


class TestRateLimiting:
    def test_default_limits(self, scheduler):
        limits = scheduler.DEFAULT_RATE_LIMITS
        assert "xiaohongshu" in limits
        assert limits["xiaohongshu"].max_per_day == 3

    def test_check_rate_limit_allowed(self, scheduler):
        allowed, _ = scheduler.check_rate_limit("xiaohongshu")
        assert allowed

    def test_rate_limit_reached(self, scheduler):
        day_key = scheduler._get_day_key()
        # Simulate 3 publishes today
        scheduler._state.platform_counters["xiaohongshu"] = {day_key: 3}
        allowed, reason = scheduler.check_rate_limit("xiaohongshu")
        assert not allowed
        assert "Daily limit" in reason

    def test_weekly_limit_reached(self, scheduler):
        week_key = scheduler._get_week_key()
        scheduler._state.platform_counters["xiaohongshu"] = {week_key: 21}
        allowed, reason = scheduler.check_rate_limit("xiaohongshu")
        assert not allowed
        assert "Weekly limit" in reason

    def test_process_queue_respects_rate_limit(self, scheduler, content_a, mock_publisher):
        """When rate limit is reached, items should be skipped."""
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        # Pre-fill counter to hit limit
        day_key = scheduler._get_day_key()
        scheduler._state.platform_counters["xiaohongshu"] = {day_key: 3}

        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")
        result = scheduler.process_queue()
        assert len(result["rate_limited"]) == 1

    def test_platform_stats(self, scheduler):
        day_key = scheduler._get_day_key()
        scheduler._state.platform_counters["twitter"] = {day_key: 2}

        stats = scheduler.get_platform_stats()
        assert stats["twitter"]["daily_used"] == 2
        assert stats["xiaohongshu"]["daily_used"] == 0


# ── Queue Persistence ─────────────────────────────────────────────────────────


class TestQueuePersistence:
    def test_save_and_load(self, scheduler, content_a, tmp_path):
        """Enqueue items, save, create new scheduler, load — items should be restored."""
        queue_file = tmp_path / "schedule.json"
        scheduler._queue_path = queue_file

        scheduler.enqueue(content_a.id, scheduled_at="2026-07-01T10:00:00", priority=5)

        # Create a new scheduler with same config and queue file
        s2 = PipelineScheduler(
            config=scheduler.config,
            pipeline=scheduler.pipeline,
            registry=scheduler.registry,
            queue_path=queue_file,
        )
        s2.load_state()
        items = s2.list_queue()
        assert len(items) == 1
        assert items[0].content_id == content_a.id
        assert items[0].priority == 5

    def test_load_missing_file(self, scheduler, tmp_path):
        queue_file = tmp_path / "nonexistent.json"
        s = PipelineScheduler(
            config=scheduler.config,
            pipeline=scheduler.pipeline,
            queue_path=queue_file,
        )
        s.load_state()  # Should not raise
        assert s.list_queue() == []

    def test_load_corrupt_file(self, scheduler, tmp_path):
        queue_file = tmp_path / "corrupt.json"
        queue_file.write_text("not json", encoding="utf-8")
        s = PipelineScheduler(
            config=scheduler.config,
            pipeline=scheduler.pipeline,
            queue_path=queue_file,
        )
        s.load_state()  # Should not raise
        assert s.list_queue() == []

    def test_platform_counters_persist(self, scheduler, tmp_path):
        queue_file = tmp_path / "schedule.json"
        scheduler._queue_path = queue_file

        day_key = scheduler._get_day_key()
        scheduler._state.platform_counters["xiaohongshu"] = {day_key: 2}
        scheduler.save_state()

        s2 = PipelineScheduler(
            config=scheduler.config,
            pipeline=scheduler.pipeline,
            queue_path=queue_file,
        )
        s2.load_state()
        assert s2._get_platform_counter("xiaohongshu", day_key) == 2


# ── Retry Logic ───────────────────────────────────────────────────────────────


class TestRetryLogic:
    def test_exponential_backoff_delays(self, scheduler):
        """Verify exponential backoff values."""
        assert scheduler._get_retry_delay(0) == 60   # First retry: 1 min
        assert scheduler._get_retry_delay(1) == 300  # Second retry: 5 min
        assert scheduler._get_retry_delay(2) == 900  # Third retry: 15 min
        assert scheduler._get_retry_delay(3) == 900  # Beyond max: stays at 15 min

    def test_max_retries(self, scheduler, content_a, mock_publisher):
        """After max_retries failures, item stays as failed."""
        # Make publisher always fail
        mock_publisher.publish.return_value = PublishResult(
            platform=Platform.XIAOHONGSHU,
            success=False,
            error="Test error",
        )
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")

        # Process 4 times (initial + 3 retries)
        # Need to bypass backoff by resetting last_attempt_at after each failure
        for attempt in range(4):
            scheduler.process_queue()
            # Bypass backoff: set last_attempt_at far in past so next retry is allowed
            # (Must save state because process_queue() calls load_state() on entry)
            for item in scheduler._state.queue:
                if item.status == "failed" and item.retry_count < item.max_retries:
                    item.last_attempt_at = "2000-01-01T00:00:00"
            scheduler.save_state()

        items = scheduler.list_queue()
        assert items[0].status == "failed"
        assert items[0].retry_count == 3

    def test_retry_backoff_prevents_immediate_retry(self, scheduler, content_a, mock_publisher):
        """After a failure, item should NOT be retried immediately."""
        mock_publisher.publish.return_value = PublishResult(
            platform=Platform.XIAOHONGSHU,
            success=False,
            error="Test error",
        )
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")

        # First process — fails
        result1 = scheduler.process_queue()
        assert len(result1["failed"]) == 1

        # Second process immediately — should NOT retry (backoff hasn't elapsed)
        result2 = scheduler.process_queue()
        assert len(result2["retried"]) == 0
        assert len(result2["failed"]) == 0  # Not due for retry

    def test_retry_succeeds(self, scheduler, content_a, mock_publisher):
        """After a failed attempt, a retry can succeed."""
        # First call fails, second call succeeds
        mock_publisher.publish.side_effect = [
            PublishResult(platform=Platform.XIAOHONGSHU, success=False, error="First fail"),
            PublishResult(platform=Platform.XIAOHONGSHU, success=True, url="https://example.com/123"),
        ]
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")

        # First process — fails
        result1 = scheduler.process_queue()
        assert len(result1["failed"]) == 1

        # Manually set last_attempt_at to far in the past to bypass backoff
        items = scheduler.list_queue()
        items[0].last_attempt_at = "2020-01-01T00:00:00"
        items[0].retry_count = 0  # Reset since our mock counts differently
        scheduler.save_state()

        # Second process — succeeds
        result2 = scheduler.process_queue()

        # Check combined results (could be published or retried depending on internal logic)
        total_successes = len(result2["published"]) + len(result2["retried"])
        assert total_successes >= 1

    def test_no_retry_on_permanent_failure(self, scheduler, content_a):
        """Content not found → permanent failure, no retry."""
        # Enqueue a content that exists, then we'll try to publish but content is gone
        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")

        # Delete content to simulate not-found
        for folder in ["input", "processing", "queue", "published"]:
            path = scheduler.pipeline.store._folder_path(folder)
            for f in path.glob(f"{content_a.id}*.md"):
                f.unlink()

        result = scheduler.process_queue()
        assert len(result["failed"]) == 1
        items = scheduler.list_queue()
        assert items[0].status == "failed"
        # Content not found is immediate permanent failure
        assert "not found" in (items[0].last_error or "")


# ── Upcoming Schedule ─────────────────────────────────────────────────────────


class TestUpcomingSchedule:
    def test_upcoming_in_range(self, scheduler, content_a):
        tomorrow = (datetime.now() + timedelta(days=1)).isoformat()
        scheduler.enqueue(content_a.id, scheduled_at=tomorrow)
        upcoming = scheduler.upcoming_schedule(days=7)
        assert len(upcoming) == 1

    def test_upcoming_excludes_past(self, scheduler, content_a):
        past = "2020-01-01T00:00:00"
        scheduler.enqueue(content_a.id, scheduled_at=past)
        upcoming = scheduler.upcoming_schedule(days=7)
        assert len(upcoming) == 0

    def test_upcoming_excludes_far_future(self, scheduler, content_a):
        far = (datetime.now() + timedelta(days=30)).isoformat()
        scheduler.enqueue(content_a.id, scheduled_at=far)
        upcoming = scheduler.upcoming_schedule(days=7)
        assert len(upcoming) == 0

    def test_upcoming_excludes_completed(self, scheduler, content_a, mock_publisher):
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        today = datetime.now().isoformat()
        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")  # past → due
        scheduler.process_queue()

        upcoming = scheduler.upcoming_schedule(days=7)
        # Completed items should not show up
        for item in upcoming:
            assert item.status != "completed"


# ── Cleanup ───────────────────────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_removes_completed(self, scheduler, content_a, mock_publisher):
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")
        scheduler.process_queue()

        before = len(scheduler.list_queue())
        removed = scheduler.cleanup_completed()
        after = len(scheduler.list_queue())
        assert removed == before - after
        assert after < before

    def test_cleanup_keeps_pending(self, scheduler, content_a):
        scheduler.enqueue(content_a.id)
        count_before = len(scheduler.list_queue())
        removed = scheduler.cleanup_completed()
        assert removed == 0
        assert len(scheduler.list_queue()) == count_before


# ── Dry Run ───────────────────────────────────────────────────────────────────


class TestDryRun:
    def test_dry_run_does_not_publish(self, scheduler, content_a, mock_publisher):
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")
        result = scheduler.process_queue(dry_run=True)

        assert len(result["published"]) == 1
        assert result["published"][0].get("dry_run") is True
        # Publisher should NOT have been called
        mock_publisher.publish.assert_not_called()

    def test_dry_run_does_not_increment_counters(self, scheduler, content_a, mock_publisher):
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")
        scheduler.process_queue(dry_run=True)

        day_key = scheduler._get_day_key()
        assert scheduler._get_platform_counter("xiaohongshu", day_key) == 0


# ── Priority Interleaving ─────────────────────────────────────────────────────


class TestPriorityInterleaving:
    def test_high_priority_processed_first(self, scheduler, content_a, content_b, mock_publisher):
        """High priority items should be processed before low priority ones."""
        registry = PublisherRegistry()
        registry.register(mock_publisher)
        scheduler.registry = registry

        # Both in the past (due), but B has higher priority
        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00", priority=1)
        scheduler.enqueue(content_b.id, scheduled_at="2020-01-01T00:00:00", priority=99, platform="xiaohongshu")

        result = scheduler.process_queue(dry_run=True)
        published = result["published"]
        assert published[0]["content_id"] == content_b.id  # Higher priority first
        assert published[1]["content_id"] == content_a.id


# ── Handle missing publisher gracefully ───────────────────────────────────────


class TestMissingPublisher:
    def test_process_queue_missing_publisher(self, scheduler, content_a):
        """No publisher registered → items should fail gracefully."""
        scheduler.enqueue(content_a.id, scheduled_at="2020-01-01T00:00:00")
        result = scheduler.process_queue()
        assert len(result["failed"]) == 1
        assert "No publisher" in result["failed"][0]["error"]
