import os
import sys
import asyncio
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from core.config_manager import config_mgr, DOWNLOADS_DIR, PROFILES_DIR
from core.logger import logger

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)

# Cấu hình đường dẫn Playwright Browser đảm bảo hoạt động cả trong môi trường Python và PyInstaller .exe
local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
ms_playwright_dir = os.path.join(local_appdata, "ms-playwright")
if os.path.exists(ms_playwright_dir):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = ms_playwright_dir

def get_chromium_executable_path() -> Optional[str]:
    """Tìm tệp chrome.exe thực tế trong ms-playwright để tránh lỗi thiếu file trong PyInstaller"""
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    ms_dir = os.path.join(local, "ms-playwright")
    if os.path.exists(ms_dir):
        for item in sorted(os.listdir(ms_dir), reverse=True):
            if item.startswith("chromium-") and "headless" not in item:
                for sub in ["chrome-win64\\chrome.exe", "chrome-win\\chrome.exe"]:
                    p = os.path.join(ms_dir, item, sub)
                    if os.path.exists(p):
                        return p
    return None

class BrowserEngine:
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.is_headless: Optional[bool] = None
        self._lock = asyncio.Lock()

    async def get_context(self, headless: Optional[bool] = None, profile_name: str = "default") -> BrowserContext:
        async with self._lock:
            if headless is None:
                headless = config_mgr.get("browser", {}).get("headless", False)

            if self.context:
                try:
                    if self.is_headless != headless:
                        logger.info(f"Thay đổi trạng thái hiển thị trình duyệt sang Headless={headless}...", "BROWSER")
                        await self.context.close()
                        self.context = None
                    elif len(self.context.pages) > 0 or not self.context.is_closed():
                        return self.context
                except Exception:
                    self.context = None

            if not self.playwright:
                self.playwright = await async_playwright().start()

            user_data_dir = os.path.join(PROFILES_DIR, profile_name)
            os.makedirs(user_data_dir, exist_ok=True)

            logger.info(f"Khởi động trình duyệt Playwright (Profile: {profile_name}, Headless: {headless})...", "BROWSER")

            exec_path = get_chromium_executable_path()
            launch_kwargs = {
                "user_data_dir": user_data_dir,
                "headless": headless,
                "accept_downloads": True,
                "viewport": None,  # Use real screen size
                "args": [
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--window-position=50,50",
                    "--window-size=1400,900"
                ],
                "permissions": ["clipboard-read", "clipboard-write", "notifications"]
            }
            if exec_path:
                launch_kwargs["executable_path"] = exec_path

            # Launch persistent context with foreground window flags
            self.context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
            self.is_headless = headless
            return self.context

    async def get_page(self, context: Optional[BrowserContext] = None) -> Page:
        ctx = context or await self.get_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            await page.bring_to_front()
        except Exception:
            pass
        return page

    async def get_login_statuses(self) -> Dict[str, bool]:
        """Kiểm tra trạng thái đăng nhập của các nền tảng dựa trên Cookies/Session"""
        statuses = {
            "hatbuinho": False,
            "youtube": False,
            "tiktok": False,
            "facebook": False,
            "instagram": False
        }
        
        # 1. Kiểm tra cấu hình HatBuiNho
        h_cfg = config_mgr.get("hatbuinho", {})
        if h_cfg.get("username") and h_cfg.get("password"):
            statuses["hatbuinho"] = True

        user_data_dir = os.path.join(PROFILES_DIR, "default")
        if not os.path.exists(user_data_dir):
            return statuses

        try:
            # Chỉ đọc cookie nếu context đang chạy để tránh khóa trạng thái headless
            if self.context and not self.context.is_closed():
                cookies = await self.context.cookies()
                domains = [c.get("domain", "").lower() for c in cookies]
                statuses["youtube"] = any("youtube.com" in d or "google.com" in d for d in domains)
                statuses["tiktok"] = any("tiktok.com" in d for d in domains)
                statuses["facebook"] = any("facebook.com" in d for d in domains)
                statuses["instagram"] = any("instagram.com" in d for d in domains)
                if any("hatbuinho.com" in d for d in domains):
                    statuses["hatbuinho"] = True
        except Exception:
            pass

        return statuses

    async def open_login_page(self, platform: str):
        """Mở cửa sổ trình duyệt nổi để người dùng đăng nhập tài khoản thủ công"""
        urls = {
            "hatbuinho": "https://hatbuinho.com/",
            "youtube": "https://studio.youtube.com",
            "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
            "facebook": "https://www.facebook.com/",
            "instagram": "https://www.instagram.com/"
        }
        url = urls.get(platform, "https://www.google.com")
        
        # Đóng context cũ nếu đang chạy headless để mở cửa sổ trực quan
        await self.close()
        ctx = await self.get_context(headless=False)
        page = await self.get_page(ctx)
        await page.goto(url)
        logger.info(f"Đã mở trang đăng nhập {platform.upper()} trên trình duyệt.", "BROWSER")

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
