#!/usr/bin/env python3
"""
图片生成模块 - 使用 DALL-E 3 生成有意义的内容图片
"""

import os
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Optional
import openai

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

class ImageGenerator:
    """AI 图片生成器"""
    
    def __init__(self):
        self.config = load_config()
        self.openai_config = self.config.get('openai', {})
        self.image_config = self.config.get('image_generation', {})
        
        # 设置 OpenAI API
        api_key = self.openai_config.get('api_key') or os.environ.get('OPENAI_API_KEY')
        if api_key:
            openai.api_key = api_key
    
    def is_configured(self) -> bool:
        """检查是否配置了 DALL-E"""
        api_key = self.openai_config.get('api_key') or os.environ.get('OPENAI_API_KEY')
        return bool(api_key)
    
    async def generate_image(self, content_id: str, title: str, content: str, output_path: str) -> Optional[str]:
        """
        使用 DALL-E 生成图片
        
        Args:
            content_id: 内容 ID
            title: 标题
            content: 正文内容
            output_path: 输出路径
            
        Returns:
            str: 生成的图片路径，失败返回 None
        """
        if not self.is_configured():
            print(f"⚠️ 未配置 OpenAI API Key，无法生成 AI 图片")
            return None
        
        # 构建 prompt
        # 提取核心观点
        lines = content.split('\n')
        core_points = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('---'):
                # 取前几个关键句子
                if len(line) > 10:
                    core_points.append(line)
                    if len(core_points) >= 3:
                        break
        
        core_text = ' '.join(core_points[:2]) if core_points else title
        
        # DALL-E prompt - 要求生成有意义的插图
        prompt = f"""Create a minimalist, modern illustration for a social media post about: "{title}". 

The concept: {core_text[:200]}

Requirements:
- Modern, clean design suitable for Chinese social media (Xiaohongshu)
- Warm, inviting color palette
- Abstract or conceptual illustration, not text
- 16:9 or 4:3 aspect ratio
- High quality, visually appealing
- No text or words in the image"""

        try:
            # 调用 DALL-E 3
            response = openai.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            
            image_url = response.data[0].url
            
            # 下载图片
            import urllib.request
            urllib.request.urlretrieve(image_url, output_path)
            
            print(f"✅ DALL-E 图片生成成功: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"❌ DALL-E 图片生成失败: {e}")
            return None
    
    def generate_placeholder(self, content_id: str, title: str, output_path: str) -> str:
        """
        生成占位符图片（当 DALL-E 不可用时）
        使用 text overlay 在彩色背景上
        """
        # 使用 ffmpeg 生成带文字的图片
        # 提取标题中的关键词
        keywords = title.replace('#', '').replace(':', '').strip()[:30]
        
        # 转义特殊字符
        escaped_title = keywords.replace("'", "\\'").replace('"', '\\"')
        
        # 使用中文字体和彩色背景
        cmd = [
            'ffmpeg', '-y',
            '-f', 'lavfi', '-i', f'color=c=#667eea:s=1080x1920:d=1',
            '-vf', f"drawtext=text='{escaped_title}':fontcolor=white:fontsize=48:font=/System/Library/Fonts/PingFang.ttc:x=(w-text_w)/2:y=(h-text_h)/2",
            '-frames:v', '1',
            output_path
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
            return output_path
        except Exception as e:
            print(f"❌ 占位符生成失败: {e}")
            return None


async def main():
    """测试图片生成"""
    import sys
    
    if len(sys.argv) > 1:
        content_id = sys.argv[1]
    else:
        content_id = "012"
    
    ig = ImageGenerator()
    
    # 读取内容
    content_file = Path(__file__).parent.parent / "processing" / f"{content_id}.md"
    if not content_file.exists():
        print(f"❌ 内容文件不存在: {content_file}")
        return
    
    with open(content_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取标题
    title = content.split('\n')[0].replace('# ', '').strip()
    
    output_path = Path(__file__).parent.parent / "input" / f"{content_id}_cover.jpg"
    
    # 尝试 DALL-E 生成
    if ig.is_configured():
        result = await ig.generate_image(content_id, title, content, str(output_path))
    else:
        print("⚠️ DALL-E 未配置，使用占位符...")
        result = ig.generate_placeholder(content_id, title, str(output_path))
    
    if result:
        print(f"✅ 图片已生成: {result}")
    else:
        print("❌ 图片生成失败")


if __name__ == "__main__":
    asyncio.run(main())
