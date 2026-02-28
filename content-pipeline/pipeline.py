#!/usr/bin/env python3
"""
Content Pipeline - 核心模块
负责内容从输入到发布的完整流程
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# 配置
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

def load_config() -> dict:
    """加载配置文件"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_folders() -> dict:
    """获取各文件夹路径"""
    config = load_config()
    return {
        'input': BASE_DIR / config.get('input_folder', 'input'),
        'processing': BASE_DIR / config.get('processing_folder', 'processing'),
        'output': BASE_DIR / config.get('output_folder', 'output'),
        'queue': BASE_DIR / config.get('queue_folder', 'queue'),
    }

def list_content(folder: str, status_filter: Optional[str] = None) -> list:
    """列出指定文件夹的内容"""
    folders = get_folders()
    folder_path = folders.get(folder)
    
    if not folder_path or not folder_path.exists():
        return []
    
    contents = []
    for f in folder_path.glob("*.md"):
        content = parse_content_file(f)
        if status_filter is None or content.get('status') == status_filter:
            contents.append(content)
    
    return sorted(contents, key=lambda x: x.get('created', ''))

def parse_content_file(file_path: Path) -> dict:
    """解析内容文件"""
    content = {
        'id': file_path.stem,
        'file': str(file_path),
        'title': '',
        'status': 'idea',
        'platforms': [],
        'created': datetime.now().strftime('%Y-%m-%d')
    }
    
    # 简单的 frontmatter 解析
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        in_frontmatter = False
        body_lines = []
        
        for line in lines:
            if line.strip() == '---':
                in_frontmatter = not in_frontmatter
                continue
            if not in_frontmatter:
                body_lines.append(line)
                if line.startswith('# ') and not content['title']:
                    content['title'] = line[2:].strip()
        
        content['body'] = ''.join(body_lines)
    
    return content

def move_content(content_id: str, from_folder: str, to_folder: str) -> bool:
    """移动内容到目标文件夹"""
    folders = get_folders()
    source = folders[from_folder] / f"{content_id}.md"
    dest = folders[to_folder] / f"{content_id}.md"
    
    if source.exists():
        source.rename(dest)
        return True
    return False

def get_next_id() -> str:
    """获取下一个内容 ID"""
    folders = get_folders()
    all_ids = []
    
    for folder in ['input', 'processing', 'output', 'queue']:
        folder_path = folders.get(folder)
        if folder_path and folder_path.exists():
            for f in folder_path.glob("*.md"):
                all_ids.append(f.stem)
    
    if not all_ids:
        return "001"
    
    # 提取数字并找最大值
    nums = [int(x.split('_')[0]) for x in all_ids if x.split('_')[0].isdigit()]
    return f"{max(nums) + 1:03d}" if nums else "001"

def create_content(title: str, platforms: list, body: str) -> str:
    """创建新内容"""
    content_id = get_next_id()
    folders = get_folders()
    
    content = f"""---
id: {content_id}
title: "{title}"
status: drafting
platforms: {json.dumps(platforms)}
created: "{datetime.now().strftime('%Y-%m-%d')}"
---

# {title}

{body}
"""
    
    file_path = folders['input'] / f"{content_id}_{title[:20]}.md"
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return content_id

def update_status(content_id: str, new_status: str) -> bool:
    """更新内容状态"""
    folders = get_folders()
    
    # 在所有文件夹中查找
    for folder in ['input', 'processing', 'output', 'queue']:
        folder_path = folders[folder]
        for f in folder_path.glob(f"{content_id}_*.md"):
            # 读取并更新 frontmatter
            content = f.read_text(encoding='utf-8')
            lines = content.split('\n')
            new_lines = []
            in_frontmatter = False
            
            for line in lines:
                if line.strip() == '---':
                    in_frontmatter = not in_frontmatter
                if in_frontmatter and line.startswith('status:'):
                    line = f'status: {new_status}'
                new_lines.append(line)
            
            f.write_text('\n'.join(new_lines), encoding='utf-8')
            return True
    
    return False

def publish_content(content_id: str, platform: str = None) -> dict:
    """发布内容到指定平台"""
    from publishers import PublishManager
    
    folders = get_folders()
    content_file = None
    
    # 在所有文件夹中查找
    for folder in ['input', 'processing', 'queue']:
        folder_path = folders[folder]
        for f in folder_path.glob(f"{content_id}_*.md"):
            content_file = f
            break
    
    if not content_file:
        return {"error": f"Content {content_id} not found"}
    
    # 解析内容
    content = parse_content_file(content_file)
    platforms = content.get('platforms', [])
    
    if not platform and not platforms:
        return {"error": "No platform specified"}
    
    # 解析正文中的各平台版本
    body = content.get('body', '')
    platform_contents = parse_platform_content(body)
    
    # 自动查找图片
    images = content.get('images', [])
    if not images:
        # 在 input 文件夹中查找同名图片
        input_folder = folders.get('input', Path('input'))
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            img_path = input_folder / f"{content_id}_cover{ext}"
            if img_path.exists():
                images = [str(img_path)]
                break
            # 也尝试 content_id 开头的其他图片
            for img in input_folder.glob(f"{content_id}*{ext}"):
                images = [str(img)]
                break
    
    pm = PublishManager()
    results = {}
    
    target_platforms = [platform] if platform else platforms
    
    for p in target_platforms:
        platform_text = platform_contents.get(p, '')
        if not platform_text:
            platform_text = body  # 使用默认正文
        
        result = pm.publish_to_platform(p, {
            'title': content.get('title', ''),
            f'{p}_text': platform_text,
            'images': images
        })
        results[p] = result
    
    return results

def parse_platform_content(body: str) -> dict:
    """解析各平台版本内容"""
    contents = {}
    current_platform = None
    current_content = []
    
    lines = body.split('\n')
    for line in lines:
        if line.startswith('# 🐦 '):
            current_platform = 'twitter'
            current_content = []
        elif line.startswith('# 💼 '):
            current_platform = 'linkedin'
            current_content = []
        elif line.startswith('# 📖 '):
            current_platform = 'zhihu'
            current_content = []
        elif line.startswith('# 📕 '):
            current_platform = 'xiaohongshu'
            current_content = []
        elif current_platform:
            current_content.append(line)
            contents[current_platform] = '\n'.join(current_content)
    
    return contents

# CLI 接口
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: pipeline.py <command> [args]")
        print("Commands:")
        print("  list [folder]      - 列出内容")
        print("  create <title>     - 创建新内容")
        print("  status <id> <stat> - 更新状态")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "list":
        folder = sys.argv[2] if len(sys.argv) > 2 else 'input'
        for c in list_content(folder):
            print(f"[{c['id']}] {c.get('title', 'Untitled')} - {c.get('status')}")
    
    elif cmd == "create":
        title = sys.argv[2] if len(sys.argv) > 2 else "New Content"
        content_id = create_content(title, ["twitter"], "Content here...")
        print(f"Created: {content_id}")
    
    elif cmd == "status":
        if len(sys.argv) > 3:
            update_status(sys.argv[2], sys.argv[3])
            print(f"Updated {sys.argv[2]} to {sys.argv[3]}")
    
    elif cmd == "publish":
        content_id = sys.argv[2] if len(sys.argv) > 2 else None
        platform = sys.argv[3] if len(sys.argv) > 3 else None
        if content_id:
            result = publish_content(content_id, platform)
            print(f"Publish result: {result}")
        else:
            print("Usage: pipeline.py publish <content_id> [platform]")
    
    elif cmd == "publishers":
        from publishers import PublishManager
        pm = PublishManager()
        print("📡 平台发布器就绪状态:")
        for platform in ['twitter', 'linkedin', 'zhihu', 'xiaohongshu']:
            status = "✅" if pm.is_publisher_ready(platform) else "⚠️"
            print(f"  {platform}: {status}")
    
    else:
        print(f"Unknown command: {cmd}")
