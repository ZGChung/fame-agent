"""
Content Pipeline — LinkedIn 发布器

使用 LinkedIn API v2 发布专业文章/帖子。
完全独立，不依赖其他平台模块。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .base import BasePublisher
from ..models import Content, Platform, PublishResult

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"


class LinkedInPublisher(BasePublisher):
    """
    LinkedIn 发布器。

    通过 LinkedIn API v2 发布文章/帖子。
    需要 LINKEDIN_ACCESS_TOKEN 和 LINKEDIN_PERSON_URN 环境变量。
    """

    platform = Platform.LINKEDIN

    def __init__(
        self,
        access_token: Optional[str] = None,
        person_urn: Optional[str] = None,
        api_base: str = LINKEDIN_API_BASE,
    ):
        self.access_token = access_token or os.getenv("LINKEDIN_ACCESS_TOKEN", "")
        self.person_urn = person_urn or os.getenv("LINKEDIN_PERSON_URN", "")
        self.api_base = api_base

    def is_configured(self) -> bool:
        return bool(self.access_token) and bool(self.person_urn)

    def publish(self, content: Content) -> PublishResult:
        """发布内容到 LinkedIn"""
        try:
            platform_text = content.platform_variants.get(
                Platform.LINKEDIN.value, content.body
            )

            # LinkedIn 分享帖格式
            payload = {
                "author": self.person_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": f"{content.title}\n\n{platform_text[:3000]}",
                        },
                        "shareMediaCategory": "NONE",
                    },
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
                },
            }

            # 如果有 tags，作为 hashtags 追加
            if content.tags:
                hashtags = " ".join(f"#{t.replace(' ', '')}" for t in content.tags)
                payload["specificContent"]["com.linkedin.ugc.ShareContent"][
                    "shareCommentary"
                ]["text"] += f"\n\n{hashtags}"

            response = httpx.post(
                f"{self.api_base}/ugcPosts",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                json=payload,
                timeout=30.0,
            )

            if response.status_code in (200, 201):
                post_id = response.headers.get("X-RestLi-Id", "")
                logger.info("LinkedIn publish success: %s", post_id)
                return PublishResult(
                    platform=self.platform,
                    success=True,
                    post_id=post_id,
                )
            else:
                logger.warning(
                    "LinkedIn HTTP %d: %s", response.status_code, response.text[:200]
                )
                return PublishResult(
                    platform=self.platform,
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )
        except Exception as e:
            logger.exception("LinkedIn publish failed")
            return PublishResult(
                platform=self.platform,
                success=False,
                error=str(e),
            )
