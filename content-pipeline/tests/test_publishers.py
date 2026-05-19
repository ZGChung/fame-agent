"""
Content Pipeline — 发布器测试
"""

from unittest.mock import MagicMock, patch

from content_pipeline.models import Content, Platform, PublishResult
from content_pipeline.publishers.base import PublisherRegistry
from content_pipeline.publishers.xiaohongshu import XiaohongshuPublisher
from content_pipeline.publishers.twitter import TwitterPublisher


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


class TestTwitterPublisher:
    def test_not_configured_by_default(self):
        pub = TwitterPublisher()
        assert not pub.is_configured()

    def test_configured_with_token(self):
        pub = TwitterPublisher(bearer_token="test-token")
        assert pub.is_configured()

    def test_split_into_tweets_short_text(self):
        pub = TwitterPublisher(bearer_token="test")
        text = "Hello, this is a short tweet!"
        result = pub._split_into_tweets(text)
        assert len(result) == 1
        assert result[0] == text

    def test_split_into_tweets_long_text(self):
        pub = TwitterPublisher(bearer_token="test")
        # Create text longer than 280 chars
        text = "This is paragraph one.\n\n" + "A" * 200 + "\n\n" + "This is paragraph three."
        result = pub._split_into_tweets(text, max_chars=100)
        assert len(result) > 1
        # Verify no tweet exceeds max_chars
        for tweet in result:
            assert len(tweet) <= 100, f"Tweet too long: {len(tweet)} chars"

    def test_split_long_paragraph(self):
        pub = TwitterPublisher(bearer_token="test")
        # Create a paragraph longer than max_chars without sentence breaks
        para = "HelloWorld" + "B" * 300
        result = pub._split_long_paragraph(para, max_chars=50)
        assert len(result) > 1
        for segment in result:
            assert len(segment) <= 50

    def test_split_long_paragraph_with_sentences(self):
        pub = TwitterPublisher(bearer_token="test")
        para = "First sentence. Second sentence. Third sentence that is longer."
        result = pub._split_long_paragraph(para, max_chars=50)
        assert len(result) >= 2

    def test_split_empty_text(self):
        pub = TwitterPublisher(bearer_token="test")
        result = pub._split_into_tweets("")
        assert result == []

    def test_split_single_paragraph_no_breaks(self):
        pub = TwitterPublisher(bearer_token="test")
        # Text that is short enough to not need splitting
        text = "A" * 200
        result = pub._split_into_tweets(text, max_chars=280)
        assert len(result) == 1
        assert len(result[0]) == 200

    def test_publish_single_tweet(self):
        pub = TwitterPublisher(bearer_token="test-token")

        # Mock httpx.Client
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "data": {"id": "1234567890"}
        }

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            content = Content(id="001", title="Test", body="Short tweet body")
            result = pub.publish(content)

            assert result.success is True
            assert result.post_id == "1234567890"
            assert "twitter.com" in result.url
            # Verify the API was called
            mock_client.post.assert_called_once()

    def test_publish_thread(self):
        pub = TwitterPublisher(bearer_token="test-token")

        mock_responses = []
        for i in range(3):
            mr = MagicMock()
            mr.status_code = 201
            mr.json.return_value = {"data": {"id": f"tweet_{i}"}}
            mock_responses.append(mr)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = mock_responses

            # Create content long enough to trigger threading
            content = Content(
                id="002",
                title="Long Test",
                body="Short intro paragraph.\n\n" + "B" * 250 + "\n\nAnother paragraph.\n\n" + "C" * 250 + "\n\nFinal paragraph here.",
            )
            result = pub.publish(content)

            assert result.success is True
            # Should have at least 2 tweets (the long B block + C block each exceed 280 combined with title)
            assert mock_client.post.call_count >= 2

    def test_publish_api_error(self):
        pub = TwitterPublisher(bearer_token="bad-token")

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            content = Content(id="003", title="Fail", body="This will fail")
            result = pub.publish(content)

            assert result.success is False
            assert "Twitter API error" in result.error

    def test_publish_uses_platform_variant(self):
        pub = TwitterPublisher(bearer_token="test-token")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "data": {"id": "1234567890"}
        }

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            content = Content(
                id="004",
                title="Test",
                body="Default body content",
                platform_variants={"twitter": "Custom Twitter variant content"},
            )
            result = pub.publish(content)

            assert result.success is True
            # Check that the posted text includes the variant, not the default body
            call_kwargs = mock_client.post.call_args[1]
            posted_text = call_kwargs["json"]["text"]
            assert "Custom Twitter variant" in posted_text
