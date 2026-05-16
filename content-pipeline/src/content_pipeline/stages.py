"""
Content Pipeline — 处理阶段

Pipeline 中的各个独立处理阶段，每个阶段继承 BaseStage。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .models import Content, ContentStatus

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """阶段处理结果"""
    success: bool
    content: Optional[Content] = None
    message: str = ""
    errors: list[str] = field(default_factory=list)


class BaseStage(ABC):
    """所有处理阶段的基类"""

    name: str = "base"

    @abstractmethod
    def process(self, content: Content) -> StageResult:
        """处理一个内容，返回处理结果"""
        ...


class DraftStage(BaseStage):
    """
    草稿生成阶段 — 为内容生成各平台适配版本。
    
    根据内容的原始主题和平台配置，生成平台特有的格式。
    当前保持原样传递，未来可以集成 LLM 生成。
    """

    name = "draft"

    def process(self, content: Content) -> StageResult:
        """为内容生成各平台版本"""
        try:
            # 目前逻辑：保留原文作为各平台通用版本
            # TODO: 后续可调用 LLM 生成各平台专属文案
            content.status = ContentStatus.DRAFTING
            content.updated = datetime.now().strftime("%Y-%m-%d")
            return StageResult(success=True, content=content, message="Draft ready")
        except Exception as e:
            return StageResult(success=False, content=content, message=str(e))


class ReviewStage(BaseStage):
    """
    审核阶段 — 人工审核或自动规则审核。
    
    当前自动通过，可以配置自动批准规则。
    """

    name = "review"

    def __init__(self, auto_approve: bool = True):
        self.auto_approve = auto_approve

    def process(self, content: Content) -> StageResult:
        if self.auto_approve:
            content.status = ContentStatus.SCHEDULED
            content.updated = datetime.now().strftime("%Y-%m-%d")
            return StageResult(success=True, content=content, message="Auto-approved")
        return StageResult(
            success=True, content=content, message="Pending human review"
        )


class ValidateStage(BaseStage):
    """
    验证阶段 — 检查内容完整性。
    
    确保必填字段存在、长度合规等。
    """

    name = "validate"

    def process(self, content: Content) -> StageResult:
        errors = []
        if not content.title:
            errors.append("Title is required")
        if not content.body:
            errors.append("Body is required")
        if not content.platforms:
            errors.append("At least one platform must be specified")

        if errors:
            return StageResult(success=False, content=content, errors=errors)
        return StageResult(success=True, content=content, message="Validation passed")
