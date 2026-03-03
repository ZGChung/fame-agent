#!/usr/bin/env python3
"""
Pipeline Scheduler - 自动化调度器
自动处理内容的完整流程：图片 -> 视频 -> 发布
"""

import os
import time
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
import subprocess

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

class PipelineScheduler:
    """自动化流水线调度器"""
    
    def __init__(self):
        self.folders = self._get_folders()
        self.config = self._load_config()
        self.log_file = BASE_DIR / "scheduler.log"
        
    def _get_folders(self) -> dict:
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
        return {
            'input': BASE_DIR / config.get('input_folder', 'input'),
            'processing': BASE_DIR / config.get('processing_folder', 'processing'),
            'output': BASE_DIR / config.get('output_folder', 'output'),
            'queue': BASE_DIR / config.get('queue_folder', 'queue'),
        }
    
    def _load_config(self) -> dict:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    
    def log(self, message: str):
        """写入日志"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"
        with open(self.log_file, 'a') as f:
            f.write(log_line)
        print(log_line.strip())
    
    def get_content_ids(self, folder: str) -> set:
        """获取文件夹中的内容 ID 集合"""
        folder_path = self.folders.get(folder)
        if not folder_path or not folder_path.exists():
            return set()
        return {f.stem for f in folder_path.glob("*.md")}
    
    def get_images(self, folder: str) -> set:
        """获取文件夹中的图片 ID 集合"""
        folder_path = self.folders.get(folder)
        if not folder_path or not folder_path.exists():
            return set()
        return {f.stem.replace('_cover', '').replace('_', '') 
                for f in folder_path.glob("*cover.jpg")}
    
    def generate_cover_image(self, content_id: str) -> bool:
        """使用 AI 生成有意义的封面图片"""
        # 提取纯数字 ID
        img_id = self.extract_id(content_id)
        
        # 检查图片是否已存在
        output_path = self.folders['input'] / f"{content_id}_cover.jpg"
        
        # 读取内容生成带文字的封面
        content_file = self.folders['processing'] / f"{content_id}.md"
        if not content_file.exists():
            # 尝试纯 ID 文件名
            content_file = self.folders['processing'] / f"{img_id}.md"
        
        # 提取标题
        title = "内容图片"
        if content_file.exists():
            try:
                with open(content_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('# '):
                        title = line[2:].strip()
                        break
            except:
                pass
        
        # 使用带文字的封面
        self.log(f"🎬 生成文字封面: {title[:20]}")
        return self._generate_text_cover(content_id, title, output_path)
    
    def _generate_text_cover(self, content_id: str, title: str, output_path: Path) -> bool:
        """生成带标题的图片封面（英文/数字标题）"""
        # 清理标题，只保留 ASCII 字符
        import re
        clean_title = re.sub(r'[^\x00-\x7F]+', '', title)[:30]
        if not clean_title:
            clean_title = f"#{content_id}"
        
        # 使用默认字体（不指定中文字体）
        cmd = [
            'ffmpeg', '-y',
            '-f', 'lavfi', '-i', 'color=c=#1a1a2e:s=1080x1920:d=1',
            '-vf', f"drawtext=text='{clean_title}':fontcolor=white:fontsize=50:x=(w-text_w)/2:y=(h-text_h)/2",
            '-frames:v', '1',
            str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0:
                self.log(f"✅ 文字封面生成: {content_id}")
                return True
            else:
                self.log(f"⚠️ 文字封面失败，尝试渐变...")
                return self._generate_fallback_cover(content_id, output_path)
        except Exception as e:
            return self._generate_fallback_cover(content_id, output_path)
    
    def _generate_fallback_cover(self, content_id: str, output_path: Path) -> bool:
        """生成带渐变效果的彩色背景封面"""
        # 渐变色彩方案
        gradients = [
            'linear_gradient=#667eea:#764ba2',  # 紫蓝渐变
            'linear_gradient=#f093fb:#f5576c',  # 粉红渐变
            'linear_gradient=#4facfe:#00f2fe',  # 蓝色渐变
            'linear_gradient=#43e97b:#38f9d7',  # 绿色渐变
            'linear_gradient=#fa709a:#fee140',  # 红黄渐变
            'linear_gradient=#a8edea:#fed6e3',  # 浅绿粉渐变
            'linear_gradient=#ff9a9e:#fecfef',  # 粉色渐变
            'linear_gradient=#ffecd2:#fcb69f',  # 橙黄渐变
            'linear_gradient=#c471f5:#fa71cd',  # 紫色渐变
            'linear_gradient=#30cfd0:#330867',  # 青紫渐变
        ]
        
        try:
            idx = int(content_id.replace('00', '').replace('_', '').strip() or '0') % len(gradients)
        except:
            idx = 0
        
        gradient = gradients[idx]
        
        # 使用 FFmpeg 渐变生成（简化版：纯色 + 暗角效果）
        cmd = [
            'ffmpeg', '-y',
            '-f', 'lavfi', '-i', f'color=c=#1a1a2e:s=1080x1920:d=1',
            '-vf', 'vignette=angle=0.5',
            '-frames:v', '1',
            str(output_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode == 0:
                self.log(f"✅ 渐变封面生成: {content_id}")
                return True
        except:
            pass
        
        # 最简备选：纯色
        cmd = [
            'ffmpeg', '-y',
            '-f', 'lavfi', '-i', 'color=c=#2d3436:s=1080x1920:d=1',
            '-frames:v', '1',
            str(output_path)
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, timeout=10)
            return True
        except:
            return False
    
    def extract_id(self, content_id: str) -> str:
        """提取内容 ID 数字部分"""
        # 012_two_types -> 012
        # 012 -> 012
        if '_' in content_id:
            return content_id.split('_')[0]
        return content_id
    
    def generate_video(self, content_id: str) -> bool:
        """生成视频"""
        # 提取纯数字 ID
        video_id = self.extract_id(content_id)
        
        # 检查图片是否存在
        cover_path = self.folders['input'] / f"{content_id}_cover.jpg"
        if not cover_path.exists():
            cover_path = self.folders['input'] / f"{video_id}_cover.jpg"
        
        if not cover_path.exists():
            self.log(f"⚠️ No cover for {content_id}, generating...")
            self.generate_cover_image(content_id)
        
        # 运行视频生成命令
        cmd = [
            'python3', str(BASE_DIR / 'pipeline.py'),
            'video', 'generate-with-tts', video_id
        ]
        
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=120,
                cwd=str(BASE_DIR)
            )
            if result.returncode == 0:
                self.log(f"✅ Video generated for {content_id}")
                return True
            else:
                self.log(f"❌ Video generation failed: {result.stderr}")
                return False
        except Exception as e:
            self.log(f"❌ Error generating video: {e}")
            return False
    
    def check_and_process(self) -> dict:
        """检查并处理内容 - 自动化核心"""
        results = {
            'images_generated': 0,
            'videos_generated': 0,
            'errors': []
        }
        
        # 1. 检查 processing 文件夹中需要图片的内容
        processing_ids = self.get_content_ids('processing')
        input_images = self.get_images('input')
        
        for content_id in processing_ids:
            # 跳过已有图片的
            if content_id in input_images:
                continue
            
            # 生成图片
            if self.generate_cover_image(content_id):
                results['images_generated'] += 1
        
        # 2. 检查需要生成视频的内容
        output_videos = set()
        for f in self.folders['output'].glob("*_video_with_audio.mp4"):
            # 提取 ID: 012_video_with_audio -> 012
            stem = f.stem.replace('_video_with_audio', '')
            # 处理 005_attention -> 005
            if '_' in stem:
                stem = stem.split('_')[0]
            output_videos.add(stem)
        
        for content_id in processing_ids:
            if content_id in output_videos:
                continue
            
            # 生成视频
            if self.generate_video(content_id):
                results['videos_generated'] += 1
            else:
                results['errors'].append(f"{content_id}: video generation failed")
        
        return results
    
    def run_once(self):
        """运行一次自动化处理"""
        self.log("=" * 50)
        self.log("🚀 Starting automated pipeline check...")
        
        results = self.check_and_process()
        
        self.log(f"📊 Results: {results['images_generated']} images, {results['videos_generated']} videos")
        
        if results['errors']:
            for err in results['errors']:
                self.log(f"  ❌ {err}")
        
        # 如果有视频准备好，可以触发发布
        if results['videos_generated'] > 0:
            self.log("✅ 视频已生成，可发布到小红书")
        
        return results
    
    def run_continuous(self, interval: int = 300):
        """持续运行调度器"""
        self.log(f"🔄 Starting continuous scheduler (interval: {interval}s)")
        
        while True:
            try:
                self.run_once()
            except Exception as e:
                self.log(f"❌ Scheduler error: {e}")
            
            time.sleep(interval)
    
    async def publish_to_xiaohongshu(self, content_id: str, video_path: str = None) -> bool:
        """发布内容到小红书"""
        try:
            from publishers.xiaohongshu import XiaohongshuPublisher
            
            # 读取内容
            content_file = self.folders['processing'] / f"{content_id}.md"
            if not content_file.exists():
                self.log(f"❌ 内容文件不存在: {content_id}")
                return False
            
            with open(content_file, 'r') as f:
                content = f.read()
            
            # 提取标题和正文
            title = content.split('\n')[0].replace('# ', '').strip()
            body = '\n'.join(content.split('\n')[2:])  # 跳过第一行标题和---分隔符
            
            # 获取图片
            images = []
            if video_path and os.path.exists(video_path):
                images = [video_path]
            else:
                cover_path = self.folders['input'] / f"{content_id}_cover.jpg"
                if cover_path.exists():
                    images = [str(cover_path)]
            
            # 发布
            publisher = XiaohongshuPublisher()
            await publisher.init_browser(headless=True)
            await publisher.load_cookies()
            
            result = await publisher.publish(title, body, images)
            
            await publisher.close()
            
            if result:
                self.log(f"✅ 发布成功: {content_id}")
                return True
            else:
                self.log(f"❌ 发布失败: {content_id}")
                return False
                
        except Exception as e:
            self.log(f"❌ 发布错误: {e}")
            return False


def main():
    import sys
    
    scheduler = PipelineScheduler()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--continuous':
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        scheduler.run_continuous(interval)
    else:
        scheduler.run_once()


if __name__ == "__main__":
    main()
