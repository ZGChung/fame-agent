"""
Content Pipeline — LinkedIn发布器测试
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from content_pipeline.models import Content, Platform, PublishResult
from content_pipeline.publishers.linkedin import LinkedInPublisher


class TestLinkedInPublisher:
    def test_platform(self):
        pub = LinkedInPublisher()
        assert pub.platform == Platform.LINKEDIN

    def test_is_configured_with_token_and_urn(self):
        pub = LinkedInPublisher(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
        )
        assert pub.is_configured() is True

    def test_not_configured_missing_token(self):
        pub = LinkedInPublisher(
            access_token="",
            person_urn="urn:li:person:abc123",
        )
        assert pub.is_configured() is False

    def test_not_configured_missing_urn(self):
        pub = LinkedInPublisher(
            access_token="test-token",
            person_urn="",
        )
        assert pub.is_configured() is False

    def test_not_configured_default(self):
        pub = LinkedInPublisher()
        assert pub.is_configured() is False

    def test_publish_success(self):
        pub = LinkedInPublisher(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.headers = {"X-RestLi-Id": "urn:li:share:789"}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(
                id="001",
                title="Professional Update",
                body="Here is my latest article on AI.",
                tags=["ai", "machinelearning"],
            )
            result = pub.publish(content)

            assert result.success is True
            assert result.platform == Platform.LINKEDIN
            assert result.post_id == "urn:li:share:789"
            mock_post.assert_called_once()

            # Verify payload structure
            call_args = mock_post.call_args
            payload = call_args.kwargs["json"]
            assert payload["author"] == "urn:li:person:abc123"
            share_text = payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"]
            assert "Professional Update" in share_text
            assert "#ai" in share_text
            assert "#machinelearning" in share_text

    def test_publish_success_status_200(self):
        """LinkedIn may return 200 as well"""
        pub = LinkedInPublisher(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"X-RestLi-Id": "urn:li:share:456"}

        with patch("httpx.post", return_value=mock_response):
            content = Content(id="002", title="Update", body="Body text")
            result = pub.publish(content)

            assert result.success is True
            assert result.post_id == "urn:li:share:456"

    def test_publish_http_error(self):
        pub = LinkedInPublisher(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.text = "Forbidden: insufficient permissions"

        with patch("httpx.post", return_value=mock_response):
            content = Content(id="003", title="Forbidden", body="x")
            result = pub.publish(content)

            assert result.success is False
            assert "403" in result.error

    def test_publish_network_error(self):
        pub = LinkedInPublisher(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
        )

        with patch("httpx.post", side_effect=httpx.ConnectError("Connection refused")):
            content = Content(id="004", title="Network", body="x")
            result = pub.publish(content)

            assert result.success is False
            assert "Connection refused" in result.error

    def test_publish_uses_platform_variant(self):
        pub = LinkedInPublisher(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.headers = {"X-RestLi-Id": "urn:li:share:111"}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(
                id="005",
                title="Variant Test",
                body="Default body",
                platform_variants={"linkedin": "LinkedIn-specific professional text"},
            )
            pub.publish(content)

            payload = mock_post.call_args.kwargs["json"]
            share_text = payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"]
            assert "LinkedIn-specific professional text" in share_text
            assert "Default body" not in share_text

    def test_publish_no_tags(self):
        pub = LinkedInPublisher(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.headers = {"X-RestLi-Id": "urn:li:share:222"}

        with patch("httpx.post", return_value=mock_response) as mock_post:
            content = Content(id="006", title="No Tags", body="Just text", tags=[])
            result = pub.publish(content)

            assert result.success is True
            payload = mock_post.call_args.kwargs["json"]
            share_text = payload["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"]
            assert "#" not in share_text.split("\n\n")[-1]  # No hashtag line appended
