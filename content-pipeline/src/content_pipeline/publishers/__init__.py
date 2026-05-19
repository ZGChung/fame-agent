"""
Content Pipeline — 各平台发布器注册

保持发布器之间完全独立，通过 Registry 统一管理。
"""

from .base import BasePublisher, PublisherRegistry
from .xiaohongshu import XiaohongshuPublisher
from .twitter import TwitterPublisher

# 未来添加的平台在这里注册（完全解耦，互不影响）
# from .linkedin import LinkedInPublisher
# from .bilibili import BilibiliPublisher

__all__ = [
    "BasePublisher",
    "PublisherRegistry",
    "XiaohongshuPublisher",
    "TwitterPublisher",
]


def create_default_registry() -> PublisherRegistry:
    """创建默认发布器注册表，包含所有配置好的发布器"""
    registry = PublisherRegistry()

    # 小红书
    xhs = XiaohongshuPublisher()
    if xhs.is_configured():
        registry.register(xhs)

    # Twitter
    tw = TwitterPublisher()
    if tw.is_configured():
        registry.register(tw)

    # 未来添加：
    # if linkedin credentials available...
    # registry.register(LinkedInPublisher(...))

    return registry
