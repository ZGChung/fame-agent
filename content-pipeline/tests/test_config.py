"""
Content Pipeline — 配置测试
"""

import json
import tempfile
from pathlib import Path

import pytest

from content_pipeline.config import PipelineConfig, PlatformConfig, VideoConfig


class TestPipelineConfig:
    def test_default_config(self):
        config = PipelineConfig._default()
        assert config.version == "2.0"
        assert "xiaohongshu" in config.platforms
        assert config.platforms["xiaohongshu"].enabled is True

    def test_platform_defaults(self):
        pc = PlatformConfig()
        assert pc.enabled is True
        assert pc.max_chars == 1000
        assert pc.language == "zh-CN"

    def test_video_defaults(self):
        vc = VideoConfig()
        assert vc.enabled is True
        assert vc.default_service == "ffmpeg"
        assert vc.resolution == "1080x1920"

    def test_load_from_json(self):
        data = {
            "version": "2.0",
            "platforms": {
                "xiaohongshu": {"enabled": True, "max_chars": 1000},
                "twitter": {"enabled": True, "max_chars": 280},
            },
        }
        config = PipelineConfig._from_dict(data)
        assert config.platforms["xiaohongshu"].max_chars == 1000
        assert config.platforms["twitter"].max_chars == 280

    def test_resolve_path_absolute(self):
        config = PipelineConfig()
        result = config.resolve_path("/tmp/test")
        assert str(result) == "/tmp/test"

    def test_resolve_path_relative(self):
        config = PipelineConfig(content_root="content")
        result = config.resolve_path("input")
        assert "content" in str(result)
        assert "input" in str(result)
