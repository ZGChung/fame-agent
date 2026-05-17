#!/usr/bin/env python3
"""
小红书自动化发布模块
使用 Playwright 浏览器自动化
"""

import json
import os
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

COOKIE_FILE = Path(__file__).parent / "cookies" / "xiaohongshu.json"

class XiaohongshuPublisher:
    """小红书发布器"""
    
    def __init__(self, cookie_path: Optional[str] = None):
        self.cookie_path = Path(cookie_path) if cookie_path else COOKIE_FILE
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        
    async def init_browser(self, headless: bool = False):
        """初始化浏览器"""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright not installed. Run: pip install playwright")
        
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        self.page = await self.context.new_page()
    
    async def load_cookies(self):
        """加载登录 Cookie"""
        if not self.cookie_path.exists():
            raise FileNotFoundError(f"Cookie 文件不存在: {self.cookie_path}")
        
        with open(self.cookie_path, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        
        await self.context.add_cookies(cookies)
    
    def is_configured(self) -> bool:
        """检查是否已配置 Cookie"""
        return self.cookie_path.exists()
    
    async def publish(self, title: str, content: str, images: list = None) -> bool:
        """
        发布笔记
        
        Args:
            title: 标题
            content: 正文内容
            images: 图片路径列表
        
        Returns:
            bool: 发布是否成功
        """
        if not self.browser:
            await self.init_browser()
        
        try:
            # 1. 访问发布页面
            await self.page.goto('https://creator.xiaohongshu.com/publish/publish?from=homepage&target=image&openFilePicker=true')
            await asyncio.sleep(3)
            
            print(f"📍 当前页面: {self.page.url}")
            
            # 2. 上传图片
            if images and len(images) > 0:
                image_path = images[0]  # 取第一张图
                print(f"📤 上传图片: {image_path}")
                
                # 找到文件上传输入框
                file_input = await self.page.query_selector('input.upload-input')
                if file_input:
                    await file_input.set_input_files(image_path)
                    print("✅ 图片已选择")
                    await asyncio.sleep(3)  # 等待图片上传
                else:
                    print("⚠️ 未找到上传输入框")
            else:
                print("⚠️ 未提供图片路径")
            
            # 3. 等待表单出现并填写
            print("⏳ 等待表单加载...")
            await asyncio.sleep(3)
            
            # 4. 填写标题 - 使用JavaScript查找
            title_filled = False
            if title:
                # 方法1: 尝试使用placeholder查找
                try:
                    title_input = await self.page.query_selector('input[placeholder*="标题"], [aria-label*="标题"], [data-placeholder*="标题"]')
                    if title_input:
                        await title_input.fill(title[:100])
                        title_filled = True
                        print("✅ 标题已填写")
                except Exception as e:
                    print(f"标题填写尝试1失败: {e}")
                
                # 方法2: 用JavaScript直接设置
                if not title_filled:
                    try:
                        result = await self.page.evaluate(f'''
                            () => {{
                                const inputs = document.querySelectorAll('input, textarea');
                                for (let inp of inputs) {{
                                    if (inp.placeholder && inp.placeholder.includes('标题')) {{
                                        inp.value = "{title[:100]}";
                                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        return true;
                                    }}
                                }}
                                return false;
                            }}
                        ''')
                        if result:
                            title_filled = True
                            print("✅ 标题已填写 (JS)")
                    except Exception as e:
                        print(f"标题填写尝试2失败: {e}")
            
            # 5. 填写正文
            content_filled = False
            if content:
                try:
                    # 尝试查找正文输入框
                    content_input = await self.page.query_selector('textarea[placeholder*="正文"], [aria-label*="正文"], [data-placeholder*="正文"]')
                    if content_input:
                        await content_input.fill(content[:1000])
                        content_filled = True
                        print("✅ 正文已填写")
                except Exception as e:
                    print(f"正文填写尝试1失败: {e}")
                
                if not content_filled:
                    try:
                        result = await self.page.evaluate(f'''
                            () => {{
                                const inputs = document.querySelectorAll('input, textarea, [contenteditable]');
                                for (let inp of inputs) {{
                                    if (inp.placeholder && (inp.placeholder.includes('正文') || inp.placeholder.includes('分享'))) {{
                                        inp.value = `{content[:1000]}`;
                                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                        return true;
                                    }}
                                }}
                                return false;
                            }}
                        ''')
                        if result:
                            content_filled = True
                            print("✅ 正文已填写 (JS)")
                    except Exception as e:
                        print(f"正文填写尝试2失败: {e}")
            
            # 6. 截图确认
            await self.page.screenshot(path='/tmp/xiaohongshu_filled.png')
            print("📸 表单截图已保存")
            
            # 7. 点击发布按钮
            try:
                publish_buttons = await self.page.query_selector_all('button')
                for btn in publish_buttons:
                    text = await btn.inner_text()
                    if text and '发布' in text and len(text) < 20:
                        await btn.click()
                        await asyncio.sleep(2)
                        print("✅ 已点击发布按钮")
                        break
            except Exception as e:
                print(f"⚠️ 点击发布按钮失败: {e}")
            
            # 8. 确认发布
            try:
                await asyncio.sleep(2)
                confirm_buttons = await self.page.query_selector_all('button')
                for btn in confirm_buttons:
                    text = await btn.inner_text()
                    if text and ('确认' in text or '发布' in text):
                        await btn.click()
                        await asyncio.sleep(3)
                        print("✅ 已确认发布")
                        break
            except:
                pass
            
            # 9. 最终截图
            await self.page.screenshot(path='/tmp/xiaohongshu_final.png')
            
            print("✨ 发布流程完成!")
            return True
            
        except Exception as e:
            print(f"❌ 发布失败: {e}")
            await self.page.screenshot(path='/tmp/xiaohongshu_error.png')
            return False
    
    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()


async def quick_publish(title: str, content: str, images: list = None) -> bool:
    """快速发布"""
    publisher = XiaohongshuPublisher()
    try:
        await publisher.init_browser(headless=False)
        await publisher.load_cookies()
        return await publisher.publish(title, content, images)
    finally:
        await publisher.close()


if __name__ == "__main__":
    import sys
    
    if not PLAYWRIGHT_AVAILABLE:
        print("❌ Playwright 未安装")
        print("安装命令: pip install playwright && playwright install chromium")
        sys.exit(1)
    
    if len(sys.argv) < 3:
        print("Usage: xiaohongshu.py <title> <content> [images...]")
        sys.exit(1)
    
    title = sys.argv[1]
    content = sys.argv[2]
    images = sys.argv[3:] if len(sys.argv) > 3 else None
    
    asyncio.run(quick_publish(title, content, images))
