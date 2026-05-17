"""
Content Pipeline — Twitter发布器测试
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from content_pipeline.models import Content, Platform, PublishResult
from content_pipeline.publishers.twitter import TwitterPublisher, _split_into_tweets


class TestSplitIntoTweets:
    """测试推文线程拆分逻辑"""

    def test_short_text_returns_single_tweet(self):
        result = _split_into_tweets("Hello world", limit=280)
        assert result == ["Hello world"]

    def test_exact_limit(self):
        text = "A" * 280
        result = _split_into_tweets(text, limit=280)
        assert len(result) == 1
        assert result[0] == text

    def test_long_text_splits(self):
        text = "word " * 100  # ~500 chars, 100 words
        result = _split_into_tweets(text, limit=280)
        assert len(result) > 1
        for tweet in result:
            assert len(tweet) <= 280

    def test_single_word_exceeds_limit(self):
        long_word = "A" * 300
        result = _split_into_tweets(long_word, limit=280)
        # Each word goes on its own line if it exceeds limit
        assert len(result) == 1
        assert len(result[0]) == 300

    def test_empty_string(self):
        result = _split_into_tweets("", limit=280)
        assert result == [""]


class TestTwitterPublisher:
    def test_platform(self):
        pub = TwitterPublisher()
        assert pub.platform == Platform.TWITTER

    def test_is_configured_with_token(self):
        pub = TwitterPublisher(bearer_token="test-bearer-token")
        assert pub.is_configured() is True

    def test_not_configured_without_token(self):
        pub = TwitterPublisher(bearer_token="")
        assert pub.is_configured() is False

    def test_not_configured_default(self):
        pub = TwitterPublisher()
        assert pub.is_configured() is False

    def test_is_configured_ignores_optional_keys(self):
        """api_key/secret are optional — bearer token alone is enough"""
        pub = TwitterPublisher(
            bearer_token="test-bearer",
            api_key="",
            api_secret="",
        )
        assert pub.is_configured() is True

    def test_publish_single_tweet_success(self):
        pub = TwitterPublisher(bearer_token="test-bearer")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "data": {"id": "1234567890"},
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(
                id="001",
                title="Short tweet",
                body="This is a short tweet.",
            )
            result = pub.publish(content)

            assert result.success is True
            assert result.platform == Platform.TWITTER
            assert result.post_id == "1234567890"
            mock_post.assert_called_once()

    def test_publish_success_status_200(self):
        pub = TwitterPublisher(bearer_token="test-bearer")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"id": "9876543210"},
        }

        with patch("httpx.post", return_value=mock_response):
            content = Content(id="002", title="OK", body="Body")
            result = pub.publish(content)

            assert result.success is True
            assert result.post_id == "9876543210"

    def test_publish_thread_for_long_content(self):
        pub = TwitterPublisher(bearer_token="test-bearer")

        # Mock httpx.post to always return success (can be called any number of times)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"id": "tweet-thread-final"}}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(
                id="003",
                title="Long Thread",
                body="word " * 200,  # Long body that requires threading
                tags=["ai"],
            )
            result = pub.publish(content)

            assert result.success is True
            # Last tweet ID is returned
            assert result.post_id == "tweet-thread-final"
            # Multiple tweets were posted
            assert mock_post.call_count > 1

    def test_publish_with_tags(self):
        pub = TwitterPublisher(bearer_token="test-bearer")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"id": "111"}}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(
                id="004",
                title="Tagged",
                body="Body",
                tags=["ai", "machine learning"],
            )
            pub.publish(content)

            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert "#ai" in payload["text"]
            assert "#machinelearning" in payload["text"]

    def test_publish_reply_chaining(self):
        """Second tweet in thread should reply to first"""
        pub = TwitterPublisher(bearer_token="test-bearer")

        mock1 = MagicMock(spec=httpx.Response)
        mock1.status_code = 201
        mock1.json.return_value = {"data": {"id": "first-tweet"}}

        mock2 = MagicMock(spec=httpx.Response)
        mock2.status_code = 201
        mock2.json.return_value = {"data": {"id": "second-tweet"}}

        with patch("httpx.post", side_effect=[mock1, mock2]) as mock_post:
            content = Content(
                id="005",
                title="Thread",
                body="word " * 200,
            )
            pub.publish(content)

            # First call: no reply
            first_call = mock_post.call_args_list[0]
            assert "reply" not in first_call.kwargs["json"]

            # Second call: reply to first-tweet
            second_call = mock_post.call_args_list[1]
            assert second_call.kwargs["json"]["reply"]["in_reply_to_tweet_id"] == "first-tweet"

    def test_publish_first_tweet_fails(self):
        pub = TwitterPublisher(bearer_token="test-bearer")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        with patch("httpx.post", return_value=mock_response):
            content = Content(id="006", title="Fail", body="Body")
            result = pub.publish(content)

            assert result.success is False
            assert "Failed to create first tweet" in result.error

    def test_publish_network_error(self):
        pub = TwitterPublisher(bearer_token="test-bearer")

        with patch("httpx.post", side_effect=httpx.ConnectError("Timeout")):
            content = Content(id="007", title="Network", body="x")
            result = pub.publish(content)

            assert result.success is False
            assert "Timeout" in result.error

    def test_publish_empty_content(self):
        pub = TwitterPublisher(bearer_token="test-bearer")

        content = Content(id="008", title="", body="")
        result = pub.publish(content)

        assert result.success is False
        assert "Empty tweet content" in result.error

    def test_publish_uses_platform_variant(self):
        pub = TwitterPublisher(bearer_token="test-bearer")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {"data": {"id": "999"}}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(
                id="009",
                title="Variant",
                body="Default body",
                platform_variants={"twitter": "Twitter-specific text"},
            )
            pub.publish(content)

            payload = mock_post.call_args.kwargs["json"]
            assert "Twitter-specific text" in payload["text"]
            assert "Default body" not in payload["text"]

    def test_constructor_accepts_optional_keys(self):
        pub = TwitterPublisher(
            bearer_token="bt",
            api_key="ak",
            api_secret="as",
        )
        assert pub.api_key == "ak"
        assert pub.api_secret == "as"
        assert pub.bearer_token == "bt"
        assert pub.is_configured() is True
