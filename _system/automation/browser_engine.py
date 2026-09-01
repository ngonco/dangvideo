import os
import sys
import asyncio
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from core.config_manager import config_mgr, DOWNLOADS_DIR, PROFILES_DIR
from core.logger import logger

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)

class BrowserEngine:
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self._lock = asyncio.Lock()

    async def get_context(self, headless: Optional[bool] = None, profile_name: str = "default") -> BrowserContext:
        async with self._lock:
            if self.context:
                try:
                    if len(self.context.pages) > 0 or not self.context.is_closed():
                        return self.context
                except Exception:
                    self.context = None

            if not self.playwright:
                self.playwright = await async_playwright().start()

            user_data_dir = os.path.join(PROFILES_DIR, profile_name)
            os.makedirs(user_data_dir, exist_ok=True)

            if headless is None:
                headless = config_mgr.get("browser", {}).get("headless", False)

            logger.info(f"Khởi động trình duyệt Playwright (Profile: {profile_name}, Headless: {headless})...", "BROWSER")

            # Launch persistent context with foreground window flags
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=headless,
                accept_downloads=True,
                viewport=None,  # Use real screen size
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--window-position=50,50",
                    "--window-size=1400,900"
                ],
                permissions=["clipboard-read", "clipboard-write", "notifications"]
            )
            return self.context

    async def get_page(self, context: Optional[BrowserContext] = None) -> Page:
        ctx = context or await self.get_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            await page.bring_to_front()
        except Exception:
            pass
        return page

    async def close(self):
        async with self._lock:
            if self.context:
                try:
                    await self.context.close()
                except Exception:
                    pass
                self.context = None
            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception:
                    pass
                self.playwright = None
            logger.info("Đã đóng trình duyệt Playwright an toàn.", "BROWSER")

browser_engine = BrowserEngine()
