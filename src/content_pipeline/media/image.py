"""
Content Pipeline — 图片生成模块

支持 DALL-E 3 生成和 FFmpeg 占位符两种方式。
独立模块，不依赖 pipeline 其他部分。
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ImageGenerator:
    """
    图片生成器。
    
    优先使用 AI（DALL-E 3），回退到 FFmpeg 文字封面。
    """

    def __init__(self, openai_api_key: str = ""):
        self.openai_api_key = openai_api_key or ""

    def is_configured(self) -> bool:
        return bool(self.openai_api_key)

    def generate(self, title: str, body: str = "", output_path: str = "") -> Optional[str]:
        """
        生成图片。
        
        优先 AI 生成，不可用时回退到 FFmpeg 文字封面。
        """
        if self.is_configured():
            result = self._generate_ai(title, body, output_path)
            if result:
                return result

        logger.info("AI image generation unavailable, falling back to FFmpeg cover")
        return self._generate_ffmpeg_cover(title, output_path)

    def _generate_ai(self, title: str, body: str, output_path: str) -> Optional[str]:
        """使用 DALL-E 3 生成图片"""
        try:
            import openai
            openai.api_key = self.openai_api_key

            # 提取核心内容作为 prompt
            core_points = [line.strip() for line in body.split("\n")
                          if line.strip() and not line.startswith("#")
                          and len(line) > 10][:2]
            core_text = " ".join(core_points) if core_points else title

            prompt = (
                f"Create a minimalist, modern illustration for a social media post "
                f'about: "{title}". The concept: {core_text[:200]}\n\n'
                "Requirements:\n"
                "- Modern, clean design suitable for Chinese social media (Xiaohongshu)\n"
                "- Warm, inviting color palette\n"
                "- Abstract or conceptual illustration, not text\n"
                "- 16:9 or 4:3 aspect ratio\n"
                "- High quality, visually appealing\n"
                "- No text or words in the image"
            )

            response = openai.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )

            image_url = response.data[0].url
            import urllib.request
            urllib.request.urlretrieve(image_url, output_path)
            logger.info("DALL-E image generated: %s", output_path)
            return output_path

        except Exception as e:
            logger.warning("DALL-E generation failed: %s", e)
            return None

    def _generate_ffmpeg_cover(self, title: str, output_path: str) -> Optional[str]:
        """使用 FFmpeg 生成文字封面"""
        # 清理标题中的特殊字符
        import re
        clean_title = re.sub(r"[^\w\s\-:,，。！？]", "", title)[:40]
        if not clean_title.strip():
            clean_title = "Content"

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 用 ffmpeg drawtext 渲染中文
        fonts = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]
        font_path = None
        for f in fonts:
            if Path(f).exists():
                font_path = f
                break

        if font_path:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=#667eea:s=1080x1920:d=1",
                "-vf",
                f"drawtext=text='{clean_title}':"
                f"fontfile={font_path}:"
                f"fontcolor=white:fontsize=48:"
                f"x=(w-text_w)/2:y=(h-text_h)/2",
                "-frames:v", "1",
                str(out),
            ]
        else:
            # 无中文字体时的回退
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=#667eea:s=1080x1920:d=1",
                "-frames:v", "1",
                str(out),
            ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0:
                logger.info("FFmpeg cover generated: %s", output_path)
                return output_path
            else:
                logger.warning("FFmpeg cover failed: %s", result.stderr[:200])
                return None
        except Exception as e:
            logger.warning("FFmpeg cover error: %s", e)
            return None


def quick_generate(title: str, body: str = "", output_path: str = "") -> Optional[str]:
    """快速生成图片（无需实例化 ImageGenerator）"""
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "")
    gen = ImageGenerator(openai_api_key=api_key)
    return gen.generate(title, body, output_path)
