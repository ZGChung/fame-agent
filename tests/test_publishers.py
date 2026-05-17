"""
Content Pipeline — 发布器测试
"""

from unittest.mock import AsyncMock, MagicMock, patch

from content_pipeline.models import Content, Platform, PublishResult
from content_pipeline.publishers.base import PublisherRegistry
from content_pipeline.publishers.xiaohongshu import XiaohongshuPublisher


class MockPublisher:
    """模拟发布器（测试用）"""
    def __init__(self, platform: Platform, configured: bool = True):
        self.platform = platform
        self._configured = configured

    def is_configured(self):
        return self._configured

    def publish(self, content: Content) -> PublishResult:
        return PublishResult(
            platform=self.platform,
            success=True,
            url=f"https://{self.platform.value}/post/{content.id}",
        )


class TestPublisherRegistry:
    def test_register_and_get(self):
        r = PublisherRegistry()
        pub = MockPublisher(Platform.XIAOHONGSHU)
        r.register(pub)
        assert r.get("xiaohongshu") is pub

    def test_get_nonexistent(self):
        r = PublisherRegistry()
        assert r.get("unknown") is None

    def test_configured_list(self):
        r = PublisherRegistry()
        r.register(MockPublisher(Platform.XIAOHONGSHU, configured=True))
        r.register(MockPublisher(Platform.TWITTER, configured=False))
        assert r.configured() == ["xiaohongshu"]

    def test_all_publishers(self):
        r = PublisherRegistry()
        xhs = MockPublisher(Platform.XIAOHONGSHU)
        tw = MockPublisher(Platform.TWITTER)
        r.register(xhs)
        r.register(tw)
        assert len(r.all()) == 2


class TestXiaohongshuPublisher:
    def test_not_configured_by_default(self):
        pub = XiaohongshuPublisher(cookie_path="/nonexistent/cookies.json")
        assert not pub.is_configured()

    @patch("content_pipeline.publishers.xiaohongshu.XiaohongshuPublisher._async_publish")
    def test_publish_dispatches_to_async(self, mock_async):
        mock_async.return_value = PublishResult(
            platform=Platform.XIAOHONGSHU,
            success=True,
            url="https://xhslink.com/abc",
        )
        pub = XiaohongshuPublisher(cookie_path="/tmp/test_cookies.json")

        # Mock cookie file exists
        import json
        from pathlib import Path
        Path("/tmp/test_cookies.json").write_text(
            json.dumps([{"name": "test", "value": "cookie"}])
        )

        content = Content(id="001", title="Test", body="Body")
        result = pub.publish(content)
        assert result.success is True
        assert "xhslink" in result.url

        # Cleanup
        Path("/tmp/test_cookies.json").unlink()
