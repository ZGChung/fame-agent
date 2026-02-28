#!/usr/bin/env python3
"""
视频生成模块
支持多种 AI 视频生成服务

使用方式:
1. 配置视频生成服务 API
2. 调用 generate_video() 生成视频
3. 集成到 pipeline

支持的视频生成方式:
- Runway ML (text to video, image to video)
- Pika Labs (text to video, image to video)
- Luma Dream Machine (image to video)
- 本地 ffmpeg (图片生成视频)
"""

import os
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# 配置
CONFIG_FILE = Path(__file__).parent.parent / "config.json"

def load_config() -> dict:
    """加载配置"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


class VideoGenerator:
    """视频生成器"""
    
    def __init__(self):
        self.config = load_config()
        self.video_config = self.config.get('video', {})
    
    def is_configured(self) -> bool:
        """检查是否配置了任意视频服务"""
        return bool(
            self.video_config.get('runway_api_key') or
            self.video_config.get('pika_api_key') or
            self.video_config.get('luma_api_key') or
            self.video_config.get('heygen_api_key')
        )
    
    async def generate_from_images(
        self,
        images: List[str],
        output_path: str = None,
        duration_per_image: float = 3.0,
        transition: str = "fade"
    ) -> str:
        """
        从图片生成视频（幻灯片）
        
        Args:
            images: 图片路径列表
            output_path: 输出视频路径
            duration_per_image: 每张图片持续时间（秒）
            transition: 转场效果 (fade, slide, none)
        
        Returns:
            str: 生成视频的路径
        """
        if not images:
            raise ValueError("需要提供至少一张图片")
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"output/{timestamp}_video.mp4"
        
        # 使用 ffmpeg 生成视频
        success = await self._ffmpeg_slideshow(
            images, output_path, duration_per_image, transition
        )
        
        if success:
            return output_path
        raise RuntimeError("视频生成失败")
    
    async def _ffmpeg_slideshow(
        self,
        images: List[str],
        output_path: str,
        duration: float,
        transition: str
    ) -> bool:
        """使用 ffmpeg 生成幻灯片视频"""
        
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 如果只有一张图片，使用 Ken Burns 效果
        if len(images) == 1:
            # Ken Burns: slow zoom in
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1',
                '-i', images[0],
                '-c:v', 'libx264',
                '-t', str(duration),
                '-pix_fmt', 'yuv420p',
                '-vf', f'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,zoompan=z=\'min(zoom+0.001,1.5)\':d={int(duration*25)}:s=1080x1920',
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0
        
        # 多张图片：创建片段后合并
        try:
            temp_videos = []
            # 使用绝对路径确保正确
            output_dir = Path(output_path).resolve().parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for i, img in enumerate(images):
                img_path = Path(img).resolve()
                temp_out = output_dir / f"temp_{i}.mp4"
                cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-i', str(img_path),
                    '-c:v', 'libx264',
                    '-t', str(duration),
                    '-pix_fmt', 'yuv420p',
                    '-vf', f'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2',
                    '-r', '30',
                    str(temp_out)
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    print(f"创建片段失败: {result.stderr[:200]}")
                    return False
                temp_videos.append(str(temp_out))
            
            # 合并 - 使用 concat demuxer 方式
            concat_file = output_dir / "concat.txt"
            with open(concat_file, 'w') as f:
                for v in temp_videos:
                    f.write(f"file '{v}'\n")
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '128k',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            # 清理
            for v in temp_videos:
                Path(v).unlink()
            concat_file.unlink()
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"FFmpeg 生成失败: {e}")
            return False
    
    async def generate_text_to_video(
        self,
        prompt: str,
        service: str = "runway",
        output_path: str = None
    ) -> str:
        """
        文字生成视频
        
        Args:
            prompt: 视频描述
            service: 服务商 (runway, pika, luma, seedance)
            output_path: 输出路径
        
        Returns:
            str: 视频路径
        """
        if service == "runway":
            return await self._runway_generate(prompt, output_path)
        elif service == "pika":
            return await self._pika_generate(prompt, output_path)
        elif service == "luma":
            return await self._luma_generate(prompt, output_path)
        elif service == "seedance":
            return await self._seedance_generate(prompt, output_path)
        else:
            raise ValueError(f"不支持的服务: {service}")
    
    async def _runway_generate(self, prompt: str, output_path: str) -> str:
        """Runway ML API"""
        api_key = self.video_config.get('runway_api_key')
        if not api_key:
            raise ValueError("需要配置 Runway API Key")
        
        # TODO: 实现 Runway API 调用
        # API: https://api.runwayml.com/v1/generation
        raise NotImplementedError("Runway API 集成开发中")
    
    async def _pika_generate(self, prompt: str, output_path: str) -> str:
        """Pika Labs API"""
        api_key = self.video_config.get('pika_api_key')
        if not api_key:
            raise ValueError("需要配置 Pika API Key")
        
        # TODO: 实现 Pika API 调用
        raise NotImplementedError("Pika API 集成开发中")
    
    async def _luma_generate(self, prompt: str, output_path: str) -> str:
        """Luma Dream Machine API"""
        api_key = self.video_config.get('luma_api_key')
        if not api_key:
            raise ValueError("需要配置 Luma API Key")
        
        # TODO: 实现 Luma API 调用
        raise NotImplementedError("Luma API 集成开发中")
    
    async def _seedance_generate(self, prompt: str, output_path: str) -> str:
        """
        Seedance 2.0 API
        
        注意: Seedance 2.0 可能尚未公开发布，等待官方 API
        """
        api_key = self.video_config.get('seedance_api_key')
        if not api_key:
            # 如果没有 API Key，使用本地生成作为备选
            print("⚠️ Seedance API Key 未配置，使用本地视频生成")
            # 返回空字符串让调用方使用本地生成
            return ""
        
        # TODO: Seedance 2.0 API 集成
        # 等待官方发布后实现
        raise NotImplementedError("Seedance 2.0 API 集成开发中 - 等待官方发布")
    
    async def add_audio(
        self,
        video_path: str,
        audio_path: str = None,
        tts_text: str = None,
        output_path: str = None
    ) -> str:
        """
        为视频添加音频
        
        Args:
            video_path: 视频路径
            audio_path: 音频文件路径 (可选)
            tts_text: 要转语音的文字 (可选)
            output_path: 输出路径
        
        Returns:
            str: 带音频的视频路径
        """
        if not output_path:
            output_path = video_path.replace('.mp4', '_with_audio.mp4')
        
        # 如果提供了 tts，使用 TTS 生成音频
        if tts_text and not audio_path:
            audio_path = await self._generate_tts(tts_text)
            if not audio_path:
                raise ValueError("TTS 生成失败")
        
        if not audio_path:
            raise ValueError("需要提供音频文件或 TTS 文字")
        
        # 合并视频和音频
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-shortest',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return output_path
        raise RuntimeError(f"音频合并失败: {result.stderr}")
    
    async def _generate_tts(self, text: str, output_path: str = None, voice: str = None) -> str:
        """生成 TTS 音频
        
        优先使用 ElevenLabs（如果配置），否则使用 macOS say 命令
        
        Args:
            text: 要转换的文字
            output_path: 输出路径
            voice: 语音名称 (默认自动选择中/英文)
        """
        # 优先使用 ElevenLabs
        tts_config = self.video_config.get('tts', {})
        elevenlabs_key = tts_config.get('api_key') or os.getenv('ELEVENLABS_API_KEY')
        
        if elevenlabs_key:
            return await self._generate_elevenlabs(text, output_path, voice, elevenlabs_key)
        
        # 回退到 macOS say 命令
        return await self._generate_tts_say(text, output_path, voice)
    
    async def _generate_elevenlabs(
        self, 
        text: str, 
        output_path: str = None, 
        voice: str = None,
        api_key: str = None
    ) -> str:
        """使用 ElevenLabs 生成 TTS"""
        import urllib.request
        import urllib.parse
        
        tts_config = self.video_config.get('tts', {})
        voice_id = voice or tts_config.get('voice_id', 'rachel')
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"output/{timestamp}_tts.mp3"
        
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # ElevenLabs API
        url = f"https://api.elevenlabs.io/v1/text_to_speech/{voice_id}"
        
        headers = {
            'Accept': 'audio/mpeg',
            'Content-Type': 'application/json',
            'xi-api-key': api_key
        }
        
        data = json.dumps({
            'text': text,
            'model_id': 'eleven_monolingual_v1',
            'voice_settings': {
                'stability': 0.5,
                'similarity_boost': 0.75
            }
        }).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                with open(output_path, 'wb') as f:
                    f.write(response.read())
            return output_path
        except Exception as e:
            raise RuntimeError(f"ElevenLabs TTS 失败: {e}")
    
    async def _generate_tts_say(self, text: str, output_path: str = None, voice: str = None) -> str:
        """使用 macOS say 命令生成 TTS
        
        Args:
            text: 要转换的文字
            output_path: 输出路径
            voice: 语音名称 (默认自动选择中/英文)
        """
        # 自动选择语音
        if not voice:
            # 简单的中英文检测
            if any('\u4e00' <= c <= '\u9fff' for c in text):
                voice = "Tingting"  # 中文女声
            else:
                voice = "Daniel"  # 英文字音
        
        # 先生成 aiff
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        aiff_path = f"output/{timestamp}_tts.aiff"
        
        # 输出路径
        if output_path and output_path.endswith('.mp3'):
            mp3_path = output_path
        else:
            mp3_path = f"output/{timestamp}_tts.mp3"
        
        output_dir = Path(aiff_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用 say 命令生成音频 (使用 -v 指定语音)
        cmd = ['say', '-v', voice, text, '-o', aiff_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            # 备用：尝试默认语音
            cmd = ['say', text, '-o', aiff_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"TTS 生成失败: {result.stderr}")
        
        # 转换格式为 MP3
        cmd = [
            'ffmpeg', '-y',
            '-i', aiff_path,
            '-acodec', 'libmp3lame',
            '-ar', '22050',
            mp3_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # 删除 aiff
        Path(aiff_path).unlink()
        
        if result.returncode == 0:
            return mp3_path
        
        raise RuntimeError(f"MP3 转换失败: {result.stderr}")


# 便捷函数
async def quick_video(
    images: List[str],
    output_path: str = None,
    with_tts: str = None
) -> str:
    """快速生成视频"""
    generator = VideoGenerator()
    
    # 生成视频
    video_path = await generator.generate_from_images(images, output_path)
    
    # 添加音频
    if with_tts:
        video_path = await generator.add_audio(video_path, tts_text=with_tts)
    
    return video_path


if __name__ == "__main__":
    import sys
    
    gen = VideoGenerator()
    print("🎬 视频生成器")
    print(f"配置状态: {'✅ 已配置' if gen.is_configured() else '❌ 未配置'}")
    
    if len(sys.argv) > 1:
        # 测试生成
        images = sys.argv[1:]
        print(f"从 {len(images)} 张图片生成视频...")
        
        async def test():
            path = await gen.generate_from_images(images)
            print(f"✅ 视频生成成功: {path}")
        
        asyncio.run(test())
