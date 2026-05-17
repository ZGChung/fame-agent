"""
Content Pipeline — Twitter 发布器

使用 Twitter API v2 发布推文，自动处理 280 字符限制和长文线程。
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
TWITTER_CHAR_LIMIT = 280


def _split_into_tweets(text: str, limit: int = TWITTER_CHAR_LIMIT) -> list[str]:
    """将长文本拆分为多条推文（线程），尽量在句子边界处断句。"""
    if len(text) <= limit:
        return [text]

    tweets = []
    words = text.split()
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                tweets.append(current)
            current = word
    if current:
        tweets.append(current)
    return tweets


class TwitterPublisher(BasePublisher):
    """
    Twitter 发布器。

    通过 Twitter API v2 发布推文。
    需要 TWITTER_BEARER_TOKEN 环境变量，可选 TWITTER_API_KEY / TWITTER_API_SECRET。
    自动处理 280 字符限制，超长内容拆分为线程。
    """

    platform = Platform.TWITTER

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_base: str = TWITTER_API_BASE,
    ):
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN", "")
        self.api_key = api_key or os.getenv("TWITTER_API_KEY", "")
        self.api_secret = api_secret or os.getenv("TWITTER_API_SECRET", "")
        self.api_base = api_base

    def is_configured(self) -> bool:
        return bool(self.bearer_token)

    def publish(self, content: Content) -> PublishResult:
        """发布内容到 Twitter（自动处理线程）"""
        try:
            platform_text = content.platform_variants.get(
                Platform.TWITTER.value, content.body
            )

            # 拼接标题 + 正文 + tags
            full_text = content.title
            if platform_text:
                full_text += f"\n\n{platform_text}"
            if content.tags:
                hashtags = " ".join(f"#{t.replace(' ', '')}" for t in content.tags)
                full_text += f"\n\n{hashtags}"

            full_text = full_text.strip()

            # 拆分线程
            tweet_thread = _split_into_tweets(full_text, TWITTER_CHAR_LIMIT)

            if not tweet_thread or not tweet_thread[0].strip():
                return PublishResult(
                    platform=self.platform,
                    success=False,
                    error="Empty tweet content",
                )

            # 发布第一条
            post_id = self._post_tweet(tweet_thread[0], reply_to=None)

            # 发布后续（线程）
            for tweet_body in tweet_thread[1:]:
                reply_id = self._post_tweet(tweet_body, reply_to=post_id)
                if reply_id:
                    post_id = reply_id  # 后续回复链到自己

            if post_id:
                logger.info("Twitter thread published: %d tweets", len(tweet_thread))
                return PublishResult(
                    platform=self.platform,
                    success=True,
                    post_id=post_id,
                )
            else:
                return PublishResult(
                    platform=self.platform,
                    success=False,
                    error="Failed to create first tweet",
                )
        except Exception as e:
            logger.exception("Twitter publish failed")
            return PublishResult(
                platform=self.platform,
                success=False,
                error=str(e),
            )

    def _post_tweet(self, text: str, reply_to: Optional[str] = None) -> Optional[str]:
        """发布单条推文，返回 tweet ID 或 None"""
        payload: dict = {"text": text}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}

        response = httpx.post(
            f"{self.api_base}/tweets",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )

        if response.status_code in (200, 201):
            data = response.json()
            tweet_id = data.get("data", {}).get("id", "")
            return tweet_id
        else:
            logger.warning(
                "Twitter HTTP %d: %s", response.status_code, response.text[:200]
            )
            return None
