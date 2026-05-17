"""
Content Pipeline — Pipeline 测试
"""

from pathlib import Path

import pytest

from content_pipeline.models import Content, ContentStatus, Platform
from content_pipeline.pipeline import ContentStore, Pipeline
from content_pipeline.config import PipelineConfig


@pytest.fixture
def store(tmp_path):
    """创建临时内容存储"""
    content_root = tmp_path / "content"
    content_root.mkdir()
    config = PipelineConfig(
        content_root=str(content_root),
    )
    return ContentStore(config), config


class TestContentStore:
    def test_list_empty(self, store):
        cs, _ = store
        assert cs.list_content("input") == []

    def test_save_and_list(self, store):
        cs, _ = store
        c = Content(id="001", title="Test", body="Body")
        path = cs.save(c, "input")
        assert path.exists()

        contents = cs.list_content("input")
        assert len(contents) == 1
        assert contents[0].id == "001"

    def test_get_content_found(self, store):
        cs, _ = store
        c = Content(id="001", title="Test", body="Body")
        cs.save(c, "input")
        found = cs.get_content("001")
        assert found is not None
        assert found.id == "001"

    def test_get_content_not_found(self, store):
        cs, _ = store
        assert cs.get_content("999") is None

    def test_move_content(self, store):
        cs, _ = store
        c = Content(id="042", title="Move me", body="Moving")
        cs.save(c, "input")
        assert cs.move("042", "input", "processing")
        assert len(cs.list_content("input")) == 0
        assert len(cs.list_content("processing")) == 1

    def test_get_next_id(self, store):
        cs, _ = store
        assert cs.get_next_id() == "001"

        c = Content(id="005", title="Test", body="Body")
        cs.save(c, "input")
        assert cs.get_next_id() == "006"

    def test_update_status(self, store):
        cs, _ = store
        c = Content(id="001", title="Test", body="Body")
        cs.save(c, "input")
        assert cs.update_status("001", ContentStatus.PUBLISHED)
        # 状态更新后会移到 published
        assert len(cs.list_content("published")) == 1


class TestPipeline:
    def test_create_content(self, tmp_path):
        config = PipelineConfig(content_root=str(tmp_path))
        p = Pipeline(config)
        c = p.create_content("Hello", "World", ["xiaohongshu"])
        assert c.title == "Hello"
        assert Platform.XIAOHONGSHU in c.platforms

    def test_status(self, tmp_path):
        config = PipelineConfig(content_root=str(tmp_path))
        p = Pipeline(config)
        status = p.status()
        assert "input" in status
        assert "published" in status
