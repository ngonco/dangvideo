import os
import sys
import asyncio
from typing import Optional, Dict, Any
from playwright.async_api import BrowserContext, Page
from camoufox.async_api import AsyncCamoufox
from core.config_manager import config_mgr, DOWNLOADS_DIR, PROFILES_DIR
from core.logger import logger

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)

# Thư mục Profile Camoufox mặc định
CAMOUFOX_PROFILE_DIR = os.path.join(PROFILES_DIR, "camoufox")
os.makedirs(CAMOUFOX_PROFILE_DIR, exist_ok=True)


def ensure_camoufox_installed() -> Optional[str]:
    """Kiểm tra và tự động tải binary Camoufox nếu máy chưa có sẵn."""
    try:
        from camoufox.pkgman import launch_path, CamoufoxFetcher
        try:
            p = launch_path()
            if p and os.path.exists(p):
                return str(p)
        except Exception:
            pass

        logger.info("Chưa tìm thấy binary trình duyệt Camoufox. Đang tự động tải về (chỉ 1 lần duy nhất)...", "BROWSER")
        fetcher = CamoufoxFetcher()
        fetcher.install()
        p = launch_path()
        logger.success(f"Đã cài đặt thành công Camoufox Anti-detect: {p}", "BROWSER")
        return str(p)
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra hoặc tải Camoufox binary: {e}", "BROWSER")
        return None


def _mute_audio_enabled() -> bool:
    return bool(config_mgr.get("browser", {}).get("mute_audio", True))


def _headless_enabled() -> bool:
    return bool(config_mgr.get("browser", {}).get("headless", True))


def cleanup_profile_locks(profile_dir: str):
    """
    Dọn dẹp stale parent.lock của riêng profile_dir này.
    TUYỆT ĐỐI KHÔNG tắt các tiến trình Camoufox của các phần mềm khác (như Agent Scan Viral).
    Chỉ tắt tiến trình camoufox.exe nào đang thực sự chạy profile_dir này nếu bị treo.
    """
    lock_path = os.path.join(profile_dir, "parent.lock")
    if not os.path.exists(lock_path):
        return

    # Thử xóa trực tiếp nếu tiến trình cũ đã thoát
    try:
        os.remove(lock_path)
        return
    except Exception:
        pass

    # Nếu file lock đang bị giữ, tìm chính xác PID của Camoufox đang dùng profile này
    try:
        import psutil
        norm_target = os.path.normpath(profile_dir).lower()
        for p in psutil.process_iter(['name', 'cmdline']):
            try:
                name = (p.info['name'] or '').lower()
                if 'camoufox' in name:
                    cmdline = " ".join(p.info['cmdline'] or []).lower()
                    if norm_target in cmdline:
                        p.kill()
            except Exception:
                continue
    except Exception:
        pass

    # Thử xóa lại lock_path sau khi tắt tiến trình mồ côi của riêng profile này
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


class BrowserEngine:
    def __init__(self):
        self.cm: Optional[AsyncCamoufox] = None
        self.context: Optional[BrowserContext] = None
        self.is_headless: Optional[bool] = None
        self.is_muted: Optional[bool] = None
        self._lock = asyncio.Lock()

    async def get_context(self, headless: Optional[bool] = None, profile_name: str = "camoufox") -> BrowserContext:
        async with self._lock:
            if headless is None:
                headless = _headless_enabled()
            mute_audio = _mute_audio_enabled()

            if self.context:
                try:
                    headless_changed = self.is_headless != headless
                    mute_changed = self.is_muted is not None and self.is_muted != mute_audio
                    if headless_changed or mute_changed:
                        logger.info(
                            f"Thay đổi cấu hình trình duyệt (Headless={headless}, Mute={mute_audio})...",
                            "BROWSER",
                        )
                        await self._close_context_unlocked()
                        await asyncio.sleep(1.2)
                    elif not self.context.is_closed():
                        return self.context
                except Exception:
                    self.context = None

            ensure_camoufox_installed()

            user_data_dir = os.path.join(PROFILES_DIR, profile_name)
            os.makedirs(user_data_dir, exist_ok=True)

            # Dọn dẹp stale parent.lock của riêng profile này (an toàn, không đụng app khác)
            cleanup_profile_locks(user_data_dir)

            logger.info(
                f"Khởi động trình duyệt Camoufox Anti-detect (Profile: {profile_name}, Headless: {headless}, Mute={mute_audio})...",
                "BROWSER",
            )

            user_prefs = {
                "dom.webdriver.enabled": False,
                "useAutomationExtension": False,
                "layers.acceleration.disabled": True,
                "gfx.webrender.software": True,
                "gfx.direct3d11.enable-debug-layer": False,
            }
            if mute_audio:
                user_prefs["media.volume_scale"] = "0.0"

            self.cm = AsyncCamoufox(
                headless=headless,
                persistent_context=True,
                user_data_dir=user_data_dir,
                os="windows",
                humanize=0.8,
                window=(1400, 900),
                firefox_user_prefs=user_prefs,
            )
            self.context = await self.cm.__aenter__()
            self.is_headless = headless
            self.is_muted = mute_audio
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

        # 2. Nếu context đang chạy, lấy cookie trực tiếp từ context
        try:
            if self.context and not self.context.is_closed():
                cookies = await self.context.cookies()
                domains = [c.get("domain", "").lower() for c in cookies]
                statuses["youtube"] = any("youtube.com" in d or "google.com" in d for d in domains)
                statuses["tiktok"] = any("tiktok.com" in d for d in domains)
                statuses["facebook"] = any("facebook.com" in d for d in domains)
                statuses["instagram"] = any("instagram.com" in d for d in domains)
                if any("hatbuinho.com" in d for d in domains):
                    statuses["hatbuinho"] = True
                return statuses
        except Exception:
            pass

        # 3. Nếu context đóng, kiểm tra SQLite Cookies (hỗ trợ cả Camoufox moz_cookies và Chromium fallback)
        profile_candidates = [
            os.path.join(PROFILES_DIR, "camoufox"),
            os.path.join(PROFILES_DIR, "default")
        ]
        import tempfile
        import shutil
        import sqlite3

        for u_dir in profile_candidates:
            if not os.path.exists(u_dir):
                continue

            # A. Thử đọc cookies.sqlite của Firefox / Camoufox
            cf_cookie = os.path.join(u_dir, "cookies.sqlite")
            if os.path.exists(cf_cookie):
                temp_f = tempfile.NamedTemporaryFile(delete=False)
                temp_p = temp_f.name
                temp_f.close()
                try:
                    shutil.copy2(cf_cookie, temp_p)
                    conn = sqlite3.connect(temp_p)
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT host FROM moz_cookies")
                    hosts = [r[0].lower() for r in cur.fetchall()]
                    conn.close()
                    statuses["youtube"] = statuses["youtube"] or any("youtube.com" in h or "google.com" in h for h in hosts)
                    statuses["tiktok"] = statuses["tiktok"] or any("tiktok.com" in h for h in hosts)
                    statuses["facebook"] = statuses["facebook"] or any("facebook.com" in h for h in hosts)
                    statuses["instagram"] = statuses["instagram"] or any("instagram.com" in h for h in hosts)
                    if any("hatbuinho.com" in h for h in hosts):
                        statuses["hatbuinho"] = True
                    break
                except Exception:
                    pass
                finally:
                    try:
                        os.unlink(temp_p)
                    except Exception:
                        pass

            # B. Fallback Chromium Cookies nếu còn
            cr_candidates = [
                os.path.join(u_dir, "Default", "Network", "Cookies"),
                os.path.join(u_dir, "Network", "Cookies"),
                os.path.join(u_dir, "Cookies")
            ]
            for c_path in cr_candidates:
                if os.path.exists(c_path):
                    temp_f = tempfile.NamedTemporaryFile(delete=False)
                    temp_p = temp_f.name
                    temp_f.close()
                    try:
                        shutil.copy2(c_path, temp_p)
                        conn = sqlite3.connect(temp_p)
                        cur = conn.cursor()
                        cur.execute("SELECT DISTINCT host_key FROM cookies")
                        hosts = [r[0].lower() for r in cur.fetchall()]
                        conn.close()
                        statuses["youtube"] = statuses["youtube"] or any("youtube.com" in h or "google.com" in h for h in hosts)
                        statuses["tiktok"] = statuses["tiktok"] or any("tiktok.com" in h for h in hosts)
                        statuses["facebook"] = statuses["facebook"] or any("facebook.com" in h for h in hosts)
                        statuses["instagram"] = statuses["instagram"] or any("instagram.com" in h for h in hosts)
                        if any("hatbuinho.com" in h for h in hosts):
                            statuses["hatbuinho"] = True
                        break
                    except Exception:
                        pass
                    finally:
                        try:
                            os.unlink(temp_p)
                        except Exception:
                            pass

        return statuses

    async def open_login_page(self, platform: str):
        """Mở cửa sổ trình duyệt Camoufox để người dùng đăng nhập tài khoản thủ công"""
        urls = {
            "hatbuinho": "https://hatbuinho.com/",
            "youtube": "https://studio.youtube.com/?approve_browser_access=true",
            "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
            "facebook": "https://www.facebook.com/",
            "instagram": "https://www.instagram.com/"
        }
        url = urls.get(platform, "https://www.google.com")
        
        try:
            logger.info(f"Đang chuẩn bị mở trình duyệt Camoufox để đăng nhập {platform.upper()}...", "BROWSER")
            # Đóng context cũ nếu đang chạy headless để mở cửa sổ trực quan
            await self.close()
            ctx = await self.get_context(headless=False)
            page = await self.get_page(ctx)
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            logger.info(f"Đã mở trang đăng nhập {platform.upper()} trên trình duyệt Camoufox.", "BROWSER")
        except Exception as e:
            logger.error(f"Lỗi khi mở trang đăng nhập {platform.upper()}: {e}", "BROWSER")

    async def _close_context_unlocked(self):
        if self.cm:
            try:
                await self.cm.__aexit__(None, None, None)
            except Exception:
                pass
            self.cm = None
            self.context = None
        elif self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
        self.is_headless = None
        self.is_muted = None

        # Đợi giải phóng lock và dọn parent.lock nếu còn sót của riêng profile Auto_Dang_video
        await asyncio.sleep(0.5)
        for p_name in ["camoufox", "default"]:
            p_dir = os.path.join(PROFILES_DIR, p_name)
            if os.path.exists(p_dir):
                cleanup_profile_locks(p_dir)

    async def close(self):
        async with self._lock:
            await self._close_context_unlocked()
            logger.info("Đã đóng trình duyệt Camoufox an toàn.", "BROWSER")

browser_engine = BrowserEngine()
