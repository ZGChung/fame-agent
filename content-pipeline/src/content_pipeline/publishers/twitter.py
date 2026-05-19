"""
Content Pipeline — Twitter/X 发布器

使用 Twitter API v2 (OAuth 2.0 Bearer Token) 发布推文。
支持自动拆分为推文串（thread）当内容超过 280 字限制。

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

TWITTER_API_BASE = "https://api.twitter.com/2"
DEFAULT_MAX_CHARS = 280


class TwitterPublisher(BasePublisher):
    """
    Twitter/X 发布器。

    使用 Twitter API v2，需要设置 TWITTER_BEARER_TOKEN 环境变量。
    内容超过 280 字符时自动拆分为推文串（reply chain）。
    """

    platform = Platform.TWITTER

    def __init__(self, bearer_token: Optional[str] = None):
        self.bearer_token = bearer_token or os.environ.get("TWITTER_BEARER_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.bearer_token)

    def publish(self, content: Content) -> PublishResult:
        """发布内容到 Twitter"""
        platform_text = content.platform_variants.get(
            Platform.TWITTER.value, content.body
        )

        # 使用标题 + 正文作为推文内容
        full_text = f"{content.title}\n\n{platform_text}".strip()

        try:
            tweet_ids = self._publish_thread(full_text)
            if tweet_ids:
                first_id = tweet_ids[0]
                return PublishResult(
                    platform=self.platform,
                    success=True,
                    url=f"https://twitter.com/user/status/{first_id}",
                    post_id=first_id,
                )
            return PublishResult(
                platform=self.platform,
                success=False,
                error="Tweet publish returned no ID",
            )
        except Exception as e:
            logger.exception("Twitter publish failed")
            return PublishResult(
                platform=self.platform,
                success=False,
                error=str(e),
            )

    def _split_into_tweets(self, text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
        """
        将长文本拆分为推文串。
        
        按段落拆分，确保每条不超过 max_chars。
        如果单段超过限制，按句子或字符拆分。
        """
        if not text or not text.strip():
            return []

        if len(text) <= max_chars:
            return [text]

        paragraphs = text.split("\n\n")
        tweets: list[str] = []
        current = ""

        for para in paragraphs:
            # 如果加上新段落会超限，先保存当前内容
            candidate = (current + "\n\n" + para).strip() if current else para
            if len(candidate) > max_chars:
                if current:
                    tweets.append(current.strip())
                # 处理超长段落
                if len(para) <= max_chars:
                    current = para
                else:
                    # 按句子或子串拆分
                    for segment in self._split_long_paragraph(para, max_chars):
                        if segment:
                            tweets.append(segment)
                    current = ""
            else:
                current = candidate

        if current:
            tweets.append(current.strip())

        return tweets

    def _split_long_paragraph(self, paragraph: str, max_chars: int) -> list[str]:
        """拆分超长段落为子串列表"""
        # 先尝试按句子拆分
        import re
        sentences = re.split(r'(?<=[。！？.!?])\s*', paragraph)
        segments: list[str] = []
        current = ""

        for sentence in sentences:
            if not sentence.strip():
                continue
            candidate = (current + sentence).strip() if current else sentence
            if len(candidate) > max_chars:
                if current:
                    segments.append(current.strip())
                # 按字符拆分
                for i in range(0, len(sentence), max_chars):
                    segments.append(sentence[i:i + max_chars].strip())
                current = ""
            else:
                current = candidate

        if current:
            segments.append(current.strip())

        return segments

    def _publish_thread(self, full_text: str) -> list[str]:
        """
        发布推文串。
        
        返回所有推文的 ID 列表。如果是单条推文，返回 [id]。
        """
        tweets = self._split_into_tweets(full_text)
        if not tweets:
            return []

        tweet_ids: list[str] = []
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=30) as client:
            for i, tweet_text in enumerate(tweets):
                payload: dict = {"text": tweet_text}

                # 如果不是首条，作为对前一条的回复
                if i > 0 and tweet_ids:
                    payload["reply"] = {
                        "in_reply_to_tweet_id": tweet_ids[-1]
                    }

                response = client.post(
                    f"{TWITTER_API_BASE}/tweets",
                    headers=headers,
                    json=payload,
                )

                if response.status_code not in (200, 201):
                    raise RuntimeError(
                        f"Twitter API error (status {response.status_code}): "
                        f"{response.text}"
                    )

                data = response.json()
                tweet_id = data.get("data", {}).get("id")
                if tweet_id:
                    tweet_ids.append(tweet_id)
                    logger.info(
                        "Tweet %d/%d posted: id=%s, len=%d",
                        i + 1, len(tweets), tweet_id, len(tweet_text),
                    )

        return tweet_ids
