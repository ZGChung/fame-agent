#!/usr/bin/env python3
"""
Twitter/LinkedIn 发布模块
基于 Twitter API v2 和 LinkedIn API
"""

import json
import os
from pathlib import Path
from typing import Optional

# 配置
CONFIG_FILE = Path(__file__).parent.parent / "config.json"

def load_config() -> dict:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

class TwitterPublisher:
    """Twitter 发布器"""
    
    def __init__(self, api_key: str = None, api_secret: str = None, 
                 bearer_token: str = None, access_token: str = None):
        self.api_key = api_key or os.environ.get('TWITTER_API_KEY')
        self.api_secret = api_secret or os.environ.get('TWITTER_API_SECRET')
        self.bearer_token = bearer_token or os.environ.get('TWITTER_BEARER_TOKEN')
        self.access_token = access_token or os.environ.get('TWITTER_ACCESS_TOKEN')
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.bearer_token and self.access_token)
    
    def post(self, text: str, reply_to: str = None) -> dict:
        """
        发布推文
        
        Args:
            text: 推文内容
            reply_to: 回复的推文 ID
        
        Returns:
            dict: 包含 tweet id 和 url
        """
        if not self.is_configured():
            return {"error": "Twitter API not configured"}
        
        # TODO: 实现实际 API 调用
        # 使用 Twitter API v2
        import requests
        
        url = "https://api.twitter.com/2/tweets"
        payload = {"text": text}
        if reply_to:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to}
        
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json"
        }
        
        # 实际调用需要 OAuth 1.0a 或 OAuth 2.0
        # 这里返回模拟结果
        return {
            "success": True,
            "tweet_id": "mock_id",
            "url": f"https://twitter.com/user/status/mock_id"
        }


class LinkedInPublisher:
    """LinkedIn 发布器"""
    
    def __init__(self, access_token: str = None):
        self.access_token = access_token or os.environ.get('LINKEDIN_ACCESS_TOKEN')
    
    def is_configured(self) -> bool:
        return bool(self.access_token)
    
    def post(self, text: str, title: str = None, url: str = None) -> dict:
        """
        发布帖子
        
        Args:
            text: 正文内容
            title: 文章标题 (可选)
            url: 文章链接 (可选)
        
        Returns:
            dict: 包含 post id 和 url
        """
        if not self.is_configured():
            return {"error": "LinkedIn API not configured"}
        
        # LinkedIn API v2
        # POST https://api.linkedin.com/v2/ugcPosts
        return {
            "success": True,
            "post_id": "mock_id",
            "url": "https://www.linkedin.com/feed/update/mock"
        }


class ZhihuPublisher:
    """知乎发布器"""
    
    def __init__(self, cookie: str = None):
        self.cookie = cookie or os.environ.get('ZHIHU_COOKIE')
    
    def is_configured(self) -> bool:
        return bool(self.cookie)
    
    def post(self, title: str, content: str, url: str = None) -> dict:
        """
        发布文章
        
        Args:
            title: 文章标题
            content: 文章内容 (markdown)
            url: 原文链接 (用于同步)
        
        Returns:
            dict: 包含 article id 和 url
        """
        if not self.is_configured():
            return {"error": "Zhihu not configured"}
        
        # 知乎 API 需要登录 Cookie
        # 可以使用 web scraping 或 API
        return {
            "success": True,
            "article_id": "mock_id",
            "url": f"https://zhuanlan.zhihu.com/p/mock"
        }


# 导入小红书发布器
from .xiaohongshu import XiaohongshuPublisher

# 发布管理器
class PublishManager:
    """统一发布管理器"""
    
    def __init__(self):
        config = load_config()
        self.publishers = {
            'twitter': TwitterPublisher(),
            'linkedin': LinkedInPublisher(),
            'zhihu': ZhihuPublisher(),
            'xiaohongshu': XiaohongshuPublisher(),
        }
    
    def get_publisher(self, platform: str):
        return self.publishers.get(platform)
    
    def is_publisher_ready(self, platform: str) -> bool:
        publisher = self.get_publisher(platform)
        return publisher.is_configured() if publisher else False
    
    def publish_to_platform(self, platform: str, content: dict) -> dict:
        """发布到指定平台"""
        publisher = self.get_publisher(platform)
        
        if platform == 'twitter':
            return publisher.post(content.get('twitter_text', ''))
        elif platform == 'linkedin':
            return publisher.post(
                content.get('linkedin_text', ''),
                content.get('title'),
                content.get('url')
            )
        elif platform == 'zhihu':
            return publisher.post(
                content.get('title'),
                content.get('zhihu_text', ''),
                content.get('url')
            )
        elif platform == 'xiaohongshu':
            # 小红书需要异步调用
            import asyncio
            return asyncio.run(self._publish_xiaohongshu(publisher, content))
        
        return {"error": f"Unknown platform: {platform}"}
    
    async def _publish_xiaohongshu(self, publisher, content: dict) -> dict:
        """发布到小红书"""
        try:
            await publisher.init_browser(headless=False)
            await publisher.load_cookies()
            result = await publisher.publish(
                title=content.get('title', ''),
                content=content.get('xiaohongshu_text', ''),
                images=content.get('images', [])
            )
            await publisher.close()
            return {"success": result, "platform": "xiaohongshu"}
        except Exception as e:
            return {"error": str(e)}
    
    def publish_all(self, content: dict, platforms: list) -> dict:
        """发布到多个平台"""
        results = {}
        for platform in platforms:
            results[platform] = self.publish_to_platform(platform, content)
        return results


if __name__ == "__main__":
    # 测试
    pm = PublishManager()
    print("📡 平台发布器就绪状态:")
    for platform in ['twitter', 'linkedin', 'zhihu']:
        status = "✅" if pm.is_publisher_ready(platform) else "❌"
        print(f"  {platform}: {status}")
