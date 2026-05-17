"""
Content Pipeline — 模型测试
"""

from content_pipeline.models import (
    Content, ContentStatus, Platform, PublishResult,
)


class TestContent:
    def test_create_content(self):
        c = Content(
            id="001",
            title="Test Title",
            body="Test body content here",
            platforms=[Platform.XIAOHONGSHU],
        )
        assert c.id == "001"
        assert c.title == "Test Title"
        assert c.body == "Test body content here"
        assert c.status == ContentStatus.IDEA
        assert Platform.XIAOHONGSHU in c.platforms

    def test_content_summary_short(self):
        c = Content(id="001", title="Short", body="Hello world")
        assert c.summary == "Hello world"

    def test_content_summary_long(self):
        long_body = "A" * 200
        c = Content(id="001", title="Long", body=long_body)
        assert len(c.summary) <= 80 + 3  # 80 + "..."

    def test_content_emoji(self):
        c = Content(id="001", title="Test", body="x",
                     platforms=[Platform.XIAOHONGSHU])
        assert c.emoji == "📕"

    def test_content_emoji_empty(self):
        c = Content(id="001", title="Test", body="x")
        assert c.emoji == "📄"

    def test_to_markdown_roundtrip(self):
        original = Content(
            id="042",
            title="Test Title",
            body="This is a test body.",
            platforms=[Platform.XIAOHONGSHU, Platform.TWITTER],
            tags=["ai", "automation"],
        )
        md = original.to_markdown()
        restored = Content.from_markdown_text_for_test(md)
        assert restored.id == original.id
        assert restored.title == original.title
        # to_markdown adds "# Title" header before body in output
        assert original.body in restored.body
        assert Platform.XIAOHONGSHU in restored.platforms
        assert Platform.TWITTER in restored.platforms

    def test_from_markdown_with_frontmatter(self, tmp_path):
        content = """---
id: "005"
title: "测试内容"
status: drafting
platforms: ["xiaohongshu"]
---
# 测试内容

这是正文内容。
"""
        f = tmp_path / "005_test.md"
        f.write_text(content, encoding="utf-8")

        c = Content.from_markdown(f)
        assert c.id == "005"
        assert c.title == "测试内容"
        assert c.status == ContentStatus.DRAFTING
        assert "这是正文内容" in c.body

    def test_from_markdown_no_frontmatter(self, tmp_path):
        content = """# Simple Title

Just some body text."""
        f = tmp_path / "simple.md"
        f.write_text(content, encoding="utf-8")

        c = Content.from_markdown(f)
        assert c.id == "simple"
        assert c.title == "Simple Title"
        assert "Just some body text" in c.body


class TestPublishResult:
    def test_success(self):
        r = PublishResult(
            platform=Platform.XIAOHONGSHU,
            success=True,
            url="https://xiaohongshu.com/explore/xxx",
        )
        assert r.success is True
        assert r.url == "https://xiaohongshu.com/explore/xxx"

    def test_failure(self):
        r = PublishResult(
            platform=Platform.XIAOHONGSHU,
            success=False,
            error="Auth failed",
        )
        assert r.success is False
        assert r.error == "Auth failed"


# 辅助测试方法
def _test_from_markdown_text(cls, text: str) -> Content:
    """从字符串解析 Content（测试用）"""
    import tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(text)
        path = f.name
    try:
        return cls.from_markdown(path)
    finally:
        Path(path).unlink()

# monkey-patch for testing
Content.from_markdown_text_for_test = classmethod(_test_from_markdown_text)
