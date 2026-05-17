"""
Content Pipeline — 各平台发布器注册

保持发布器之间完全独立，通过 Registry 统一管理。
"""

from .base import BasePublisher, PublisherRegistry
from .bilibili import BilibiliPublisher
from .linkedin import LinkedInPublisher
from .twitter import TwitterPublisher
from .xiaohongshu import XiaohongshuPublisher

__all__ = [
    "BasePublisher",
    "PublisherRegistry",
    "BilibiliPublisher",
    "LinkedInPublisher",
    "TwitterPublisher",
    "XiaohongshuPublisher",
]


def create_default_registry() -> PublisherRegistry:
    """创建默认发布器注册表，包含所有配置好的发布器"""
    registry = PublisherRegistry()

    # B站
    bilibili = BilibiliPublisher()
    if bilibili.is_configured():
        registry.register(bilibili)

    # LinkedIn
    linkedin = LinkedInPublisher()
    if linkedin.is_configured():
        registry.register(linkedin)

    # Twitter
    twitter = TwitterPublisher()
    if twitter.is_configured():
        registry.register(twitter)

    # 小红书
    xhs = XiaohongshuPublisher()
    if xhs.is_configured():
        registry.register(xhs)

    return registry
