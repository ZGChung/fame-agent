"""
Content Pipeline — AI Review Panel

Runs 5 independent review dimensions against content using OpenAI-compatible
LLM APIs. Each dimension has its own system prompt, and results are aggregated
into a final decision (auto_approve / flag / reject).

Criteria Markdown files (criteria/*.md) are loaded as supplemental context
for the AI prompts, allowing domain-specific review standards.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI

from .config import ReviewConfig
from .models import Content, ReviewResult, Platform, PLATFORM_MAX_CHARS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dimension definitions — each has a name, verdict type, and system prompt
# ---------------------------------------------------------------------------

DIMENSION_DEFS: dict[str, dict] = {
    "fact_check": {
        "name": "事实核查",
        "verdict": "pass/flag/fail",
        "system_prompt": """You are a professional fact-checker reviewing content for a Chinese-language social media pipeline.

Your task: review the given content and evaluate factual accuracy.

Evaluate the following:
1. Are there any factual claims? Identify them.
2. Are the claims supported by data or widely-accepted knowledge?
3. Are there any obviously false or misleading claims?
4. Are statistics/numbers plausible?

Respond in the following JSON format ONLY (no other text):
{
  "verdict": "pass" | "flag" | "fail",
  "reasoning": "detailed explanation in Chinese",
  "issues": ["specific issue 1", "specific issue 2"],
  "confidence": 0.0-1.0
}

- "pass": all factual claims are accurate and supported.
- "flag": minor issues found (ambiguous claims, slightly outdated data) but not severe.
- "fail": contains false or seriously misleading information.

{criteria}""",
    },
    "quality": {
        "name": "内容质量",
        "verdict": "score 1-10",
        "system_prompt": """You are a content quality reviewer for a Chinese-language social media pipeline.

Your task: score the content on a 1-10 scale across multiple quality dimensions.

Evaluate:
1. Completeness: does the content fully cover its topic?
2. Coherence: is the structure logical and easy to follow?
3. Originality: is this unique or derivative? Does it add value?
4. Information density: is it substantive or filled with fluff?
5. Engagement potential: will it capture and hold reader attention?

Respond in the following JSON format ONLY (no other text):
{
  "score": 1-10 (integer),
  "sub_scores": {
    "completeness": 1-10,
    "coherence": 1-10,
    "originality": 1-10,
    "information_density": 1-10,
    "engagement": 1-10
  },
  "reasoning": "detailed explanation in Chinese",
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1"],
  "confidence": 0.0-1.0
}

{criteria}""",
    },
    "style": {
        "name": "风格适配",
        "verdict": "pass/flag",
        "system_prompt": """You are a style and tone reviewer for a Chinese-language social media content pipeline.

Your task: evaluate whether the content's style fits the target platform.

Evaluate:
1. Platform tone: is the voice appropriate for the target platform? (Xiaohongshu = warm & personal, Twitter = concise & punchy, LinkedIn = professional, Zhihu = analytical, YouTube/TikTok = engaging & visual)
2. Voice consistency: does the writing style stay consistent throughout?
3. Format: is the formatting appropriate (headings, paragraphs, emoji usage)?
4. Language quality: grammar, word choice, readability.

Respond in the following JSON format ONLY (no other text):
{
  "verdict": "pass" | "flag",
  "reasoning": "detailed explanation in Chinese",
  "issues": ["specific issue 1"],
  "confidence": 0.0-1.0
}

- "pass": style and formatting are appropriate.
- "flag": issues found that need attention but aren't deal-breakers.

{criteria}""",
    },
    "safety": {
        "name": "安全合规",
        "verdict": "pass/flag/fail",
        "system_prompt": """You are a safety and compliance reviewer for a Chinese-language social media content pipeline.

Your task: check the content for safety, policy, and legal compliance issues.

Evaluate:
1. Sensitive content: political, religious, ethnic, or social topics that could be problematic.
2. Policy compliance: does it follow general platform content policies?
3. Copyright: any potentially plagiarized or copyrighted material?
4. Privacy: any exposed personal information?
5. Harmful content: violence, hate speech, harassment, self-harm, illegal activities.

Respond in the following JSON format ONLY (no other text):
{
  "verdict": "pass" | "flag" | "fail",
  "reasoning": "detailed explanation in Chinese",
  "issues": ["specific issue 1"],
  "risk_level": "low" | "medium" | "high",
  "confidence": 0.0-1.0
}

- "pass": no safety concerns.
- "flag": minor concerns that warrant review but aren't clearly violations.
- "fail": clear policy violations or high-risk content.

{criteria}""",
    },
    "platform_compliance": {
        "name": "平台规则",
        "verdict": "pass/flag",
        "system_prompt": """You are a platform compliance reviewer for a Chinese-language social media content pipeline.

Your task: verify the content complies with platform-specific technical rules.

Evaluate:
1. Character limits: is the content within the platform's maximum character count?
2. Hashtag rules: are hashtags used appropriately (not excessive)?
3. Image guidelines: does the description suggest appropriate image usage?
4. Link policy: any links that might violate platform rules?
5. Formatting requirements: line breaks, special characters, markdown.

Target platform info:
{platform_info}

Respond in the following JSON format ONLY (no other text):
{
  "verdict": "pass" | "flag",
  "reasoning": "detailed explanation in Chinese",
  "issues": ["specific issue 1"],
  "platform_checks": {
    "char_limit": true/false,
    "hashtag_count": 0,
    "has_line_issues": true/false
  },
  "confidence": 0.0-1.0
}

- "pass": all platform rules are satisfied.
- "flag": one or more rules violated.

{criteria}""",
    },
}


# ---------------------------------------------------------------------------
# Criteria file loader
# ---------------------------------------------------------------------------

def load_criteria(criteria_dir: str | Path) -> dict[str, str]:
    """Load review criteria from Markdown files in the given directory.

    Each .md file's stem is used as the key (e.g., ``fact_check.md`` becomes
    key ``fact_check``). The file content is the value.

    Args:
        criteria_dir: Path to the criteria directory.

    Returns:
        Dict mapping dimension name to criteria text. Empty dict if the
        directory doesn't exist or contains no .md files.
    """
    criteria: dict[str, str] = {}
    path = Path(criteria_dir)
    if not path.is_dir():
        logger.debug("Criteria directory not found: %s", criteria_dir)
        return criteria

    for md_file in sorted(path.glob("*.md")):
        key = md_file.stem
        try:
            text = md_file.read_text(encoding="utf-8").strip()
            if text:
                criteria[key] = text
                logger.debug("Loaded criteria: %s (%d chars)", key, len(text))
        except Exception as e:
            logger.warning("Failed to read criteria file %s: %s", md_file, e)

    return criteria


# ---------------------------------------------------------------------------
# AI Review Panel
# ---------------------------------------------------------------------------

class AIReviewPanel:
    """Orchestrates AI review across 5 dimensions and aggregates results.

    Usage::

        config = ReviewConfig(model="gpt-4o-mini")
        panel = AIReviewPanel(config)
        result = panel.review(content)

    Args:
        config: ReviewConfig with dimension toggles, thresholds, model, etc.
    """

    def __init__(self, config: ReviewConfig):
        self.config = config
        self._client: Optional[OpenAI] = None
        self._criteria: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Client
    # ------------------------------------------------------------------

    @property
    def client(self) -> OpenAI:
        """Lazy-initialized OpenAI client."""
        if self._client is None:
            api_key = self.config.api_key or os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                raise ValueError(
                    "OpenAI API key not configured. Set review.api_key in config "
                    "or OPENAI_API_KEY environment variable."
                )
            self._client = OpenAI(api_key=api_key)
        return self._client

    # ------------------------------------------------------------------
    # Criteria
    # ------------------------------------------------------------------

    def _load_criteria(self) -> dict[str, str]:
        """Load criteria files, caching the result."""
        if not self._criteria:
            self._criteria = load_criteria(self.config.criteria_dir)
        return self._criteria

    def _get_criteria_text(self, dimension: str) -> str:
        """Get the criteria text for a specific dimension, formatted for prompt."""
        all_criteria = self._load_criteria()
        text = all_criteria.get(dimension, "")
        if text:
            return f"\n## Review Criteria (from {self.config.criteria_dir}/{dimension}.md)\n{text}\n"
        return ""

    # ------------------------------------------------------------------
    # Single dimension review
    # ------------------------------------------------------------------

    def _review_dimension(
        self,
        dimension: str,
        content: Content,
    ) -> dict:
        """Run a single AI review dimension against the content.

        Args:
            dimension: Dimension key (fact_check, quality, style, safety,
                       platform_compliance).
            content: The Content to review.

        Returns:
            Dict with keys: verdict, reasoning, confidence, and dimension-
            specific extras (e.g., score for quality, issues for others).
        """
        dim_def = DIMENSION_DEFS.get(dimension)
        if not dim_def:
            return {
                "verdict": "error",
                "reasoning": f"Unknown dimension: {dimension}",
                "confidence": 0.0,
            }

        criteria_text = self._get_criteria_text(dimension)
        system_prompt = dim_def["system_prompt"].replace("{criteria}", criteria_text)

        # Build platform info for platform_compliance dimension
        user_prompt = self._build_content_prompt(content)
        if dimension == "platform_compliance":
            platform_info = self._build_platform_info(content)
            system_prompt = dim_def["system_prompt"].replace(
                "{criteria}", criteria_text
            ).replace("{platform_info}", platform_info)

        # Get model for this dimension
        model = self.config.dimension_models.get(dimension, self.config.model)

        # Call LLM
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=800,
                    timeout=self.config.timeout,
                    response_format={"type": "json_object"},
                )

                raw = response.choices[0].message.content or "{}"
                result = self._parse_json_response(raw, dimension)

                # Ensure required fields — quality dimension uses score, not verdict
                if dimension == "quality":
                    result.setdefault("verdict", "pass")
                else:
                    result.setdefault("verdict", "flag")
                result.setdefault("reasoning", "")
                result.setdefault("confidence", 0.5)

                logger.info(
                    "Dimension %s: verdict=%s confidence=%.2f",
                    dimension, result.get("verdict"), result.get("confidence"),
                )
                return result

            except Exception as e:
                logger.warning(
                    "Dimension %s attempt %d/%d failed: %s",
                    dimension, attempt + 1, self.config.max_retries + 1, e,
                )
                if attempt == self.config.max_retries:
                    return {
                        "verdict": "error",
                        "reasoning": f"API error after {self.config.max_retries + 1} attempts: {e}",
                        "confidence": 0.0,
                    }
                time.sleep(1.0 * (attempt + 1))

        # Should never reach here
        return {"verdict": "error", "reasoning": "Unknown error", "confidence": 0.0}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_content_prompt(self, content: Content) -> str:
        """Build the user prompt with content details."""
        parts = [
            f"Title: {content.title}",
            f"Content:\n{content.body}",
        ]
        if content.platforms:
            platforms = [p.value for p in content.platforms]
            parts.append(f"Target Platforms: {', '.join(platforms)}")
        if content.tags:
            parts.append(f"Tags: {', '.join(content.tags)}")
        return "\n\n".join(parts)

    def _build_platform_info(self, content: Content) -> str:
        """Build platform-specific info for platform_compliance dimension."""
        lines = []
        for p in content.platforms:
            max_chars = PLATFORM_MAX_CHARS.get(p, 1000)
            lines.append(f"- {p.value}: max {max_chars} characters")
        return "\n".join(lines) if lines else "No specific platform targets."

    @staticmethod
    def _parse_json_response(raw: str, dimension: str) -> dict:
        """Parse LLM JSON response, handling markdown fences and other quirks."""
        import json

        text = raw.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            # Find first newline
            nl = text.find("\n")
            if nl != -1:
                text = text[nl + 1:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON object with braces
            import re
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse JSON for dimension %s: %s", dimension, raw[:200])
            return {"verdict": "error", "reasoning": f"Failed to parse response: {raw[:500]}"}

    # ------------------------------------------------------------------
    # Aggregation & decision logic
    # ------------------------------------------------------------------

    def _aggregate(self, results: dict[str, dict]) -> ReviewResult:
        """Aggregate dimension results into a final ReviewResult.

        Decision logic:
        - All dimensions pass → auto_approve
        - Quality ≥ threshold, no fails → auto_approve
        - Flags but no fails → depends on auto_approve_on_flags config
        - Any fail → reject
        """
        dimensions = {}
        verdicts: list[str] = []
        confidences: list[float] = []
        quality_score: Optional[int] = None
        notes: list[str] = []
        has_error = False

        for dim_name, dim_result in results.items():
            verdict = dim_result.get("verdict", "flag")
            confidence = dim_result.get("confidence", 0.5)

            dim_entry = {
                "verdict": verdict,
                "reasoning": dim_result.get("reasoning", ""),
                "confidence": confidence,
            }

            # Copy dimension-specific extras
            for extra_key in ("score", "sub_scores", "issues", "risk_level",
                              "strengths", "weaknesses", "platform_checks"):
                if extra_key in dim_result:
                    dim_entry[extra_key] = dim_result[extra_key]

            dimensions[dim_name] = dim_entry
            verdicts.append(verdict)
            confidences.append(confidence)

            if verdict == "error":
                has_error = True

            if dim_name == "quality" and "score" in dim_result:
                quality_score = dim_result["score"]

        # Calculate overall confidence
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Decision logic
        if has_error:
            decision = "pending"
            notes.append("One or more dimensions encountered an API error.")
            review_level = "manual"
        elif "fail" in verdicts:
            decision = "reject"
            fail_dims = [d for d, v in dimensions.items() if v.get("verdict") == "fail"]
            notes.append(f"Rejected due to failures in: {', '.join(fail_dims)}")
            review_level = "manual"
        elif quality_score is not None and quality_score < self.config.quality_min_score:
            decision = "reject"
            notes.append(
                f"Quality score {quality_score} below minimum threshold "
                f"({self.config.quality_min_score})."
            )
            review_level = "manual"
        elif "flag" in verdicts:
            if self.config.auto_approve_on_flags:
                decision = "auto_approve"
                notes.append("Flags found but auto_approve_on_flags is enabled.")
            else:
                decision = "flag"
                flag_dims = [d for d, v in dimensions.items() if v.get("verdict") == "flag"]
                notes.append(f"Flagged by: {', '.join(flag_dims)}. Review recommended.")
            review_level = "review_auto"
        else:
            # All passed
            decision = "auto_approve"
            notes.append("All dimensions passed.")
            review_level = "auto"

        # Adjust review_level based on overall confidence
        if overall_confidence >= self.config.auto_threshold and review_level == "auto":
            review_level = "auto"
        elif overall_confidence >= self.config.review_auto_threshold and review_level != "manual":
            review_level = "review_auto"
        else:
            # If already manual (reject) keep it; otherwise, low confidence → manual
            if decision != "reject":
                review_level = "manual"
                notes.append(
                    f"Overall confidence ({overall_confidence:.2f}) is below "
                    f"review_auto threshold ({self.config.review_auto_threshold})."
                )

        return ReviewResult(
            dimensions=dimensions,
            overall_confidence=round(overall_confidence, 4),
            decision=decision,
            review_level=review_level,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def review(self, content: Content) -> ReviewResult:
        """Run the full AI review panel against a single piece of content.

        Each enabled dimension runs as an independent LLM call (parallel in
        the future, sequential for now to keep things simple and debuggable).

        Args:
            content: The Content to review.

        Returns:
            ReviewResult with aggregated dimensions, confidence, decision,
            and review level.
        """
        if not self.config.enabled:
            return ReviewResult(
                dimensions={},
                overall_confidence=1.0,
                decision="auto_approve",
                review_level="auto",
                notes=["AI review is disabled in configuration."],
            )

        dimension_toggles = {
            "fact_check": self.config.fact_check,
            "quality": self.config.quality,
            "style": self.config.style,
            "safety": self.config.safety,
            "platform_compliance": self.config.platform_compliance,
        }

        results: dict[str, dict] = {}
        for dimension, enabled in dimension_toggles.items():
            if not enabled:
                results[dimension] = {
                    "verdict": "pass",
                    "reasoning": "Dimension disabled in configuration.",
                    "confidence": 1.0,
                }
                continue

            results[dimension] = self._review_dimension(dimension, content)

        return self._aggregate(results)

    def review_and_attach(self, content: Content) -> ReviewResult:
        """Run review and attach the result to the content object.

        Args:
            content: Content to review (mutated in place with review_result).

        Returns:
            The ReviewResult (also stored in content.review_result).
        """
        result = self.review(content)
        content.review_result = result.to_dict()
        content.status = content.status  # keep current status
        return result
