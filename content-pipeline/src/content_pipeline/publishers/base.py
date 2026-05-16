"""
Content Pipeline — 发布器基础

每个平台发布器继承 BasePublisher，实现自己的 publish 方法。
发布器之间完全独立，不共享任何状态。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Content, PublishResult, Platform


class BasePublisher(ABC):
    """所有平台发布器的基类"""

    platform: Platform

    @abstractmethod
    def publish(self, content: Content) -> PublishResult:
        """
        发布内容到该平台。
        每个平台负责自己的认证、格式转换、发布逻辑。
        """
        ...

    def is_configured(self) -> bool:
        """检查该发布器的配置是否完整"""
        return True


class PublisherRegistry:
    """
    发布器注册表 — 管理所有平台发布器。
    
    纯粹的注册 + 查找，不涉及任何平台逻辑。
    """

    def __init__(self):
        self._publishers: dict[str, BasePublisher] = {}

    def register(self, publisher: BasePublisher):
        self._publishers[publisher.platform.value] = publisher

    def get(self, platform: str | Platform) -> BasePublisher | None:
        if isinstance(platform, Platform):
            platform = platform.value
        return self._publishers.get(platform)

    def all(self) -> dict[str, BasePublisher]:
        return dict(self._publishers)

    def configured(self) -> list[str]:
        return [name for name, p in self._publishers.items() if p.is_configured()]
