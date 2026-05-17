"""
Content Pipeline — Bilibili发布器

使用 B站开放平台 API 发布视频/动态。
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

BILIBILI_API_BASE = "https://api.bilibili.com"


class BilibiliPublisher(BasePublisher):
    """
    B站发布器。

    通过 B站开放平台 API 发布内容（视频稿件 / 动态）。
    需要 BILIBILI_ACCESS_TOKEN 环境变量。
    """

    platform = Platform.BILIBILI

    def __init__(
        self,
        access_token: Optional[str] = None,
        api_base: str = BILIBILI_API_BASE,
    ):
        self.access_token = access_token or os.getenv("BILIBILI_ACCESS_TOKEN", "")
        self.api_base = api_base

    def is_configured(self) -> bool:
        return bool(self.access_token)

    def publish(self, content: Content) -> PublishResult:
        """发布内容到 B站"""
        try:
            platform_text = content.platform_variants.get(
                Platform.BILIBILI.value, content.body
            )

            # 格式化 tags
            tags_str = ",".join(content.tags) if content.tags else ""

            payload = {
                "title": content.title[:80],  # B站标题限制 80 字
                "desc": platform_text[:2000],  # B站描述限制
                "tag": tags_str,
            }

            response = httpx.post(
                f"{self.api_base}/x/video/upload",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    post_id = str(data.get("data", {}).get("aid", ""))
                    logger.info("Bilibili publish success: %s", post_id)
                    return PublishResult(
                        platform=self.platform,
                        success=True,
                        post_id=post_id,
                    )
                else:
                    error_msg = data.get("message", f"API error code={data.get('code')}")
                    logger.warning("Bilibili API error: %s", error_msg)
                    return PublishResult(
                        platform=self.platform,
                        success=False,
                        error=error_msg,
                    )
            else:
                logger.warning("Bilibili HTTP %d: %s", response.status_code, response.text[:200])
                return PublishResult(
                    platform=self.platform,
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text[:200]}",
                )
        except Exception as e:
            logger.exception("Bilibili publish failed")
            return PublishResult(
                platform=self.platform,
                success=False,
                error=str(e),
            )
