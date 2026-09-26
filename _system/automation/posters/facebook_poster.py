import os
import asyncio
from typing import Dict, Any, Optional, List
from playwright.async_api import Page
from automation.posters.base_poster import BasePoster
from core.logger import logger
from core.config_manager import config_manager
from core.schedule_helper import get_native_schedule
from automation.ai_fallback import fail_with_ai, SCHEDULE_GOAL

FB_PRODASH_URL = "https://www.facebook.com/professional_dashboard/"
FB_LIBRARY_SCHEDULED = "https://www.facebook.com/professional_dashboard/content/content_library"

_EN_MON = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

SHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "debug_screenshots")


def _fb_date_label(native: Dict[str, Any]) -> str:
    """Format Date combobox như bản ghi: '3 Sep 2026' (không zero-pad, tháng EN)."""
    return f"{native['day']} {_EN_MON[native['month'] - 1]} {native['year']}"


class FacebookPoster(BasePoster):
    def __init__(self):
        super().__init__("Facebook")

    async def _shot(self, page: Page, name: str):
        try:
            os.makedirs(SHOT_DIR, exist_ok=True)
            path = os.path.join(SHOT_DIR, f"{name}.png")
            await page.screenshot(path=path)
            logger.info(f"Ảnh Facebook: {path}", "FACEBOOK")
        except Exception:
            pass

    async def _dismiss_fb_popups(self, page: Page, press_escape: bool = False):
        try:
            await page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('div[role="button"], button, span'));
                const hit = btns.find(b => {
                    const t = (b.innerText || '').trim().toLowerCase();
                    return t === 'lúc khác' || t === 'not now' || t === 'đóng' || t === 'close'
                        || t === 'got it' || t === 'đã hiểu';
                });
                if (hit) hit.click();
            }""")
            if press_escape:
                await page.keyboard.press("Escape")
            await asyncio.sleep(0.4)
        except Exception:
            pass

    async def _wait_login(self, page: Page) -> bool:
        login_needed = "login" in page.url or await page.locator(
            'input#email, input[name="email"]'
        ).first.is_visible(timeout=4000)
        if not login_needed:
            return True

        logger.warning(
            "👉 Chưa đăng nhập Facebook! Vui lòng hoàn tất đăng nhập trên cửa sổ trình duyệt "
            "(hệ thống sẽ tự động chờ tối đa 5 phút)...",
            "FACEBOOK",
        )
        try:
            await page.bring_to_front()
        except Exception:
            pass

        for sec in range(0, 300, 3):
            if sec > 0 and sec % 30 == 0:
                logger.info(f"⏳ [FACEBOOK] Đang chờ bạn đăng nhập... (Đã qua {sec}/300s)", "FACEBOOK")
            await asyncio.sleep(3)
            await self._dismiss_fb_popups(page)
            if "login" not in page.url and not await page.locator(
                'input#email, input[name="email"]'
            ).first.is_visible(timeout=1000):
                return True
        return False

    async def _ensure_switched_to_fanpage(self, page: Page, page_url: str) -> bool:
        """Kiểm tra và chuyển quyền quản trị sang Fanpage mục tiêu nếu chưa chuyển."""
        if not page_url:
            return False
        try:
            logger.info(f"Kiểm tra chuyển quyền sang Fanpage: {page_url}", "FACEBOOK")
            await page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            await self._dismiss_fb_popups(page)

            if not await self._wait_login(page):
                return False

            # Check if switch button exists: Switch Now / Chuyển ngay / Switch
            switch_btn = page.locator(
                'div[role="button"]:has-text("Switch Now"), '
                'div[role="button"]:has-text("Chuyển ngay"), '
                'div[aria-label="Switch Now"], '
                'div[aria-label="Chuyển ngay"]'
            ).first

            if await switch_btn.is_visible(timeout=4000):
                logger.info("Tìm thấy nút Chuyển ngay (Switch Now), đang bấm chuyển...", "FACEBOOK")
                try:
                    await switch_btn.evaluate("el => el.click()")
                except Exception:
                    await switch_btn.click(force=True, timeout=5000)
                await asyncio.sleep(6)
                await self._dismiss_fb_popups(page)
                logger.success(f"Đã chuyển quyền sang Fanpage: {page_url}", "FACEBOOK")
                return True

            btn2 = page.locator(
                'div[role="button"]:has-text("Switch"), '
                'div[aria-label="Switch"]'
            ).first
            if await btn2.is_visible(timeout=3000):
                logger.info("Tìm thấy nút Switch, đang bấm chuyển...", "FACEBOOK")
                try:
                    await btn2.evaluate("el => el.click()")
                except Exception:
                    await btn2.click(force=True, timeout=5000)
                await asyncio.sleep(6)
                await self._dismiss_fb_popups(page)
                logger.success(f"Đã chuyển quyền sang Fanpage: {page_url}", "FACEBOOK")
                return True

            # Check if already switched (e.g. Manage / Quản lý button visible)
            manage_btn = page.locator(
                'div[role="button"]:has-text("Manage"), '
                'div[role="button"]:has-text("Quản lý"), '
                'div[aria-label="Manage"], '
                'div[aria-label="Quản lý"]'
            ).first
            if await manage_btn.is_visible(timeout=3000):
                logger.info(f"Đang ở đúng tài khoản Fanpage ({page_url}) (thấy nút Quản lý).", "FACEBOOK")
                return True

            logger.info(f"Không cần chuyển hoặc đã ở trang Fanpage: {page_url}", "FACEBOOK")
            return True
        except Exception as e:
            logger.warning(f"Lỗi khi kiểm tra/chuyển Fanpage ({page_url}): {e}", "FACEBOOK")
            return False

    async def _ensure_switched_to_personal(self, page: Page) -> bool:
        """Kiểm tra và chuyển quyền trở lại Trang cá nhân nếu trình duyệt đang ở profile Fanpage."""
        try:
            logger.info("Kiểm tra profile Facebook hiện tại (cần ở Trang cá nhân)...", "FACEBOOK")
            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            await self._dismiss_fb_popups(page)

            if not await self._wait_login(page):
                return False

            profile_btn = page.locator(
                'div[aria-label="Your profile"], '
                'div[aria-label="Trang cá nhân của bạn"], '
                'div[role="button"][aria-label*="profile" i]'
            ).first

            if not await profile_btn.is_visible(timeout=5000):
                logger.info("Không tìm thấy nút profile avatar, tiếp tục với phiên hiện tại.", "FACEBOOK")
                return True

            await profile_btn.click()
            await asyncio.sleep(2)

            switch_to_personal_btn = page.locator(
                'div[role="dialog"] div[role="button"][aria-label*="Switch to "], '
                'div[role="dialog"] div[role="button"][aria-label*="Chuyển sang "], '
                'div[role="menu"] div[role="button"][aria-label*="Switch to "], '
                'div[role="menu"] div[role="button"][aria-label*="Chuyển sang "]'
            ).first

            if await switch_to_personal_btn.is_visible(timeout=3000):
                target_label = await switch_to_personal_btn.get_attribute("aria-label") or "Trang cá nhân"
                logger.info(f"Đang ở profile Fanpage, bấm chuyển về {target_label}...", "FACEBOOK")
                try:
                    await switch_to_personal_btn.evaluate("el => el.click()")
                except Exception:
                    await switch_to_personal_btn.click(force=True, timeout=5000)
                await asyncio.sleep(6)
                await self._dismiss_fb_popups(page)
                logger.success(f"Đã chuyển về {target_label}.", "FACEBOOK")
                return True

            logger.info("Đã ở đúng tài khoản Trang cá nhân Facebook.", "FACEBOOK")
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            return True
        except Exception as e:
            logger.warning(f"Lỗi khi kiểm tra/chuyển về Trang cá nhân: {e}", "FACEBOOK")
            return False

    async def scan_managed_pages(self, page: Optional[Page] = None) -> List[Dict[str, str]]:
        """Quét danh sách các Fanpage do tài khoản quản lý."""
        should_close_page = False
        if page is None:
            from automation.browser_engine import browser_engine
            ctx = await browser_engine.get_context()
            page = await ctx.new_page()
            should_close_page = True

        try:
            logger.info("Đang quét danh sách Fanpage đang quản lý từ Facebook...", "FACEBOOK")
            await page.goto("https://www.facebook.com/pages/?category=your_pages", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            await self._dismiss_fb_popups(page)

            if not await self._wait_login(page):
                logger.warning("Chưa đăng nhập Facebook, không thể quét danh sách Fanpage.", "FACEBOOK")
                return []

            pages_data = await page.evaluate('''() => {
                const results = [];
                const seen = new Set();
                const main = document.querySelector('div[role="main"]') || document.body;
                const links = Array.from(main.querySelectorAll('a[href]'));
                const excluded = [
                    'pages', 'watch', 'gaming', 'messages', 'friends', 'groups',
                    'marketplace', 'bookmarks', 'events', 'saved', 'memories',
                    'ads', 'business', 'notifications', 'me', 'help', 'settings',
                    'privacy', 'login', 'policies', 'dialog', 'recover'
                ];
                for (const a of links) {
                    const href = a.href;
                    const text = (a.innerText || '').trim();
                    if (!text) continue;
                    try {
                        const u = new URL(href);
                        if (u.pathname.includes('profile.php')) {
                            const id = u.searchParams.get('id');
                            if (id) {
                                const cleanUrl = `https://www.facebook.com/profile.php?id=${id}`;
                                const name = text.split('\\n')[0].trim();
                                if (!seen.has(cleanUrl) && name.length >= 2) {
                                    seen.add(cleanUrl);
                                    results.push({ name: name, url: cleanUrl });
                                }
                            }
                            continue;
                        }
                        const segs = u.pathname.split('/').filter(Boolean);
                        if (segs.length === 1 && !excluded.includes(segs[0].toLowerCase())) {
                            const cleanUrl = `https://www.facebook.com/${segs[0]}/`;
                            const name = text.split('\\n')[0].trim();
                            const nameLower = name.toLowerCase();
                            if (['create post', 'tạo bài viết', 'switch', 'chuyển', 'see all', 'xem tất cả', 'xem thêm', 'see more'].includes(nameLower)) {
                                continue;
                            }
                            if (!seen.has(cleanUrl) && name.length >= 2) {
                                seen.add(cleanUrl);
                                results.push({ name: name, url: cleanUrl });
                            }
                        }
                    } catch(e) {}
                }
                return results;
            }''')
            logger.success(f"Quét được {len(pages_data)} Fanpage Facebook.", "FACEBOOK")
            return pages_data
        except Exception as e:
            logger.error(f"Lỗi khi quét danh sách Fanpage Facebook: {e}", "FACEBOOK")
            return []
        finally:
            if should_close_page and page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def _click_create_reel(self, page: Page) -> bool:
        create = None
        for sec in range(35):
            for sel in [
                '#prodash-create-button',
                'div[role="main"] div[role="button"][aria-label="Create"]',
                'div[role="main"] div[role="button"][aria-label="Tạo"]',
                'div[role="button"]:has-text("+ Create")',
                'div[role="button"]:has-text("+ Tạo")',
                'div[role="button"]:has-text("Create a post")',
                'div[role="button"]:has-text("Tạo bài viết")',
            ]:
                loc = page.locator(sel).first
                try:
                    if await loc.is_visible(timeout=500):
                        create = loc
                        break
                except Exception:
                    pass
            if create is not None:
                break
            await asyncio.sleep(1)

        if create is None:
            return False

        try:
            await create.evaluate("el => el.click()")
        except Exception:
            await create.click(force=True, timeout=5000)
        logger.info("Đã bấm nút Create / Tạo trên Professional Dashboard.", "FACEBOOK")
        await asyncio.sleep(2)

        for attempt in range(2):
            clicked = await page.evaluate("""() => {
                const menu = document.getElementById('prodash_create_menu_items') || document.body;
                const items = Array.from(menu.querySelectorAll('[role="menuitem"], div[role="button"], span'));
                const hit = items.find(el => {
                    const t = (el.innerText || '').trim().toLowerCase();
                    return t === 'reel' || t === 'thước phim' || t.startsWith('reel') || t.startsWith('thước phim');
                });
                if (hit) { hit.click(); return true; }
                return false;
            }""")
            if clicked:
                await asyncio.sleep(3)
                return True
            # Retry click create button
            try:
                await create.evaluate("el => el.click()")
            except Exception:
                await create.click(force=True, timeout=5000)
            await asyncio.sleep(1.5)

        return False

    async def _reel_dialog_ready(self, page: Page) -> bool:
        dialog = page.locator(
            'div[role="dialog"]:has-text("Create reel"), '
            'div[role="dialog"]:has-text("Tạo thước phim"), '
            'div[role="dialog"]:has-text("Add Video"), '
            'div[role="dialog"]:has-text("Thêm video")'
        ).first
        return await dialog.is_visible(timeout=15000)

    async def _click_next_only(self, page: Page) -> str:
        """Chỉ bấm Next/Tiếp. Không bấm Post/Share/Schedule a post."""
        return await page.evaluate("""() => {
            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]')).filter(d => {
                const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                const t = (d.innerText || '').toLowerCase();
                if (aria.includes('notification')) return false;
                return t.includes('create reel') || t.includes('tạo thước')
                    || t.includes('edit reel') || t.includes('chỉnh sửa') || t.includes('trim video')
                    || t.includes('add video') || t.includes('thêm video');
            });
            const d = dialogs[dialogs.length - 1];
            if (!d) return '';
            const btns = Array.from(d.querySelectorAll('div[role="button"], button')).filter(b => {
                const aria = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                const text = (b.innerText || '').toLowerCase().trim();
                if (aria.includes('add to') || text.includes('add to')) return false;
                if (text.includes('schedule a post')) return false;
                return aria === 'next' || aria === 'tiếp' || aria === 'tiếp tục'
                    || text === 'next' || text === 'tiếp' || text === 'tiếp tục' || text === 'tiếp theo';
            });
            if (!btns.length) return '';
            const target = btns[btns.length - 1];
            if (target.getAttribute('aria-disabled') === 'true' || target.disabled) return '';
            target.click();
            return target.innerText || target.getAttribute('aria-label') || 'Next';
        }""")

    async def _on_reel_settings(self, page: Page) -> bool:
        return bool(await page.evaluate("""() => {
            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]')).filter(d => {
                const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                return !aria.includes('notification');
            });
            const d = dialogs[dialogs.length - 1];
            if (!d) return false;
            const t = (d.innerText || '').toLowerCase();
            return t.includes('reel settings') || t.includes('cài đặt thước')
                || t.includes('publish now') || t.includes('đăng ngay');
        }"""))

    async def _wait_next_enabled(self, page: Page, seconds: int = 50) -> bool:
        for _ in range(seconds):
            ready = await page.evaluate("""() => {
                const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]')).filter(d => {
                    const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                    return !aria.includes('notification');
                });
                const d = dialogs[dialogs.length - 1];
                if (!d) return false;
                const btns = Array.from(d.querySelectorAll('div[role="button"], button')).filter(b => {
                    const aria = (b.getAttribute('aria-label') || '').toLowerCase().trim();
                    const text = (b.innerText || '').toLowerCase().trim();
                    return aria === 'next' || aria === 'tiếp' || text === 'next' || text === 'tiếp'
                        || text === 'tiếp tục' || text === 'tiếp theo';
                });
                const b = btns[btns.length - 1];
                if (!b) return false;
                return b.getAttribute('aria-disabled') !== 'true' && !b.disabled;
            }""")
            if ready:
                return True
            await asyncio.sleep(1)
        return False

    async def _goto_reel_settings(self, page: Page) -> bool:
        """Hai lần Next: Create → Edit → Reel settings. Đợi copyright xong."""
        for step in range(6):
            if await self._on_reel_settings(page):
                logger.info(f"Facebook đã tới Reel settings (step={step}).", "FACEBOOK")
                for _ in range(40):
                    blob = (await page.evaluate("""() => {
                        const d = Array.from(document.querySelectorAll('div[role="dialog"]')).pop();
                        return (d && d.innerText) || '';
                    }""") or "").lower()
                    if "safe to publish" in blob or "an toàn" in blob:
                        logger.info("Facebook: video an toàn để đăng (copyright xong).", "FACEBOOK")
                        break
                    await asyncio.sleep(1)
                return True
            nxt = await self._click_next_only(page)
            if nxt:
                logger.info(f"Facebook Reel bước tiếp: '{nxt}'", "FACEBOOK")
            await asyncio.sleep(1.8)
        return await self._on_reel_settings(page)

    async def _fill_caption(self, page: Page, caption: str):
        editor = page.locator(
            'div[role="dialog"] div[role="textbox"][aria-placeholder*="Describe"], '
            'div[role="dialog"] div[role="textbox"][aria-placeholder*="mô tả"], '
            'div[role="dialog"] div[role="textbox"][aria-placeholder*="thước"], '
            'div[role="dialog"] div[contenteditable="true"]'
        ).first
        if await editor.is_visible(timeout=8000):
            await editor.click(force=True)
            await page.keyboard.type(caption, delay=20)
            logger.info("Đã điền mô tả Facebook Reel (Reel settings).", "FACEBOOK")
            await asyncio.sleep(0.8)

    async def _open_schedule_ui(self, page: Page) -> bool:
        """Bấm Publish now / Đăng ngay (dropdown). Không bấm heading Scheduling options / empty-state."""
        opened = await page.evaluate("""() => {
            const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]')).filter(d => {
                const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                return !aria.includes('notification');
            });
            const d = dialogs[dialogs.length - 1];
            if (!d) return false;
            Array.from(d.querySelectorAll('div')).forEach(el => {
                if (el.scrollHeight > el.clientHeight + 40) el.scrollTop = el.scrollHeight;
            });
            const firstLine = (el) => ((el.innerText || '').split('\\n')[0] || '').trim().toLowerCase();
            const els = Array.from(d.querySelectorAll('div[role="button"], button, span'));
            const pub = els.find(el => {
                const t = firstLine(el);
                return t === 'publish now' || t === 'đăng ngay' || t === 'đăng ngay lập tức';
            });
            if (pub) { pub.click(); return true; }
            return false;
        }""")
        await asyncio.sleep(1.5)
        if opened:
            logger.info("Đã bấm Publish now / Đăng ngay để mở Scheduling options.", "FACEBOOK")
        return bool(opened)

    async def _dump_schedule_debug(self, page: Page) -> str:
        try:
            return await page.evaluate("""() => {
                const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]')).filter(d => {
                    const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                    return !aria.includes('notification');
                });
                const d = dialogs[dialogs.length - 1];
                if (!d) return 'no-dialog';
                const fields = Array.from(d.querySelectorAll('input, [role="combobox"]')).map(el => ({
                    tag: el.tagName, type: el.getAttribute('type') || '',
                    role: el.getAttribute('role') || '',
                    aria: el.getAttribute('aria-label') || '',
                    label: (el.getAttribute('aria-label') || ''),
                    value: el.value || '',
                }));
                return JSON.stringify({ text: (d.innerText || '').slice(0, 1200), fields });
            }""")
        except Exception as e:
            return str(e)

    async def _fill_schedule_fields(self, page: Page, native: Dict[str, Any]) -> bool:
        date_fb = _fb_date_label(native)
        time_str = native["time"]

        date_box = page.locator(
            'div[role="dialog"] label:has-text("Date") input[role="combobox"], '
            'div[role="dialog"] label:has-text("Ngày") input[role="combobox"], '
            'div[role="dialog"] input[role="combobox"][aria-label="Date"], '
            'div[role="dialog"] input[role="combobox"][aria-label="Ngày"]'
        ).first
        time_box = page.locator(
            'div[role="dialog"] label:has-text("Time") input[role="combobox"], '
            'div[role="dialog"] label:has-text("Giờ") input[role="combobox"], '
            'div[role="dialog"] input[role="combobox"][aria-label="Time"], '
            'div[role="dialog"] input[role="combobox"][aria-label="Giờ"]'
        ).first

        date_ok = False
        if await date_box.is_visible(timeout=5000):
            await date_box.click(force=True)
            await asyncio.sleep(0.3)
            try:
                await date_box.fill(date_fb)
            except Exception:
                await page.keyboard.press("Control+A")
                await page.keyboard.type(date_fb, delay=35)
            await date_box.evaluate(
                """el => {
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }"""
            )
            date_ok = True
            await date_box.press("Tab")
            await asyncio.sleep(0.6)

        time_ok = False
        if await time_box.is_visible(timeout=4000):
            await time_box.click(force=True)
            await asyncio.sleep(0.3)
            try:
                await time_box.fill(time_str)
            except Exception:
                await page.keyboard.press("Control+A")
                await page.keyboard.type(time_str, delay=35)
            await time_box.evaluate(
                """el => {
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }"""
            )
            time_ok = True
            await time_box.press("Tab")
            await asyncio.sleep(0.6)

        # Đóng overlay calendar: bấm helper text (bản ghi). Không Escape — Escape đóng cả Scheduling options.
        helper_ok = await page.evaluate("""() => {
            const spans = Array.from(document.querySelectorAll('div[role="dialog"] span, div[role="dialog"] div'));
            const hit = spans.find(el => {
                const t = (el.innerText || '').trim();
                if (t.length > 180) return false;
                const low = t.toLowerCase();
                return low.includes('choose a date and time in the future')
                    || low.includes('chọn ngày và giờ');
            });
            if (hit) { hit.click(); return true; }
            return false;
        }""")
        if helper_ok:
            logger.info("Đã bấm helper text để đóng overlay lịch.", "FACEBOOK")
            await asyncio.sleep(1.2)
        else:
            logger.warning("Không thấy helper text đóng lịch — vẫn thử Schedule for later.", "FACEBOOK")

        logger.info(
            f"Facebook Date/Time fill date={date_ok} time={time_ok} want={date_fb} {time_str}",
            "FACEBOOK",
        )
        return bool(date_ok and time_ok)

    async def _scheduling_panel_open(self, page: Page) -> bool:
        return bool(await page.evaluate("""() => {
            const t = (document.body.innerText || '').toLowerCase();
            return t.includes('schedule for later') || t.includes('lên lịch sau');
        }"""))

    async def _click_schedule_for_later(self, page: Page) -> bool:
        for attempt in range(3):
            if not await self._scheduling_panel_open(page):
                logger.info(f"Scheduling options đóng — mở lại Publish now (lần {attempt + 1}).", "FACEBOOK")
                await self._open_schedule_ui(page)
                await asyncio.sleep(1)
            btn = page.locator(
                'div[role="dialog"] span:has-text("Schedule for later"), '
                'div[role="dialog"] span:has-text("Lên lịch sau")'
            ).first
            try:
                if await btn.is_visible(timeout=4000):
                    await btn.click(force=True)
                    logger.info("Đã bấm Schedule for later.", "FACEBOOK")
                    await asyncio.sleep(3.0)
                    return True
            except Exception:
                pass
            clicked = await page.evaluate("""() => {
                const els = Array.from(document.querySelectorAll('div[role="button"], button, span'));
                const hit = els.find(el => {
                    const t = (el.innerText || '').trim().toLowerCase();
                    return t === 'schedule for later' || t === 'lên lịch sau';
                });
                if (hit) { hit.click(); return true; }
                return false;
            }""")
            if clicked:
                logger.info("Đã bấm Schedule for later (JS).", "FACEBOOK")
                await asyncio.sleep(3.0)
                return True
            await asyncio.sleep(0.8)
        return False

    async def _click_footer_schedule(self, page: Page) -> bool:
        """Nút Schedule ở chân Reel settings (thay Post). Không bấm Post/Đăng."""
        for _ in range(15):
            for name in ("Schedule", "Lên lịch"):
                btn = page.get_by_role("button", name=name, exact=True).last
                try:
                    if await btn.is_visible(timeout=400):
                        await btn.click(force=True)
                        logger.info(f"Đã bấm Schedule footer (role exact='{name}').", "FACEBOOK")
                        await asyncio.sleep(4)
                        return True
                except Exception:
                    pass
            label = await page.evaluate("""() => {
                const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]')).filter(d => {
                    const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                    return !aria.includes('notification');
                });
                const d = dialogs.find(x => {
                    const t = (x.innerText || '').toLowerCase();
                    return t.includes('reel settings') || t.includes('cài đặt thước');
                }) || dialogs[dialogs.length - 1];
                if (!d) return '';
                const btns = Array.from(d.querySelectorAll('div[role="button"], button'));
                const hit = btns.find(el => {
                    const t = (el.innerText || '').trim().toLowerCase();
                    const first = t.split('\\n')[0].trim();
                    if (t.includes('schedule a post') || t.includes('schedule for later') || t.includes('lên lịch sau')) {
                        return false;
                    }
                    if (first === 'post' || first === 'đăng' || first === 'share' || first === 'chia sẻ') return false;
                    return first === 'schedule' || first === 'lên lịch';
                });
                if (!hit) return '';
                if (hit.getAttribute('aria-disabled') === 'true') return 'disabled';
                hit.click();
                return (hit.innerText || 'schedule').trim().slice(0, 40);
            }""")
            if label and label != "disabled":
                logger.info(f"Đã bấm Schedule footer: '{label}'", "FACEBOOK")
                await asyncio.sleep(4)
                return True
            await asyncio.sleep(0.8)
        return False

    async def _wait_schedule_processing(self, page: Page):
        """Đợi overlay Scheduling / hộp Reel settings đóng — không rời trang khi Facebook còn xử lý."""
        for _ in range(50):
            state = await page.evaluate("""() => {
                const t = (document.body.innerText || '').toLowerCase();
                const overlay = t.includes('scheduling') && !t.includes('scheduling options');
                const reel = Array.from(document.querySelectorAll('div[role="dialog"]')).some(d => {
                    const aria = (d.getAttribute('aria-label') || '').toLowerCase();
                    if (aria.includes('notification')) return false;
                    const x = (d.innerText || '').toLowerCase();
                    return x.includes('reel settings') || x.includes('cài đặt thước');
                });
                return { overlay, reel };
            }""")
            if not state.get("reel"):
                logger.info("Hộp Reel settings đã đóng sau khi Schedule.", "FACEBOOK")
                return
            if state.get("overlay"):
                await asyncio.sleep(1)
                continue
            await asyncio.sleep(1)
        logger.warning("Hết thời gian chờ overlay Scheduling — vẫn sang Content Library.", "FACEBOOK")

    async def _click_scheduled_tab(self, page: Page):
        for name in ("Scheduled", "Đã lên lịch"):
            tab = page.get_by_role("tab", name=name, exact=True)
            try:
                if await tab.is_visible(timeout=1500):
                    await tab.click(force=True)
                    await asyncio.sleep(1.5)
                    return
            except Exception:
                pass
        try:
            clicked = await page.evaluate("""() => {
                const tabs = Array.from(document.querySelectorAll('[role="tab"], div[role="button"], button, span'));
                const hit = tabs.find(el => {
                    const t = (el.innerText || '').trim().toLowerCase();
                    return t === 'scheduled' || t === 'đã lên lịch';
                });
                if (hit) { hit.click(); return true; }
                return false;
            }""")
            if clicked:
                await asyncio.sleep(1.5)
        except Exception:
            pass

    async def _library_has_post_row(self, page: Page, caption: str = "") -> bool:
        markers = (
            "Scheduled • Tomorrow at 10:00",
            "Tomorrow at 10:00",
            "Scheduled •",
            "Ngày mai lúc 10:00",
            "Ngày mai lúc",
            "Scheduled",
            "Đã lên lịch",
        )
        for m in markers:
            loc = page.get_by_text(m, exact=False).first
            try:
                if await loc.is_visible(timeout=1200):
                    return True
            except Exception:
                pass
        snippet = ((caption or "").split("\n")[0] or "").strip()[:16]
        if snippet:
            loc = page.get_by_text(snippet, exact=False).first
            try:
                if await loc.is_visible(timeout=800):
                    empty = page.get_by_text("No scheduled posts", exact=False).first
                    if await empty.is_visible(timeout=400):
                        return False
                    return True
            except Exception:
                pass
        return False

    async def _confirm_in_library(self, page: Page, native: Dict[str, Any], caption: str = "") -> bool:
        try:
            if "content_library" not in page.url:
                await page.goto(FB_LIBRARY_SCHEDULED, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4)
                await self._dismiss_fb_popups(page)
            await self._click_scheduled_tab(page)
            for _ in range(8):
                if await self._library_has_post_row(page, caption):
                    return True
                await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Lỗi khi xác nhận thư viện: {e}", "FACEBOOK")
        return False

    def _is_fb_permalink(self, url: str) -> bool:
        u = (url or "").strip()
        low = u.lower()
        if "facebook.com" not in low and "fb.watch" not in low and "fb.me" not in low:
            return False
        if "content_library" in low or "professional_dashboard/content" in low:
            return False
        return True

    def _read_os_clipboard(self) -> str:
        import ctypes
        try:
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if not user32.OpenClipboard(None):
                return ""
            try:
                h_mem = user32.GetClipboardData(CF_UNICODETEXT)
                if not h_mem:
                    return ""
                p_mem = kernel32.GlobalLock(h_mem)
                if not p_mem:
                    return ""
                try:
                    return (ctypes.c_wchar_p(p_mem).value or "").strip()
                finally:
                    kernel32.GlobalUnlock(h_mem)
            finally:
                user32.CloseClipboard()
        except Exception:
            return ""

    async def _read_fb_clipboard(self, page: Page) -> str:
        # 1. Direct OS clipboard read (instant, 100% reliable on Windows)
        clip = self._read_os_clipboard()
        if clip:
            return clip

        # 2. Browser clipboard with hard timeout (prevents hanging in Firefox/Camoufox)
        try:
            await page.context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://www.facebook.com",
            )
        except Exception:
            pass
        try:
            text = await asyncio.wait_for(
                page.evaluate(
                    """async () => {
                        try {
                            if (!navigator.clipboard || !navigator.clipboard.readText) return '';
                            const timeout = new Promise(resolve => setTimeout(() => resolve(''), 1500));
                            return await Promise.race([navigator.clipboard.readText().catch(() => ''), timeout]);
                        } catch (e) { return ''; }
                    }"""
                ),
                timeout=2.5,
            )
            return (text or "").strip()
        except Exception:
            return ""

    async def _open_scheduled_row_menu(self, page: Page, caption: str) -> bool:
        result = await page.evaluate(
            """() => {
                const nodes = Array.from(document.querySelectorAll('span, div'));
                const status = nodes.find(el => {
                    const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (t.length > 80) return false;
                    const low = t.toLowerCase();
                    return low.includes('tomorrow at') || low.includes('ngày mai lúc')
                        || /^scheduled\\s*[•·]/.test(low);
                });
                if (!status) return 'no-status';
                const sr = status.getBoundingClientRect();
                if (sr.width < 4 || sr.height < 4) return 'status-hidden';
                const midY = (sr.top + sr.bottom) / 2;
                const btns = Array.from(document.querySelectorAll('div[role="button"], button')).filter(el => {
                    const r = el.getBoundingClientRect();
                    if (r.width < 12 || r.height < 12) return false;
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    if (aria.includes('create') || aria.includes('tạo')) return false;
                    return Math.abs((r.top + r.bottom) / 2 - midY) < 32;
                });
                btns.sort((a, b) => b.getBoundingClientRect().left - a.getBoundingClientRect().left);
                const hit = btns[0];
                if (!hit) return 'no-btn';
                hit.click();
                return 'ok:' + (hit.getAttribute('aria-label') || hit.getAttribute('aria-haspopup') || 'dot');
            }"""
        )
        logger.info(f"Menu ba chấm hàng Scheduled: {result}", "FACEBOOK")
        return isinstance(result, str) and result.startswith("ok:")

    async def _click_copy_link_item(self, page: Page) -> bool:
        names = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('[role="menuitem"]')).map(el => {
                return ((el.innerText || '').split('\\n')[0] || '').trim();
            }).filter(Boolean).slice(0, 15);
        }""")
        logger.info(f"Menu bài Scheduled: {names}", "FACEBOOK")
        for name in ("Copy link", "Sao chép liên kết"):
            item = page.get_by_role("menuitem", name=name, exact=True)
            try:
                if await item.is_visible(timeout=2000):
                    await item.click(force=True)
                    return True
            except Exception:
                pass
        return bool(await page.evaluate("""() => {
            const items = Array.from(document.querySelectorAll('[role="menuitem"], div[role="none"]'));
            const hit = items.find(el => {
                const first = ((el.innerText || '').split('\\n')[0] || '').trim().toLowerCase();
                return first === 'copy link' || first === 'sao chép liên kết';
            });
            if (hit) { hit.click(); return true; }
            return false;
        }"""))

    async def _copy_scheduled_post_link(self, page: Page, caption: str) -> str:
        """Chờ Facebook tạo permalink, làm tươi tab Scheduled, Copy link bài vừa hẹn."""
        logger.info("Chờ Facebook tạo link bài vừa lên lịch, rồi làm tươi Content Library...", "FACEBOOK")
        await asyncio.sleep(20)
        try:
            await page.context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://www.facebook.com",
            )
        except Exception:
            pass

        for attempt in range(8):
            logger.info(f"Làm tươi tab Scheduled để Copy link (lần {attempt + 1}/8)...", "FACEBOOK")
            await page.goto(FB_LIBRARY_SCHEDULED, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(5)
            await self._dismiss_fb_popups(page)
            await self._click_scheduled_tab(page)

            if not await self._library_has_post_row(page, caption) and not await self._library_has_post_row(page, ""):
                logger.warning("Tab Scheduled vẫn trống — chờ rồi tải lại.", "FACEBOOK")
                await self._shot(page, f"fb_library_empty_{attempt}")
                await asyncio.sleep(12)
                continue

            opened = await self._open_scheduled_row_menu(page, caption)
            if not opened:
                opened = await self._open_scheduled_row_menu(page, "")
            if not opened:
                logger.warning("Chưa thấy nút ba chấm trên hàng bài Scheduled.", "FACEBOOK")
                await self._shot(page, f"fb_row_menu_fail_{attempt}")
                await asyncio.sleep(12)
                continue

            await asyncio.sleep(1.2)
            if not await self._click_copy_link_item(page):
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                logger.warning("Menu hàng bài đã mở nhưng chưa có Copy link — chờ rồi tải lại.", "FACEBOOK")
                await self._shot(page, f"fb_copy_link_missing_{attempt}")
                await asyncio.sleep(12)
                continue

            await asyncio.sleep(1.5)
            url = await self._read_fb_clipboard(page)
            if self._is_fb_permalink(url):
                logger.success(f"Đã Copy link Facebook: {url}", "FACEBOOK")
                return url
            logger.warning(f"Clipboard chưa có permalink Facebook (got={url[:120]!r}).", "FACEBOOK")
            await asyncio.sleep(12)

        await self._shot(page, "fb_copy_link_fail")
        return ""

    async def post_video(
        self,
        page: Page,
        video_data: Dict[str, Any],
        privacy_override: Optional[str] = None,
        schedule_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        file_path = video_data.get("file_path", "")
        if not self.validate_video_file(file_path):
            return {"success": False, "error": "File video không hợp lệ"}

        caption = self.format_caption(video_data)
        native = get_native_schedule(schedule_time or "")

        fb_cfg = config_manager.get_platform_config("facebook")
        target_type = fb_cfg.get("target_type", "personal")
        page_url = fb_cfg.get("page_url", "")
        page_name = fb_cfg.get("page_name", "")

        try:
            if target_type == "fanpage":
                if not page_url:
                    logger.warning(
                        "⚠️ Facebook đang ở chế độ Fanpage nhưng chưa chọn trang mục tiêu cụ thể. "
                        "Bỏ qua đăng Facebook lần này (vui lòng vào Dashboard chọn Fanpage)!",
                        "FACEBOOK",
                    )
                    return {"success": True, "skipped": True, "error": "Chưa chọn Fanpage mục tiêu trên Dashboard"}

                logger.info(f"Chuẩn bị đăng lên Facebook Fanpage: {page_name} ({page_url})", "FACEBOOK")
                switched = await self._ensure_switched_to_fanpage(page, page_url)
                if not switched:
                    logger.warning(f"Không thể xác nhận chuyển sang Fanpage {page_url}, tiếp tục mở Professional Dashboard...", "FACEBOOK")
            else:
                logger.info("Chuẩn bị đăng lên Facebook Trang cá nhân...", "FACEBOOK")
                await self._ensure_switched_to_personal(page)

            logger.info(f"Mở Facebook Professional Dashboard: {FB_PRODASH_URL}", "FACEBOOK")
            if "professional_dashboard" not in page.url:
                await page.goto(FB_PRODASH_URL, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4)
                await self._dismiss_fb_popups(page, press_escape=False)

            if not await self._wait_login(page):
                logger.error("Hết thời gian chờ đăng nhập Facebook (5 phút). Vui lòng đăng nhập trước!", "FACEBOOK")
                return {"success": False, "error": "Hết thời gian chờ đăng nhập Facebook"}

            if not await self._click_create_reel(page):
                logger.error("Không mở được Create → Reel trên Professional Dashboard.", "FACEBOOK")
                await self._shot(page, "fb_create_reel_fail")
                return await fail_with_ai(
                    page, "facebook",
                    "Không tìm thấy Create → Reel trên Professional Dashboard.",
                    goal=SCHEDULE_GOAL,
                )

            if not await self._reel_dialog_ready(page):
                logger.error("Hộp thoại Create reel không hiện.", "FACEBOOK")
                await self._shot(page, "fb_create_dialog_fail")
                return await fail_with_ai(
                    page, "facebook",
                    "Hộp thoại Create reel không hiện sau khi bấm Create → Reel.",
                    goal=SCHEDULE_GOAL,
                )

            file_input = page.locator(
                'div[role="dialog"] input[type="file"][accept*="video"], '
                'div[role="dialog"] input[type="file"]'
            ).first
            await file_input.wait_for(state="attached", timeout=15000)
            await file_input.set_input_files(os.path.abspath(file_path))
            logger.info("Đã đính kèm tệp video lên Facebook Reel...", "FACEBOOK")
            await asyncio.sleep(3)
            if not await self._wait_next_enabled(page, seconds=50):
                logger.warning("Nút Next Facebook vẫn disabled sau khi tải video — vẫn thử tiếp.", "FACEBOOK")

            if not native["enabled"]:
                logger.error("schedule_publish đang tắt — không đăng Facebook công khai ngay.", "FACEBOOK")
                return await fail_with_ai(
                    page, "facebook",
                    "schedule_publish tắt; không bấm Post trên Facebook.",
                    goal=SCHEDULE_GOAL,
                )

            if not await self._goto_reel_settings(page):
                await self._shot(page, "fb_reel_settings_fail")
                dump = await self._dump_schedule_debug(page)
                logger.error(f"Không tới được Reel settings. Dump={dump[:700]}", "FACEBOOK")
                return await fail_with_ai(
                    page, "facebook",
                    "Không tới được bước Reel settings sau 2 lần Next.",
                    goal=SCHEDULE_GOAL,
                )

            try:
                await self._fill_caption(page, caption)
            except Exception as e:
                logger.warning(f"Lưu ý khi điền caption Facebook: {e}", "FACEBOOK")

            opened = await self._open_schedule_ui(page)
            if not opened:
                await self._shot(page, "fb_publish_now_fail")
                dump = await self._dump_schedule_debug(page)
                logger.error(f"Không bấm được Publish now. Dump={dump[:700]}", "FACEBOOK")
                return await fail_with_ai(
                    page, "facebook",
                    "Không mở được Scheduling options từ Publish now (không đăng ngay).",
                    goal=SCHEDULE_GOAL,
                )

            if not await self._fill_schedule_fields(page, native):
                dump = await self._dump_schedule_debug(page)
                await self._shot(page, "fb_schedule_fail")
                logger.error(f"Facebook không điền được Date/Time. Dump={dump[:900]}", "FACEBOOK")
                return await fail_with_ai(
                    page, "facebook",
                    "Không điền được combobox Date/Time trên Scheduling options (không đăng ngay).",
                    goal=SCHEDULE_GOAL,
                )

            if not await self._click_schedule_for_later(page):
                dump = await self._dump_schedule_debug(page)
                await self._shot(page, "fb_schedule_later_fail")
                logger.error(f"Không bấm được Schedule for later. Dump={dump[:900]}", "FACEBOOK")
                return await fail_with_ai(
                    page, "facebook",
                    "Đã điền ngày/giờ nhưng không bấm được Schedule for later.",
                    goal=SCHEDULE_GOAL,
                )

            if not await self._click_footer_schedule(page):
                dump = await self._dump_schedule_debug(page)
                await self._shot(page, "fb_schedule_footer_fail")
                logger.error(f"Không bấm được Schedule footer. Dump={dump[:900]}", "FACEBOOK")
                return await fail_with_ai(
                    page, "facebook",
                    "Đã Schedule for later nhưng không bấm được nút Schedule ở chân (không bấm Post).",
                    goal=SCHEDULE_GOAL,
                )

            logger.info("Đã bấm Schedule Facebook. Đợi Facebook xử lý xong rồi xác nhận thư viện...", "FACEBOOK")
            await self._shot(page, "fb_after_footer_schedule")
            await self._wait_schedule_processing(page)
            await asyncio.sleep(3)

            ok = await self._confirm_in_library(page, native, caption)

            if not ok:
                logger.warning(
                    "Chưa thấy ngay hàng bài trong tab Scheduled của Content Library "
                    "(Facebook có thể đang mã hóa video ngầm). Vẫn ghi nhận thành công vì hộp thoại Schedule đã đóng hoàn tất.",
                    "FACEBOOK",
                )
                await self._shot(page, "fb_library_unconfirmed")
            else:
                logger.success(
                    f"Đã lên lịch Facebook (Professional Dashboard) công khai lúc {native['label']}!",
                    "FACEBOOK",
                )

            post_url = ""
            if ok:
                post_url = await self._copy_scheduled_post_link(page, caption)
            if not post_url:
                logger.info(
                    "Lưu URL Content Library làm link bài viết Facebook.",
                    "FACEBOOK",
                )
            return {"success": True, "url": post_url or FB_LIBRARY_SCHEDULED, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên Facebook: {str(ex)}", "FACEBOOK")
            await self._shot(page, "fb_exception")
            return await fail_with_ai(page, "facebook", str(ex), goal=SCHEDULE_GOAL)


facebook_poster = FacebookPoster()
