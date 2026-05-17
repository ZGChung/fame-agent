"""
Content Pipeline — 配置管理

支持 JSON / YAML 配置文件 + 环境变量覆盖敏感字段。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"


@dataclass
class PlatformConfig:
    """单个平台的配置"""
    enabled: bool = True
    max_chars: int = 1000
    language: str = "zh-CN"
    api_key: str = ""
    api_secret: str = ""
    bearer_token: str = ""
    access_token: str = ""
    cookie_path: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class VideoConfig:
    enabled: bool = True
    default_service: str = "ffmpeg"
    duration_per_image: float = 3.0
    transition: str = "fade"
    resolution: str = "1080x1920"
    tts_provider: str = "elevenlabs"
    tts_voice_id: str = "rachel"
    tts_fallback_zh: str = "Tingting"
    tts_fallback_en: str = "Daniel"
    api_keys: dict = field(default_factory=dict)


@dataclass
class ImageConfig:
    default_style: str = "modern"
    size: str = "1024x1024"
    openai_api_key: str = ""


@dataclass
class ReviewConfig:
    """AI review panel configuration.

    Controls which review dimensions are active, confidence thresholds,
    the LLM model used for each dimension, and where criteria Markdown
    files are loaded from.
    """

    enabled: bool = True
    """Master switch to enable/disable AI review entirely."""

    # Dimension toggles
    fact_check: bool = True
    quality: bool = True
    style: bool = True
    safety: bool = True
    platform_compliance: bool = True

    # Confidence thresholds for review levels
    auto_threshold: float = 0.85
    """Content with overall confidence >= this is auto-approved (review_level='auto')."""
    review_auto_threshold: float = 0.7
    """Content with overall confidence >= this but < auto_threshold gets 'review_auto'."""

    # Quality score threshold (quality dimension uses 1-10 score)
    quality_min_score: int = 7
    """Content with quality < this score is rejected regardless of other dimensions."""

    # Flag policy
    auto_approve_on_flags: bool = False
    """If True, content with only flags (no fails) is auto-approved.
    If False (default), flagged content stays at 'review_auto' level."""

    # LLM configuration
    model: str = "gpt-4o-mini"
    """Default model for all review dimensions. Can be overridden per dimension."""

    api_key: str = ""
    """OpenAI API key. Falls back to OPENAI_API_KEY environment variable."""

    # Criteria files
    criteria_dir: str = "criteria"
    """Directory containing Markdown criteria files loaded as review context."""

    # Timeouts
    timeout: float = 30.0
    """Timeout in seconds for each LLM call."""

    max_retries: int = 2
    """Max retries per dimension on API failure."""

    # Per-dimension model overrides
    dimension_models: dict[str, str] = field(default_factory=dict)
    """Override the model for specific dimensions, e.g. {'fact_check': 'gpt-4o'}."""


@dataclass
class PipelineConfig:
    """完整配置"""
    version: str = "2.0"
    description: str = "Jayson's Content Pipeline"

    # 文件夹路径（相对或绝对）
    content_root: str = "content"
    input_folder: str = "input"
    processing_folder: str = "processing"
    queue_folder: str = "queue"
    published_folder: str = "published"
    output_folder: str = "output"

    # 平台配置
    platforms: dict[str, PlatformConfig] = field(default_factory=dict)

    # 媒体配置
    video: VideoConfig = field(default_factory=VideoConfig)
    image: ImageConfig = field(default_factory=ImageConfig)

    # AI review configuration
    review: ReviewConfig = field(default_factory=ReviewConfig)

    # 旧文件夹路径（自动检测，不序列化）
    _legacy_folders: dict = field(default_factory=dict, repr=False, compare=False)

    def resolve_path(self, *parts: str) -> Path:
        """解析内容路径（相对 content_root 或绝对路径）"""
        path = Path(*parts)
        if path.is_absolute():
            return path
        return BASE_DIR / self.content_root / path

    def get_platform(self, name: str) -> Optional[PlatformConfig]:
        return self.platforms.get(name)

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> PipelineConfig:
        """从配置文件加载"""
        path = Path(path) if path else DEFAULT_CONFIG_PATH

        if not path.exists():
            return cls._default()

        raw = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml") and HAS_YAML:
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)

        config = cls._from_dict(data)

        # 自动检测已有的内容文件夹，确保兼容旧结构
        config._auto_detect_legacy_folders()

        return config

    def _auto_detect_legacy_folders(self):
        """
        自动检测已有的内容文件夹。
        如果旧文件夹存在（published/, blog/, onhold/），
        将它们加入搜索路径。
        """
        legacy = {
            "published": BASE_DIR / "published",
            "blog": BASE_DIR / "blog",
            "onhold": BASE_DIR / "onhold",
        }
        self._legacy_folders = {}
        for name, path in legacy.items():
            if path.is_dir() and any(path.iterdir()):
                self._legacy_folders[name] = str(path)

    @classmethod
    def _default(cls) -> PipelineConfig:
        return cls(
            platforms={
                "xiaohongshu": PlatformConfig(enabled=True, max_chars=1000),
                "twitter": PlatformConfig(enabled=True, max_chars=280, language="en-US"),
                "linkedin": PlatformConfig(enabled=True, max_chars=3000, language="en-US"),
                "zhihu": PlatformConfig(enabled=True, max_chars=10000),
                "youtube": PlatformConfig(enabled=False, max_chars=5000),
                "tiktok": PlatformConfig(enabled=False, max_chars=2200),
            }
        )

    @classmethod
    def _from_dict(cls, data: dict) -> PipelineConfig:
        platforms = {}
        raw_platforms = data.get("platforms", {})

        if isinstance(raw_platforms, list):
            # 旧格式：platforms 是数组 [{id: ..., name: ..., max_chars: ...}]
            for item in raw_platforms:
                name = item.get("id", item.get("name", "unknown"))
                platforms[name] = PlatformConfig(
                    enabled=item.get("enabled", True),
                    max_chars=item.get("max_chars", 1000),
                    language=item.get("language", "zh-CN"),
                )
        elif isinstance(raw_platforms, dict):
            # 新格式：platforms 是字典 {name: {config}}
            for name, cfg in raw_platforms.items():
                if isinstance(cfg, dict):
                    platforms[name] = PlatformConfig(**cfg)
                else:
                    platforms[name] = PlatformConfig(enabled=True)

        video_data = data.get("video", {})
        image_data = data.get("image_generation", data.get("image", {}))

        return cls(
            version=data.get("version", "2.0"),
            description=data.get("description", ""),
            content_root=data.get("content_root", "content"),
            input_folder=data.get("input_folder", "input"),
            processing_folder=data.get("processing_folder", "processing"),
            queue_folder=data.get("queue_folder", "queue"),
            published_folder=data.get("published_folder", "published"),
            output_folder=data.get("output_folder", "output"),
            platforms=platforms,
            video=VideoConfig(
                enabled=video_data.get("enabled", True),
                default_service=video_data.get("default_service", "ffmpeg"),
                duration_per_image=video_data.get("duration_per_image", 3.0),
                transition=video_data.get("transition", "fade"),
                resolution=video_data.get("resolution", "1080x1920"),
                tts_provider=video_data.get("tts", {}).get("provider", "elevenlabs"),
                tts_voice_id=video_data.get("tts", {}).get("voice_id", "rachel"),
                tts_fallback_zh=video_data.get("tts", {}).get("fallback_voice_zh", "Tingting"),
                tts_fallback_en=video_data.get("tts", {}).get("fallback_voice_en", "Daniel"),
                api_keys={
                    k: v for k, v in video_data.get("services", {}).items()
                    if isinstance(v, dict) and v.get("api_key")
                },
            ),
            image=ImageConfig(
                default_style=image_data.get("default_style", "modern"),
                size=image_data.get("size", "1024x1024"),
                openai_api_key=(
                    image_data.get("api_key")
                    or data.get("openai", {}).get("api_key")
                    or os.environ.get("OPENAI_API_KEY", "")
                ),
            ),
            review=cls._parse_review_config(data.get("review", {})),
        )

    @staticmethod
    def _parse_review_config(raw: dict) -> ReviewConfig:
        """Parse review configuration from a raw dict."""
        dim_models = raw.get("dimension_models", {})
        if isinstance(dim_models, list):
            dim_models = {d.get("dimension", ""): d.get("model", "") for d in dim_models}
        return ReviewConfig(
            enabled=raw.get("enabled", True),
            fact_check=raw.get("fact_check", True),
            quality=raw.get("quality", True),
            style=raw.get("style", True),
            safety=raw.get("safety", True),
            platform_compliance=raw.get("platform_compliance", True),
            auto_threshold=raw.get("auto_threshold", 0.85),
            review_auto_threshold=raw.get("review_auto_threshold", 0.7),
            quality_min_score=raw.get("quality_min_score", 7),
            auto_approve_on_flags=raw.get("auto_approve_on_flags", False),
            model=raw.get("model", "gpt-4o-mini"),
            api_key=raw.get("api_key", ""),
            criteria_dir=raw.get("criteria_dir", "criteria"),
            timeout=raw.get("timeout", 30.0),
            max_retries=raw.get("max_retries", 2),
            dimension_models=dim_models,
        )
