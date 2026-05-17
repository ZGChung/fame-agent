"""
Content Pipeline — Bilibili发布器测试
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from content_pipeline.models import Content, Platform, PublishResult
from content_pipeline.publishers.bilibili import BilibiliPublisher


class TestBilibiliPublisher:
    def test_platform(self):
        pub = BilibiliPublisher()
        assert pub.platform == Platform.BILIBILI

    def test_is_configured_with_token(self):
        pub = BilibiliPublisher(access_token="test-token-123")
        assert pub.is_configured() is True

    def test_not_configured_without_token(self):
        pub = BilibiliPublisher(access_token="")
        assert pub.is_configured() is False

    def test_not_configured_default(self):
        pub = BilibiliPublisher()
        assert pub.is_configured() is False

    def test_publish_success(self):
        pub = BilibiliPublisher(access_token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 0,
            "data": {"aid": 123456},
        }

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(
                id="001",
                title="Test Video",
                body="Test description",
                tags=["ai", "tech"],
            )
            result = pub.publish(content)

            assert result.success is True
            assert result.platform == Platform.BILIBILI
            assert result.post_id == "123456"
            mock_post.assert_called_once()

            # Verify payload
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["title"] == "Test Video"
            assert "ai" in payload["tag"]

    def test_publish_api_error(self):
        pub = BilibiliPublisher(access_token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": -101,
            "message": "Account not logged in",
        }

        with patch("httpx.post", return_value=mock_response):
            content = Content(id="002", title="Fail", body="x")
            result = pub.publish(content)

            assert result.success is False
            assert "Account not logged in" in result.error

    def test_publish_http_error(self):
        pub = BilibiliPublisher(access_token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("httpx.post", return_value=mock_response):
            content = Content(id="003", title="Auth Fail", body="x")
            result = pub.publish(content)

            assert result.success is False
            assert "401" in result.error

    def test_publish_network_error(self):
        pub = BilibiliPublisher(access_token="test-token")

        with patch("httpx.post", side_effect=httpx.ConnectError("Timeout")):
            content = Content(id="004", title="Network", body="x")
            result = pub.publish(content)

            assert result.success is False
            assert "Timeout" in result.error

    def test_publish_uses_platform_variant(self):
        pub = BilibiliPublisher(access_token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": {"aid": 999}}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(
                id="005",
                title="Variant Test",
                body="Default body",
                platform_variants={"bilibili": "B站专属文案"},
            )
            pub.publish(content)

            payload = mock_post.call_args.kwargs["json"]
            assert payload["desc"] == "B站专属文案"

    def test_publish_title_truncation(self):
        pub = BilibiliPublisher(access_token="test-token")

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": {"aid": 1}}

        long_title = "A" * 200

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(id="006", title=long_title, body="body")
            pub.publish(content)

            payload = mock_post.call_args.kwargs["json"]
            assert len(payload["title"]) == 80
