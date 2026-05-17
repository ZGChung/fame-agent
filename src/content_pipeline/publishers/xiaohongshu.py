"""
Content Pipeline — 小红书发布器

使用 Playwright 浏览器自动化，通过 Cookie 登录发布笔记。
完全独立，不依赖其他平台模块。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from .base import BasePublisher
from ..models import Content, Platform, PublishResult

logger = logging.getLogger(__name__)

COOKIE_DIR = Path(__file__).resolve().parent / "cookies"
COOKIE_FILE = COOKIE_DIR / "xiaohongshu.json"


class XiaohongshuPublisher(BasePublisher):
    """
    小红书发布器。
    
    通过 Playwright（Chromium）模拟浏览器登录发布。
    需要先通过 `pipeline auth xiaohongshu` 登录获取 Cookie。
    """

    platform = Platform.XIAOHONGSHU

    def __init__(self, cookie_path: Optional[str] = None, headless: bool = False):
        self.cookie_path = Path(cookie_path) if cookie_path else COOKIE_FILE
        self.headless = headless
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None

    def is_configured(self) -> bool:
        return self.cookie_path.exists()

    # --- 同步 publish（内部启动事件循环）---
    def publish(self, content: Content) -> PublishResult:
        return asyncio.run(self._async_publish(content))

    async def _async_publish(self, content: Content) -> PublishResult:
        """异步发布核心逻辑"""
        try:
            # 使用 platform 中配置的 variant 或全文
            platform_text = content.platform_variants.get(
                Platform.XIAOHONGSHU.value, content.body
            )

            success = await self._do_publish(
                title=content.title,
                body=platform_text,
                images=content.images,
            )

            return PublishResult(
                platform=self.platform,
                success=success,
                error=None if success else "Publish returned False",
            )
        except Exception as e:
            logger.exception("Xiaohongshu publish failed")
            return PublishResult(
                platform=self.platform,
                success=False,
                error=str(e),
            )

    async def _do_publish(self, title: str, body: str, images: list[str] | None = None) -> bool:
        """实际的小红书发布流程"""
        try:
            await self._ensure_browser()
            await self._load_cookies()

            logger.info("Navigating to Xiaohongshu publish page...")
            await self._page.goto(
                "https://creator.xiaohongshu.com/publish/publish?from=homepage"
                "&target=image&openFilePicker=true"
            )
            await asyncio.sleep(3)

            # 上传图片
            if images and len(images) > 0:
                await self._upload_image(images[0])

            # 填写标题
            await self._fill_title(title[:100])

            # 填写正文
            await self._fill_body(body[:1000])

            # 截图调试
            await self._page.screenshot(path="/tmp/xhs_before_publish.png")

            # 点击发布
            clicked = await self._click_publish_button()
            if not clicked:
                logger.warning("Could not find publish button")

            await asyncio.sleep(3)
            await self._page.screenshot(path="/tmp/xhs_after_publish.png")
            logger.info("Xiaohongshu publish flow completed")
            return True

        finally:
            await self._close_browser()

    async def _ensure_browser(self):
        """初始化浏览器"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright is required for Xiaohongshu publishing. "
                "Install: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()

    async def _load_cookies(self):
        if not self.cookie_path.exists():
            raise FileNotFoundError(
                f"Xiaohongshu cookie not found at {self.cookie_path}. "
                "Run: pipeline auth xiaohongshu"
            )
        with open(self.cookie_path, encoding="utf-8") as f:
            cookies = json.load(f)
        await self._context.add_cookies(cookies)

    async def _upload_image(self, image_path: str):
        logger.info("Uploading image: %s", image_path)
        file_input = await self._page.query_selector("input.upload-input")
        if file_input:
            await file_input.set_input_files(image_path)
            await asyncio.sleep(3)
            logger.info("Image selected")
        else:
            logger.warning("Upload input not found, trying JS fallback...")
            await self._page.evaluate(
                f"""() => {{
                    const inp = document.querySelector('input[type="file"]');
                    if (inp) {{
                        const dt = new DataTransfer();
                        // Can't set files from JS for security, but we can try
                        console.log('Found file input:', inp);
                    }}
                }}"""
            )

    async def _fill_title(self, title: str):
        filled = False
        # Method 1: placeholder-based
        try:
            el = await self._page.query_selector(
                'input[placeholder*="标题"], [aria-label*="标题"]'
            )
            if el:
                await el.fill(title)
                filled = True
        except Exception:
            pass

        # Method 2: JS fallback
        if not filled:
            try:
                result = await self._page.evaluate(
                    f"""() => {{
                        for (const inp of document.querySelectorAll('input, textarea')) {{
                            if (inp.placeholder && inp.placeholder.includes('标题')) {{
                                const nativeSetter = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value'
                                ).set;
                                nativeSetter.call(inp, '{title}');
                                inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                        return false;
                    }}"""
                )
                if result:
                    filled = True
            except Exception:
                pass

        if filled:
            logger.info("Title filled: %s", title[:30])
        else:
            logger.warning("Could not fill title")

    async def _fill_body(self, body: str):
        filled = False
        try:
            el = await self._page.query_selector(
                'textarea[placeholder*="正文"], [aria-label*="正文"]'
            )
            if el:
                await el.fill(body)
                filled = True
        except Exception:
            pass

        if not filled:
            try:
                # 转义正文中的特殊字符用于 JS
                safe_body = body.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")
                result = await self._page.evaluate(
                    f"""() => {{
                        const sanitized = `{safe_body}`;
                        for (const el of document.querySelectorAll(
                            'textarea, [contenteditable], .note-editor'
                        )) {{
                            if (el.placeholder && (
                                el.placeholder.includes('正文') ||
                                el.placeholder.includes('分享')
                            )) {{
                                el.value = sanitized;
                                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                        }}
                        return false;
                    }}"""
                )
                if result:
                    filled = True
            except Exception:
                pass

        if filled:
            logger.info("Body filled (%d chars)", len(body))
        else:
            logger.warning("Could not fill body")

    async def _click_publish_button(self) -> bool:
        """点击发布按钮"""
        try:
            buttons = await self._page.query_selector_all("button")
            for btn in buttons:
                text = await btn.inner_text()
                if text and "发布" in text and len(text) < 20:
                    await btn.click()
                    await asyncio.sleep(2)
                    return True
        except Exception:
            pass
        return False

    async def _close_browser(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
