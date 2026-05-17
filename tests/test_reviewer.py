"""
Tests for AI Review Panel (reviewer.py).

All OpenAI API calls are mocked — no real network access.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from content_pipeline.models import Content, ContentStatus, Platform, ReviewResult
from content_pipeline.config import ReviewConfig
from content_pipeline.reviewer import (
    AIReviewPanel,
    DIMENSION_DEFS,
    load_criteria,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_content() -> Content:
    return Content(
        id="test-001",
        title="AI时代人类的核心竞争力",
        body="随着AI技术的快速发展，很多人开始担心自己的工作会被取代。"
             "但真正的核心不是和AI比技能，而是学会指挥AI。"
             "元认知能力——知道自己想要什么、能判断什么是好结果——"
             "将成为未来最稀缺的能力。",
        status=ContentStatus.DRAFTING,
        platforms=[Platform.XIAOHONGSHU],
        tags=["AI", "职场", "认知"],
    )


@pytest.fixture
def review_config() -> ReviewConfig:
    return ReviewConfig(
        enabled=True,
        fact_check=True,
        quality=True,
        style=True,
        safety=True,
        platform_compliance=True,
        auto_threshold=0.85,
        review_auto_threshold=0.7,
        quality_min_score=7,
        auto_approve_on_flags=False,
        model="gpt-4o-mini",
        api_key="test-key",
        criteria_dir="tests/fixtures/criteria",
        timeout=10.0,
        max_retries=0,
    )


@pytest.fixture
def panel(review_config) -> AIReviewPanel:
    """Review panel with mocked OpenAI client."""
    panel = AIReviewPanel(review_config)
    panel._client = MagicMock()  # Pre-set mock client
    return panel


# ---------------------------------------------------------------------------
# ReviewResult tests
# ---------------------------------------------------------------------------

class TestReviewResult:
    def test_defaults(self):
        r = ReviewResult()
        assert r.decision == "pending"
        assert r.review_level == "manual"
        assert r.dimensions == {}
        assert r.notes == []

    def test_is_approved_auto(self):
        r = ReviewResult(decision="auto_approve")
        assert r.is_approved() is True

    def test_is_approved_flag(self):
        r = ReviewResult(decision="flag")
        assert r.is_approved() is True

    def test_is_approved_reject(self):
        r = ReviewResult(decision="reject")
        assert r.is_approved() is False

    def test_needs_human_review_manual(self):
        r = ReviewResult(review_level="manual")
        assert r.needs_human_review() is True

    def test_needs_human_review_reject(self):
        r = ReviewResult(decision="reject")
        assert r.needs_human_review() is True

    def test_needs_human_review_auto(self):
        r = ReviewResult(review_level="auto", decision="auto_approve")
        assert r.needs_human_review() is False

    def test_to_dict_roundtrip(self):
        r = ReviewResult(
            dimensions={"quality": {"verdict": "8", "reasoning": "Good"}},
            overall_confidence=0.9,
            decision="auto_approve",
            review_level="auto",
            notes=["All good"],
        )
        d = r.to_dict()
        assert d["decision"] == "auto_approve"
        assert d["review_level"] == "auto"
        assert d["overall_confidence"] == 0.9


# ---------------------------------------------------------------------------
# Dimension definitions
# ---------------------------------------------------------------------------

class TestDimensionDefs:
    def test_all_five_dimensions_defined(self):
        expected = {"fact_check", "quality", "style", "safety", "platform_compliance"}
        assert set(DIMENSION_DEFS.keys()) == expected

    def test_each_dimension_has_system_prompt(self):
        for dim, defn in DIMENSION_DEFS.items():
            assert "system_prompt" in defn, f"{dim} missing system_prompt"
            assert "{criteria}" in defn["system_prompt"], f"{dim} missing criteria placeholder"

    def test_platform_compliance_has_platform_info(self):
        assert "{platform_info}" in DIMENSION_DEFS["platform_compliance"]["system_prompt"]


# ---------------------------------------------------------------------------
# Criteria loading
# ---------------------------------------------------------------------------

class TestLoadCriteria:
    def test_nonexistent_dir(self, tmp_path):
        result = load_criteria(tmp_path / "nonexistent")
        assert result == {}

    def test_loads_md_files(self, tmp_path: Path):
        criteria_dir = tmp_path / "criteria"
        criteria_dir.mkdir()
        (criteria_dir / "fact_check.md").write_text("# Fact Check Rules\nBe accurate.", encoding="utf-8")
        (criteria_dir / "style.md").write_text("# Style Rules\nUse emoji.", encoding="utf-8")

        result = load_criteria(criteria_dir)
        assert "fact_check" in result
        assert "# Fact Check Rules" in result["fact_check"]
        assert "style" in result
        assert "# Style Rules" in result["style"]

    def test_skips_empty_files(self, tmp_path: Path):
        criteria_dir = tmp_path / "criteria"
        criteria_dir.mkdir()
        (criteria_dir / "empty.md").write_text("", encoding="utf-8")
        (criteria_dir / "has_content.md").write_text("# Good", encoding="utf-8")

        result = load_criteria(criteria_dir)
        assert "empty" not in result
        assert "has_content" in result


# ---------------------------------------------------------------------------
# Review panel — disabled
# ---------------------------------------------------------------------------

class TestPanelDisabled:
    def test_disabled_review_bypasses(self, sample_content):
        config = ReviewConfig(enabled=False, api_key="test-key")
        panel = AIReviewPanel(config)
        panel._client = MagicMock()

        result = panel.review(sample_content)
        assert result.decision == "auto_approve"
        assert result.review_level == "auto"
        assert "disabled" in result.notes[0].lower()
        assert panel._client.chat.completions.create.call_count == 0


# ---------------------------------------------------------------------------
# Aggregation logic (no API calls — mock dimension results)
# ---------------------------------------------------------------------------

class TestAggregation:
    def make_dim_result(self, verdict="pass", confidence=0.9, **extras):
        return {"verdict": verdict, "reasoning": "test", "confidence": confidence, **extras}

    def test_all_pass_auto_approve(self, panel):
        results = {
            "fact_check": self.make_dim_result("pass", 0.95),
            "quality": self.make_dim_result("8", 0.90, score=8),
            "style": self.make_dim_result("pass", 0.92),
            "safety": self.make_dim_result("pass", 0.98),
            "platform_compliance": self.make_dim_result("pass", 0.95),
        }
        result = panel._aggregate(results)
        assert result.decision == "auto_approve"
        assert result.review_level == "auto"
        assert result.is_approved()

    def test_quality_below_threshold_rejects(self, panel):
        """Quality score < 7 should reject."""
        results = {
            "fact_check": self.make_dim_result("pass", 0.9),
            "quality": self.make_dim_result("5", 0.85, score=5),
            "style": self.make_dim_result("pass", 0.9),
            "safety": self.make_dim_result("pass", 0.95),
            "platform_compliance": self.make_dim_result("pass", 0.9),
        }
        result = panel._aggregate(results)
        assert result.decision == "reject"
        assert result.review_level == "manual"

    def test_quality_on_threshold_passes(self, panel):
        """Quality score = 7 should NOT reject (>= not <)."""
        results = {
            "fact_check": self.make_dim_result("pass", 0.9),
            "quality": self.make_dim_result("7", 0.85, score=7),
            "style": self.make_dim_result("pass", 0.9),
            "safety": self.make_dim_result("pass", 0.95),
            "platform_compliance": self.make_dim_result("pass", 0.9),
        }
        result = panel._aggregate(results)
        assert result.decision == "auto_approve"

    def test_fail_rejects(self, panel):
        """Single fail rejects regardless of other dims."""
        results = {
            "fact_check": self.make_dim_result("fail", 0.8),
            "quality": self.make_dim_result("9", 0.95, score=9),
            "style": self.make_dim_result("pass", 0.9),
            "safety": self.make_dim_result("pass", 0.95),
            "platform_compliance": self.make_dim_result("pass", 0.9),
        }
        result = panel._aggregate(results)
        assert result.decision == "reject"
        assert result.review_level == "manual"

    def test_flags_no_fail_review_auto(self, panel):
        """Flags with no fails: review_auto level (default config)."""
        panel.config.auto_approve_on_flags = False
        results = {
            "fact_check": self.make_dim_result("flag", 0.8),
            "quality": self.make_dim_result("8", 0.85, score=8),
            "style": self.make_dim_result("pass", 0.9),
            "safety": self.make_dim_result("pass", 0.95),
            "platform_compliance": self.make_dim_result("pass", 0.9),
        }
        result = panel._aggregate(results)
        assert result.decision == "flag"
        assert result.review_level == "review_auto"

    def test_flags_auto_approve_when_enabled(self, panel):
        """Flags with auto_approve_on_flags=True."""
        panel.config.auto_approve_on_flags = True
        results = {
            "fact_check": self.make_dim_result("flag", 0.8),
            "quality": self.make_dim_result("8", 0.85, score=8),
            "style": self.make_dim_result("pass", 0.9),
            "safety": self.make_dim_result("pass", 0.95),
            "platform_compliance": self.make_dim_result("pass", 0.9),
        }
        result = panel._aggregate(results)
        assert result.decision == "auto_approve"
        assert result.is_approved()

    def test_error_dimension_pending(self, panel):
        """Error in a dimension → pending."""
        results = {
            "fact_check": self.make_dim_result("error", 0.0),
            "quality": self.make_dim_result("8", 0.85, score=8),
            "style": self.make_dim_result("pass", 0.9),
            "safety": self.make_dim_result("pass", 0.95),
            "platform_compliance": self.make_dim_result("pass", 0.9),
        }
        result = panel._aggregate(results)
        assert result.decision == "pending"
        assert result.review_level == "manual"

    def test_low_confidence_downgrades_to_manual(self, panel):
        """Very low confidence across dims should → manual."""
        results = {
            "fact_check": self.make_dim_result("pass", 0.55),
            "quality": self.make_dim_result("7", 0.50, score=7),
            "style": self.make_dim_result("pass", 0.55),
            "safety": self.make_dim_result("pass", 0.50),
            "platform_compliance": self.make_dim_result("pass", 0.55),
        }
        result = panel._aggregate(results)
        assert result.review_level == "manual"


# ---------------------------------------------------------------------------
# Content prompt building
# ---------------------------------------------------------------------------

class TestContentPrompt:
    def test_builds_with_title_and_body(self, panel, sample_content):
        prompt = panel._build_content_prompt(sample_content)
        assert sample_content.title in prompt
        assert sample_content.body in prompt

    def test_builds_with_platforms(self, panel, sample_content):
        prompt = panel._build_content_prompt(sample_content)
        assert "xiaohongshu" in prompt.lower()

    def test_builds_with_tags(self, panel, sample_content):
        prompt = panel._build_content_prompt(sample_content)
        assert "AI" in prompt
        assert "职场" in prompt


# ---------------------------------------------------------------------------
# Platform info building
# ---------------------------------------------------------------------------

class TestPlatformInfo:
    def test_builds_for_single_platform(self, panel, sample_content):
        info = panel._build_platform_info(sample_content)
        assert "xiaohongshu" in info
        assert "1000" in info

    def test_no_platforms(self, panel):
        content = Content(id="t", title="T", body="B")
        info = panel._build_platform_info(content)
        assert "No specific platform targets" in info


# ---------------------------------------------------------------------------
# JSON response parsing
# ---------------------------------------------------------------------------

class TestParseJSON:
    def test_clean_json(self):
        result = AIReviewPanel._parse_json_response(
            '{"verdict": "pass", "confidence": 0.9}', "test"
        )
        assert result["verdict"] == "pass"
        assert result["confidence"] == 0.9

    def test_json_with_markdown_fences(self):
        result = AIReviewPanel._parse_json_response(
            '```json\n{"verdict": "flag", "confidence": 0.7}\n```', "test"
        )
        assert result["verdict"] == "flag"
        assert result["confidence"] == 0.7

    def test_invalid_json(self):
        result = AIReviewPanel._parse_json_response(
            "not json at all", "test"
        )
        assert result.get("verdict") == "error"


# ---------------------------------------------------------------------------
# Mocked API review (full flow)
# ---------------------------------------------------------------------------

class TestMockedReview:
    """Test the full review flow with mocked API responses."""

    def mock_api_response(self, verdict="pass", confidence=0.9, score=8):
        """Create a mock chat completion with the given verdict."""
        response = MagicMock()
        if verdict == "pass":
            body = json.dumps({
                "verdict": "pass",
                "reasoning": "Looks good.",
                "confidence": confidence,
            })
        elif verdict == "score":
            body = json.dumps({
                "verdict": "pass",
                "score": score,
                "sub_scores": {"completeness": 8, "coherence": 8, "originality": 8,
                               "information_density": 8, "engagement": 8},
                "reasoning": "Solid content.",
                "strengths": ["Clear structure"],
                "weaknesses": [],
                "confidence": confidence,
            })
        elif verdict == "fail":
            body = json.dumps({
                "verdict": "fail",
                "reasoning": "Contains false claims.",
                "issues": ["Claim X is incorrect"],
                "confidence": confidence,
            })
        elif verdict == "flag":
            body = json.dumps({
                "verdict": "flag",
                "reasoning": "Minor issues.",
                "issues": ["Ambiguous claim"],
                "confidence": confidence,
            })
        elif verdict == "compliance":
            body = json.dumps({
                "verdict": "pass",
                "reasoning": "Within limits.",
                "issues": [],
                "platform_checks": {"char_limit": True, "hashtag_count": 2, "has_line_issues": False},
                "confidence": confidence,
            })
        else:
            body = '{"verdict": "pass", "reasoning": "ok", "confidence": 0.9}'

        response.choices = [MagicMock()]
        response.choices[0].message.content = body
        return response

    def test_review_all_pass(self, panel, sample_content):
        # Mock each dimension's API call
        panel._client.chat.completions.create.side_effect = [
            self.mock_api_response("pass", 0.95),      # fact_check
            self.mock_api_response("score", 0.9, score=8),  # quality
            self.mock_api_response("pass", 0.92),       # style
            self.mock_api_response("pass", 0.98),       # safety
            self.mock_api_response("compliance", 0.95),  # platform_compliance
        ]

        result = panel.review(sample_content)
        assert result.decision == "auto_approve"
        assert result.review_level == "auto"
        assert len(result.dimensions) == 5

    def test_review_with_disabled_dimension(self, panel, sample_content):
        panel.config.fact_check = False
        panel._client.chat.completions.create.side_effect = [
            self.mock_api_response("score", 0.9, score=8),  # quality
            self.mock_api_response("pass", 0.92),       # style
            self.mock_api_response("pass", 0.98),       # safety
            self.mock_api_response("compliance", 0.95),  # platform_compliance
        ]

        result = panel.review(sample_content)
        assert result.dimensions["fact_check"]["verdict"] == "pass"
        assert "disabled" in result.dimensions["fact_check"]["reasoning"].lower()
        # Only 4 API calls (fact_check skipped)
        assert panel._client.chat.completions.create.call_count == 4

    def test_review_with_fail(self, panel, sample_content):
        panel._client.chat.completions.create.side_effect = [
            self.mock_api_response("fail", 0.8),        # fact_check fails
            self.mock_api_response("score", 0.9, score=9),  # quality
            self.mock_api_response("pass", 0.92),       # style
            self.mock_api_response("pass", 0.98),       # safety
            self.mock_api_response("compliance", 0.95),  # platform_compliance
        ]

        result = panel.review(sample_content)
        assert result.decision == "reject"
        assert result.review_level == "manual"

    def test_review_and_attach(self, panel, sample_content):
        panel._client.chat.completions.create.side_effect = [
            self.mock_api_response("pass", 0.95),
            self.mock_api_response("score", 0.9, score=8),
            self.mock_api_response("pass", 0.92),
            self.mock_api_response("pass", 0.98),
            self.mock_api_response("compliance", 0.95),
        ]

        result = panel.review_and_attach(sample_content)
        assert sample_content.review_result is not None
        assert sample_content.review_result["decision"] == "auto_approve"
