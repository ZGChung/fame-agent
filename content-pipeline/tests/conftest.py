"""
Content Pipeline — 共享 fixtures
"""

import pytest


@pytest.fixture
def sample_content():
    """简单的测试内容"""
    from content_pipeline.models import Content, Platform, ContentStatus
    return Content(
        id="test_001",
        title="Test Content",
        body="This is test body content for pipeline testing.",
        platforms=[Platform.XIAOHONGSHU],
        status=ContentStatus.DRAFTING,
    )
