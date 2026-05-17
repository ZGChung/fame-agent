"""
Content Pipeline — 视频生成模块

支持 FFmpeg 幻灯片视频生成、Ken Burns 特效、TTS 配音、背景音乐。
独立模块，不依赖 pipeline 其他部分。
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 常用中文字体路径（macOS）
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]


class VideoGenerator:
    """
    视频生成器。
    
    核心功能：
    - 从图片生成幻灯片视频
    - Ken Burns 动态缩放/平移效果
    - TTS 配音（ElevenLabs / macOS say）
    - 背景音乐叠加
    - 字幕添加
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """检查 ffmpeg 是否可用"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                logger.info("FFmpeg available: %s", result.stdout.split("\n")[0])
            else:
                raise RuntimeError("ffmpeg not found")
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg is not installed. Install: brew install ffmpeg"
            )

    # --- 幻灯片视频 ---

    async def slideshow(
        self,
        images: list[str],
        output_path: str = "",
        duration_per_image: float = 3.0,
        resolution: str = "1080x1920",
        transition: str = "fade",
    ) -> str:
        """
        从多张图片生成幻灯片视频。

        Args:
            images: 图片路径列表
            output_path: 输出路径（默认自动生成）
            duration_per_image: 每张图片时长（秒）
            resolution: 视频分辨率
            transition: 转场效果

        Returns:
            生成的视频文件路径
        """
        if not images:
            raise ValueError("Need at least 1 image")

        if not output_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"/tmp/content_pipeline_{ts}.mp4"

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if len(images) == 1:
            return await self._ken_burns_single(
                images[0], output_path, duration_per_image, resolution
            )

        # 多图：生成片段后合并
        return await self._multi_image_slideshow(
            images, output_path, duration_per_image, resolution
        )

    async def _multi_image_slideshow(
        self, images: list[str], output_path: str,
        duration: float, resolution: str,
    ) -> str:
        """多图幻灯片"""
        out = Path(output_path)
        temp_dir = out.parent / f"temp_{out.stem}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 生成每个片段
            temp_videos = []
            for i, img in enumerate(images):
                temp_out = temp_dir / f"seg_{i:03d}.mp4"
                cmd = self._build_single_clip_cmd(img, str(temp_out), duration, resolution)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    raise RuntimeError(f"Segment {i} failed: {result.stderr[:200]}")
                temp_videos.append(str(temp_out))

            # 合并
            concat_file = temp_dir / "concat.txt"
            concat_file.write_text(
                "\n".join(f"file '{v}'" for v in temp_videos) + "\n",
                encoding="utf-8",
            )

            merge_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                output_path,
            ]
            result = subprocess.run(merge_cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise RuntimeError(f"Merge failed: {result.stderr[:200]}")

            logger.info("Slideshow generated: %s", output_path)
            return output_path

        finally:
            # 清理临时文件
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    def _build_single_clip_cmd(
        self, image: str, output: str, duration: float, resolution: str
    ) -> list[str]:
        """构建单图视频片段命令"""
        w, h = resolution.split("x") if "x" in resolution else ("1080", "1920")
        scale_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        )
        return [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", scale_filter,
            "-r", "30",
            output,
        ]

    # --- Ken Burns 特效 ---

    async def _ken_burns_single(
        self, image: str, output_path: str,
        duration: float, resolution: str,
        zoom_direction: str = "in",
    ) -> str:
        """单图 Ken Burns 效果"""
        w, h = resolution.split("x") if "x" in resolution else ("1080", "1920")
        base_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        )
        frames = int(duration * 30)

        if zoom_direction == "in":
            vf = f"{base_filter},zoompan=z=1.2:x=0:y=0:d={frames}:s={w}x{h}"
        elif zoom_direction == "out":
            vf = f"{base_filter},zoompan=z=0.8:x=0:y=0:d={frames}:s={w}x{h}"
        elif zoom_direction == "pan":
            vf = f"{base_filter},zoompan=z=1.15:x=iw/4:y=ih/4:d={frames}:s={w}x{h}"
        else:
            vf = base_filter

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-vf", vf,
            "-r", "30",
            "-preset", "fast",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.warning("Ken Burns failed, retrying static: %s", result.stderr[:100])
            # 回退到静态
            return await self._static_single(image, output_path, duration, resolution)

        logger.info("Ken Burns video: %s", output_path)
        return output_path

    async def _static_single(
        self, image: str, output_path: str, duration: float, resolution: str
    ) -> str:
        """静态单图视频"""
        cmd = self._build_single_clip_cmd(image, output_path, duration, resolution)
        subprocess.run(cmd, capture_output=True, timeout=60)
        return output_path

    # --- TTS 配音 ---

    async def add_tts(
        self,
        video_path: str,
        text: str,
        output_path: str = "",
        provider: str = "elevenlabs",
        voice_id: str = "rachel",
    ) -> str:
        """
        为视频添加 TTS 配音。

        Args:
            video_path: 输入视频路径
            text: 配音文字
            output_path: 输出路径
            provider: TTS 服务（elevenlabs / say）
            voice_id: 音色 ID
        """
        if not output_path:
            output_path = video_path.replace(".mp4", "_with_tts.mp4")

        # 生成音频
        audio_path = await self._generate_tts_audio(text, provider, voice_id)
        if not audio_path:
            logger.warning("TTS generation failed, returning original video")
            return video_path

        # 合成到视频
        return await self._merge_audio(video_path, audio_path, output_path)

    async def _generate_tts_audio(
        self, text: str, provider: str, voice_id: str
    ) -> Optional[str]:
        """生成 TTS 音频文件"""
        audio_path = f"/tmp/tts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"

        if provider == "elevenlabs":
            return await self._elevenlabs_tts(text, voice_id, audio_path)
        elif provider == "say":
            return await self._macos_say_tts(text, audio_path)
        else:
            logger.warning("Unknown TTS provider: %s, using macOS 'say'", provider)
            return await self._macos_say_tts(text, audio_path)

    async def _elevenlabs_tts(self, text: str, voice_id: str, output_path: str) -> Optional[str]:
        """ElevenLabs TTS"""
        try:
            import httpx
            api_key = (
                self.config.get("api_keys", {}).get("elevenlabs")
                or self._get_env("ELEVENLABS_API_KEY")
            )
            if not api_key:
                logger.warning("ElevenLabs API key not configured")
                return None

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
            }

            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    Path(output_path).write_bytes(response.content)
                    logger.info("ElevenLabs TTS generated: %s", output_path)
                    return output_path
                else:
                    logger.warning(
                        "ElevenLabs TTS failed: %s %s",
                        response.status_code, response.text[:200]
                    )
                    return None

        except Exception as e:
            logger.warning("ElevenLabs TTS error: %s", e)
            return None

    async def _macos_say_tts(self, text: str, output_path: str) -> Optional[str]:
        """macOS say 命令 TTS（离线备选）"""
        try:
            # 只取前 500 字符避免超长
            safe_text = text[:500].replace('"', '\\"')
            cmd = [
                "say", "-o", output_path,
                "--data-format=LEI16@22050",
                safe_text,
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            if result.returncode == 0 and Path(output_path).exists():
                logger.info("macOS say TTS generated: %s", output_path)
                return output_path
            return None
        except Exception as e:
            logger.warning("macOS say TTS error: %s", e)
            return None

    # --- 音频合并 ---

    async def _merge_audio(self, video_path: str, audio_path: str, output_path: str) -> str:
        """将音频合并到视频"""
        # 检查视频是否有音频轨道
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=10,
        )
        has_audio = bool(probe.stdout.strip())

        if not has_audio:
            # 视频无音频 -> 直接叠加
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                output_path,
            ]
        else:
            # 视频有音频 -> 混音（降低原音音量）
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-filter_complex",
                "[1:a]volume=1.0[voice];[0:a][voice]amix=inputs=2:duration=first[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-shortest",
                output_path,
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Audio merge failed: {result.stderr[:200]}")

        logger.info("Audio merged: %s", output_path)
        return output_path

    # --- 背景音乐 ---

    async def add_background_music(
        self,
        video_path: str,
        music_path: str,
        output_path: str = "",
        volume: float = 0.15,
    ) -> str:
        """
        添加背景音乐（自动嵌入淡入淡出）。
        
        Args:
            video_path: 输入视频
            music_path: 音乐文件
            output_path: 输出路径
            volume: 音乐音量（0.0-1.0）
        """
        if not output_path:
            output_path = video_path.replace(".mp4", "_with_music.mp4")

        # 获取视频时长
        duration = self._get_duration(video_path)

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex",
            (
                f"[1:a]volume={volume},"
                f"afade=t=in:st=0:d=3,"
                f"afade=t=out:st={max(0, duration - 3)}:d=3[music];"
                f"[0:a][music]amix=inputs=2:duration=first[aout]"
            ),
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-shortest",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Background music failed: {result.stderr[:200]}")

        logger.info("Background music added: %s", output_path)
        return output_path

    def _get_duration(self, video_path: str) -> float:
        """获取视频时长（秒）"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip() or 30)

    def _get_env(self, name: str) -> str:
        """获取环境变量"""
        import os
        return os.environ.get(name, "")


# --- 便捷函数 ---

async def quick_slideshow(images: list[str], **kwargs) -> str:
    """快速生成幻灯片视频"""
    vg = VideoGenerator()
    return await vg.slideshow(images, **kwargs)
