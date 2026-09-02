import os
import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import Page
from automation.posters.base_poster import BasePoster
from core.logger import logger
from core.config_manager import config_mgr
from core.schedule_helper import get_native_schedule
from automation.ai_fallback import fail_with_ai, SCHEDULE_GOAL

TT_CONTENT = "https://www.tiktok.com/tiktokstudio/content"
TT_UPLOAD = "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video"
SHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "debug_screenshots")


class TikTokPoster(BasePoster):
    def __init__(self):
        super().__init__("TikTok")

    async def _shot(self, page: Page, name: str):
        try:
            os.makedirs(SHOT_DIR, exist_ok=True)
            path = os.path.join(SHOT_DIR, f"{name}.png")
            await page.screenshot(path=path)
            logger.info(f"Ảnh TikTok: {path}", "TIKTOK")
        except Exception:
            pass

    async def _dismiss_overlays(self, page: Page, allow_discard: bool = False):
        """Xóa overlay joyride / popup hướng dẫn. Không bấm Hủy bỏ (Cancel) trên form."""
        try:
            try:
                exit_dlg = page.locator('text=Are you sure you want to exit, text=Bạn có chắc muốn thoát').first
                if await exit_dlg.is_visible(timeout=400):
                    cancel = page.locator(
                        'div[role="dialog"] button:has-text("Cancel"), '
                        'div[role="dialog"] button:has-text("Hủy"), '
                        'div[role="dialog"] button:has-text("Huỷ")'
                    ).first
                    if await cancel.is_visible(timeout=500):
                        await cancel.click(force=True)
                        await asyncio.sleep(0.4)
            except Exception:
                pass

            try:
                for sel in (
                    'button:has-text("Got it")', 'button:has-text("Đã hiểu")',
                    'button:has-text("Skip")', 'button:has-text("Bỏ qua")',
                    'button:has-text("Edit now")', 'button:has-text("Chỉnh sửa ngay")',
                ):
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=400):
                        await btn.click(force=True)
                        await asyncio.sleep(0.3)
            except Exception:
                pass

            if allow_discard:
                await self._confirm_discard_dialog(page)

            await page.evaluate("""() => {
                const joyrides = document.querySelectorAll('#react-joyride-portal, .react-joyride__overlay, [data-test-id="overlay"], .tiktok-modal__mask');
                joyrides.forEach(el => el.remove());
            }""")
        except Exception:
            pass

    async def _confirm_discard_dialog(self, page: Page) -> bool:
        """Bấm Discard trong hộp 'Discard this post?' — không bấm Not now / Hủy bỏ."""
        clicked = await page.evaluate("""() => {
            const firstLine = (el) => ((el.innerText || '').split('\\n')[0] || '').trim().toLowerCase();
            const nodes = Array.from(document.querySelectorAll('[role="dialog"], [class*="Modal"], [class*="modal"]'));
            const d = nodes.find(el => {
                const t = (el.innerText || '').toLowerCase();
                return t.includes('discard this post') || t.includes('hủy bài đăng')
                    || t.includes('huỷ bài đăng') || t.includes('hủy bài viết')
                    || t.includes('bỏ bài đăng này') || t.includes('discard this');
            });
            if (!d) return false;
            const btns = Array.from(d.querySelectorAll('button'));
            const hit = btns.find(b => {
                const t = firstLine(b);
                if (t === 'not now' || t === 'để sau' || t === 'hủy bỏ' || t === 'huỷ bỏ' || t === 'cancel') {
                    return false;
                }
                return t === 'discard' || t === 'hủy' || t === 'huỷ' || t === 'xóa' || t === 'xoá';
            });
            if (hit) { hit.click(); return true; }
            return false;
        }""")
        if clicked:
            logger.info("Đã bấm Discard trên hộp bản nháp video trước.", "TIKTOK")
            await asyncio.sleep(2.0)
        return bool(clicked)

    async def _ensure_clean_upload(self, page: Page):
        """Xóa form dở của video trước: dialog Discard, hoặc Hủy bỏ rồi Discard."""
        if await self._confirm_discard_dialog(page):
            await asyncio.sleep(1)
            if "upload" not in page.url:
                await self._open_upload(page)
            return

        leftover = await page.locator(
            'button:has-text("Replace"), button:has-text("Thay thế"), '
            '.caption-editor [contenteditable="true"]'
        ).first.is_visible(timeout=2000)

        if leftover:
            cancel = page.locator(
                'button:has-text("Hủy bỏ"), button:has-text("Huỷ bỏ"), '
                'button:has-text("Cancel")'
            ).last
            try:
                if await cancel.is_visible(timeout=2000):
                    await cancel.click(force=True)
                    logger.info("Đã bấm Hủy bỏ form video trước để mở hộp Discard.", "TIKTOK")
                    await asyncio.sleep(1.0)
            except Exception:
                pass
            if await self._confirm_discard_dialog(page):
                await asyncio.sleep(1)
                if "upload" not in page.url:
                    await self._open_upload(page)
                return
            await asyncio.sleep(0.6)
            await self._confirm_discard_dialog(page)
            if "upload" not in page.url:
                await self._open_upload(page)

    async def _wait_login(self, page: Page) -> bool:
        login_needed = "login" in page.url or await page.locator(
            'button:has-text("Log in"), button:has-text("Đăng nhập")'
        ).first.is_visible(timeout=4000)
        if not login_needed:
            return True

        logger.warning(
            "👉 Chưa đăng nhập TikTok! Vui lòng hoàn tất đăng nhập trên cửa sổ trình duyệt "
            "(hệ thống sẽ tự động chờ tối đa 5 phút)...",
            "TIKTOK",
        )
        try:
            await page.bring_to_front()
        except Exception:
            pass

        for sec in range(0, 300, 3):
            if sec > 0 and sec % 30 == 0:
                logger.info(f"⏳ [TIKTOK] Đang chờ bạn đăng nhập... (Đã qua {sec}/300s)", "TIKTOK")
            await asyncio.sleep(3)
            await self._dismiss_overlays(page)
            if "login" not in page.url and not await page.locator(
                'button:has-text("Log in"), button:has-text("Đăng nhập")'
            ).first.is_visible(timeout=1000):
                return True
        return False

    async def _open_upload(self, page: Page) -> bool:
        """Từ Content Library bấm Tải lên / Upload (bản ghi action-002)."""
        for name in ("Tải lên", "Upload"):
            btn = page.get_by_role("button", name=name, exact=True)
            try:
                if await btn.is_visible(timeout=4000):
                    await btn.click(force=True)
                    logger.info("Đã bấm Tải lên / Upload trên TikTok Studio.", "TIKTOK")
                    await asyncio.sleep(3)
                    return True
            except Exception:
                pass
        clicked = await page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const hit = btns.find(b => {
                const t = ((b.innerText || '').split('\\n')[0] || '').trim().toLowerCase();
                return t === 'tải lên' || t === 'upload';
            });
            if (hit) { hit.click(); return true; }
            return false;
        }""")
        if clicked:
            await asyncio.sleep(3)
        return bool(clicked)

    async def _fill_caption(self, page: Page, caption: str):
        editor = page.locator(
            '.caption-editor [contenteditable="true"][role="combobox"], '
            'div.public-DraftEditor-content[contenteditable="true"], '
            'div[contenteditable="true"][role="combobox"]'
        ).first
        if not await editor.is_visible(timeout=25000):
            logger.warning("Không thấy ô mô tả TikTok.", "TIKTOK")
            return
        await editor.click(force=True)
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.4)
        await page.keyboard.type(caption, delay=18)
        logger.info("Đã điền mô tả TikTok.", "TIKTOK")
        await asyncio.sleep(0.6)
        # Đóng gợi ý hashtag: bấm nhãn Mô tả (bản ghi action-011)
        title = page.locator(
            '.caption-title:has-text("Mô tả"), .caption-title:has-text("Description"), '
            'span:has-text("Mô tả"), span:has-text("Description")'
        ).first
        try:
            if await title.is_visible(timeout=1500):
                await title.click(force=True)
                await asyncio.sleep(0.4)
        except Exception:
            pass

    async def _select_schedule_radio(self, page: Page) -> bool:
        """Radio Lên lịch trong Thời điểm đăng — không bấm Bây giờ, không bấm footer."""
        try:
            lab = page.locator(
                '[data-e2e="schedule_container"] label:has-text("Lên lịch"), '
                '.schedule-radio-container label:has-text("Lên lịch"), '
                '[data-e2e="schedule_container"] label:has-text("Schedule"), '
                '.schedule-radio-container label:has-text("Schedule")'
            ).first
            if await lab.is_visible(timeout=4000):
                await lab.click(force=True)
                await asyncio.sleep(0.8)
                logger.info("Đã bấm nhãn Lên lịch trong Thời điểm đăng.", "TIKTOK")
                return True
        except Exception:
            pass
        return bool(await page.evaluate("""() => {
            const input = document.querySelector('input[name="postSchedule"][value="schedule"]');
            if (input) { input.click(); return true; }
            const root = document.querySelector('[data-e2e="schedule_container"]') || document.body;
            const lab = Array.from(root.querySelectorAll('label')).find(el => {
                const t = (el.innerText || '').trim();
                return t === 'Lên lịch' || t === 'Schedule';
            });
            if (lab) { lab.click(); return true; }
            return false;
        }"""))

    async def _set_time_picker(self, page: Page, native: Dict[str, Any]) -> bool:
        hour = f"{int(native['hour']):02d}" if int(native["hour"]) >= 10 else str(int(native["hour"]))
        # Picker dùng '10' và '00' (không zero-pad giờ 1–9 trên một số bản UI; record dùng 10)
        hour_txt = str(int(native["hour"]))
        min_txt = f"{int(native['minute']):02d}"

        time_input = page.locator('.scheduled-picker input').first
        if not await time_input.is_visible(timeout=4000):
            await self._select_schedule_radio(page)
            await asyncio.sleep(1.0)
        if not await time_input.is_visible(timeout=4000):
            logger.warning("Không thấy ô giờ .scheduled-picker — radio Lên lịch có thể chưa bật.", "TIKTOK")
            return False
        await time_input.click(force=True)
        await asyncio.sleep(0.6)

        hour_ok = await page.evaluate(
            """(hourTxt) => {
                const els = Array.from(document.querySelectorAll(
                    '.tiktok-timepicker-option-text.tiktok-timepicker-left'
                ));
                const padded = hourTxt.length === 1 ? '0' + hourTxt : hourTxt;
                const hit = els.find(el => {
                    const t = (el.innerText || '').trim();
                    return t === hourTxt || t === padded;
                });
                if (hit) { (hit.closest('.tiktok-timepicker-option-item') || hit).click(); return true; }
                return false;
            }""",
            hour_txt,
        )
        await asyncio.sleep(0.4)
        min_ok = await page.evaluate(
            """(minTxt) => {
                const els = Array.from(document.querySelectorAll(
                    '.tiktok-timepicker-option-text.tiktok-timepicker-right'
                ));
                const hit = els.find(el => (el.innerText || '').trim() === minTxt);
                if (hit) { (hit.closest('.tiktok-timepicker-option-item') || hit).click(); return true; }
                return false;
            }""",
            min_txt,
        )
        logger.info(f"TikTok time picker hour={hour_ok} min={min_ok} want={hour}:{min_txt}", "TIKTOK")
        return bool(hour_ok and min_ok)

    async def _set_date_picker(self, page: Page, native: Dict[str, Any]) -> bool:
        date_input = page.locator('.scheduled-picker input[readonly]').nth(1)
        if not await date_input.is_visible(timeout=4000):
            date_input = page.locator('.scheduled-picker input').nth(1)
        await date_input.click(force=True)
        await asyncio.sleep(0.6)
        day = str(int(native["day"]))
        clicked = await page.evaluate(
            """(dayTxt) => {
                const days = Array.from(document.querySelectorAll('span.day.valid, span.jsx-1793871833.day.valid'));
                const hit = days.find(el => (el.innerText || '').trim() === dayTxt);
                if (hit) { hit.click(); return true; }
                return false;
            }""",
            day,
        )
        logger.info(f"TikTok date picker day={clicked} want={day}", "TIKTOK")
        return bool(clicked)

    async def _picker_shows_time(self, page: Page, native: Dict[str, Any]) -> bool:
        want = native["time"]
        vals = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('.scheduled-picker input')).map(i => i.value || '');
        }""")
        blob = " ".join(vals or [])
        ok = want in blob or f"{int(native['hour'])}:{int(native['minute']):02d}" in blob
        logger.info(f"TikTok picker values={vals} want={want} ok={ok}", "TIKTOK")
        return bool(ok)

    async def _handle_continue_to_post(self, page: Page) -> bool:
        """Hộp 'Continue to post?' ngoài dự kiến — bấm Post now trong dialog (xác nhận lịch đã chọn)."""
        for name in ("Continue to post?", "Continue to post", "Tiếp tục đăng?", "Tiếp tục đăng"):
            dlg = page.get_by_role("dialog").filter(has_text=name)
            try:
                if await dlg.is_visible(timeout=800):
                    for btn_name in ("Post now", "Đăng ngay"):
                        btn = dlg.get_by_role("button", name=btn_name, exact=True)
                        if await btn.is_visible(timeout=800):
                            await btn.click(force=True)
                            logger.info(
                                "TikTok: đã bấm Post now trên hộp Continue to post (không đổi radio Bây giờ).",
                                "TIKTOK",
                            )
                            await asyncio.sleep(2.5)
                            return True
            except Exception:
                pass
        clicked = await page.evaluate("""() => {
            const firstLine = (el) => ((el.innerText || '').split('\\n')[0] || '').trim().toLowerCase();
            const nodes = Array.from(document.querySelectorAll('[role="dialog"], div'));
            const d = nodes.find(x => {
                const t = (x.innerText || '');
                if (t.length > 900) return false;
                return (t.includes('Continue to post') || t.includes('Tiếp tục đăng'))
                    && (t.includes('Post now') || t.includes('Đăng ngay'));
            });
            if (!d) return false;
            const btn = Array.from(d.querySelectorAll('button')).find(b => {
                const t = firstLine(b);
                if (t === 'cancel' || t === 'hủy' || t === 'huỷ' || t === 'hủy bỏ') return false;
                return t === 'post now' || t === 'đăng ngay';
            });
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        if clicked:
            logger.info("TikTok: xác nhận hộp Continue to post (JS).", "TIKTOK")
            await asyncio.sleep(2.5)
        return bool(clicked)

    async def _dismiss_schedule_pickers(self, page: Page):
        """Bấm vùng Thời điểm đăng để đóng overlay picker (bản ghi action-021)."""
        try:
            box = page.locator('[data-e2e="schedule_container"], .scheduled-container').first
            if await box.is_visible(timeout=1500):
                await box.click(force=True, position={"x": 20, "y": 12})
                await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _click_footer_schedule(self, page: Page) -> bool:
        """Nút Lên lịch chân form (data-e2e=post_video_button). Không bấm Bây giờ / Đăng."""
        btn = page.locator('button[data-e2e="post_video_button"]').first
        await btn.wait_for(state="visible", timeout=35000)
        for _ in range(50):
            await self._dismiss_overlays(page)
            disabled = await btn.get_attribute("disabled")
            aria = await btn.get_attribute("aria-disabled")
            processing = await page.locator(
                'text=Uploading, text=Đang tải lên, text=Processing, text=Đang xử lý'
            ).first.is_visible(timeout=400)
            if disabled is None and aria != "true" and not processing:
                break
            await asyncio.sleep(1.5)
        label = ((await btn.inner_text()) or "").strip().split("\n")[0]
        low = label.lower()
        if low in ("post", "đăng", "post now", "đăng ngay", "bây giờ"):
            logger.error(f"Nút chân TikTok vẫn là '{label}' — không bấm Đăng ngay.", "TIKTOK")
            return False
        await btn.click(force=True)
        logger.info(f"Đã bấm nút chân TikTok: '{label}'", "TIKTOK")
        await asyncio.sleep(3)
        return True

    def _is_tt_permalink(self, url: str) -> bool:
        u = (url or "").strip()
        low = u.lower()
        if "tiktok.com" not in low:
            return False
        if "tiktokstudio" in low or "creator-center" in low:
            return False
        return "/video/" in low or "/@" in low

    async def _read_clipboard(self, page: Page) -> str:
        try:
            await page.context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://www.tiktok.com",
            )
        except Exception:
            pass
        try:
            text = await page.evaluate(
                """async () => {
                    try { return await navigator.clipboard.readText(); }
                    catch (e) { return ''; }
                }"""
            )
            return (text or "").strip()
        except Exception:
            return ""

    async def _click_posts_tab(self, page: Page):
        for name in ("Bài đăng", "Posts"):
            tab = page.get_by_text(name, exact=False).first
            try:
                if await tab.is_visible(timeout=1500):
                    await tab.click(force=True)
                    await asyncio.sleep(1)
                    return
            except Exception:
                pass

    async def _open_copy_on_scheduled_row(self, page: Page, caption: str) -> str:
        snippet = ((caption or "").split("\n")[0] or "").strip()[:18]
        return await page.evaluate(
            """(snippet) => {
                const nodes = Array.from(document.querySelectorAll('div, tr, li'));
                const rows = nodes.filter(el => {
                    const t = (el.innerText || '');
                    if (t.length < 20 || t.length > 900) return false;
                    const low = t.toLowerCase();
                    const timed = low.includes('10:00') || low.includes('sa') || low.includes('am')
                        || low.includes('lên lịch') || low.includes('scheduled');
                    if (!timed) return false;
                    if (snippet) {
                        const sn = snippet.toLowerCase().slice(0, 12);
                        if (sn && !low.includes(sn) && !timed) return false;
                    }
                    const btns = el.querySelectorAll('button');
                    return btns.length >= 2;
                });
                rows.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
                const row = rows[0];
                if (!row) return 'no-row';
                const btns = Array.from(row.querySelectorAll('button'));
                const copy = btns.find(el => {
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const title = (el.getAttribute('title') || '').toLowerCase();
                    const blob = aria + ' ' + title;
                    return blob.includes('copy') || blob.includes('link') || blob.includes('sao chép');
                });
                const hit = copy || btns[1];
                if (!hit) return 'no-btn';
                hit.click();
                return 'ok:' + (hit.getAttribute('aria-label') || 'icon');
            }""",
            snippet,
        )

    async def _copy_scheduled_post_link(self, page: Page, caption: str) -> str:
        """Chờ, làm tươi tab Bài đăng, copy link hàng vừa hẹn (cột Hành động)."""
        logger.info("Chờ TikTok tạo link bài vừa lên lịch, rồi làm tươi Bài đăng...", "TIKTOK")
        await asyncio.sleep(18)
        try:
            await page.context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://www.tiktok.com",
            )
        except Exception:
            pass

        for attempt in range(8):
            logger.info(f"Làm tươi TikTok Studio Content để Copy link (lần {attempt + 1}/8)...", "TIKTOK")
            await page.goto(TT_CONTENT, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            await self._dismiss_overlays(page)
            await self._click_posts_tab(page)

            opened = await self._open_copy_on_scheduled_row(page, caption)
            logger.info(f"Nút copy hàng Scheduled: {opened}", "TIKTOK")
            if not isinstance(opened, str) or not opened.startswith("ok:"):
                await self._shot(page, f"tt_copy_row_fail_{attempt}")
                await asyncio.sleep(10)
                continue

            await asyncio.sleep(1.2)
            url = await self._read_clipboard(page)
            if self._is_tt_permalink(url):
                logger.success(f"Đã Copy link TikTok: {url}", "TIKTOK")
                return url

            href = await page.evaluate("""() => {
                const a = document.querySelector('a[href*="/video/"]');
                return (a && a.href) || '';
            }""")
            if self._is_tt_permalink(href):
                logger.success(f"Đã lấy link TikTok từ DOM: {href}", "TIKTOK")
                return href

            logger.warning(f"Clipboard chưa có permalink TikTok (got={url[:120]!r}).", "TIKTOK")
            await asyncio.sleep(10)

        await self._shot(page, "tt_copy_link_fail")
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
        tt_config = config_mgr.get("platforms", {}).get("tiktok", {})
        mark_ai = tt_config.get("mark_ai", True)
        native = get_native_schedule(schedule_time or "")
        if not native["enabled"]:
            logger.error("schedule_publish đang tắt — không đăng TikTok ngay.", "TIKTOK")
            return await fail_with_ai(
                page, "tiktok",
                "schedule_publish tắt; không bấm Đăng / Bây giờ trên TikTok.",
                goal=SCHEDULE_GOAL,
            )

        try:
            logger.info(f"Mở TikTok Studio Content: {TT_CONTENT}", "TIKTOK")
            await page.goto(TT_CONTENT, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            await self._dismiss_overlays(page)
            await self._confirm_discard_dialog(page)

            if not await self._wait_login(page):
                logger.error("Hết thời gian chờ đăng nhập TikTok (5 phút). Vui lòng đăng nhập trước!", "TIKTOK")
                return {"success": False, "error": "Hết thời gian chờ đăng nhập TikTok"}

            await page.goto(TT_CONTENT, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(3)
            await self._dismiss_overlays(page)
            await self._confirm_discard_dialog(page)

            if not await self._open_upload(page):
                await page.goto(TT_UPLOAD, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(3)
            await self._dismiss_overlays(page)
            await self._ensure_clean_upload(page)
            await asyncio.sleep(1.2)
            await self._confirm_discard_dialog(page)

            file_input = page.locator(
                '#panel-video input[type="file"], input[type="file"][accept*="video"]'
            ).first
            await file_input.wait_for(state="attached", timeout=20000)
            await file_input.set_input_files(os.path.abspath(file_path))
            logger.info("Đã đính kèm video lên TikTok (#panel-video).", "TIKTOK")
            await asyncio.sleep(5)
            await self._dismiss_overlays(page)
            await self._confirm_discard_dialog(page)

            await self._fill_caption(page, caption)

            if mark_ai:
                try:
                    ai_switch = page.locator(
                        'text=Nội dung do AI tạo, text=AI-generated content'
                    ).first
                    if await ai_switch.is_visible(timeout=2500):
                        await ai_switch.click(force=True)
                        logger.info("Đã bật nhãn nội dung do AI tạo trên TikTok.", "TIKTOK")
                except Exception:
                    pass

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await asyncio.sleep(0.6)
            await self._confirm_discard_dialog(page)

            if not await self._select_schedule_radio(page):
                await self._shot(page, "tt_radio_fail")
                return await fail_with_ai(
                    page, "tiktok",
                    "Không chọn được radio Lên lịch (Thời điểm đăng).",
                    goal=SCHEDULE_GOAL,
                )

            time_ok = await self._set_time_picker(page, native)
            date_ok = await self._set_date_picker(page, native)
            await self._dismiss_schedule_pickers(page)
            if not await self._picker_shows_time(page, native):
                logger.warning("Giờ hẹn TikTok chưa khớp 10:00 — chọn lại time picker.", "TIKTOK")
                time_ok = await self._set_time_picker(page, native)
                await self._dismiss_schedule_pickers(page)
            if not (time_ok and date_ok):
                await self._shot(page, "tt_picker_fail")
                logger.warning("TikTok picker Date/Time chưa chắc chắn — vẫn thử bấm Lên lịch nếu radio đã bật.", "TIKTOK")

            logger.info(f"Cài đặt Lên lịch TikTok: {native['label']} công khai.", "TIKTOK")

            if not await self._click_footer_schedule(page):
                await self._shot(page, "tt_footer_fail")
                return await fail_with_ai(
                    page, "tiktok",
                    "Không bấm được nút Lên lịch (data-e2e=post_video_button). Không bấm Đăng.",
                    goal=SCHEDULE_GOAL,
                )

            await self._shot(page, "tt_after_schedule")
            await self._handle_continue_to_post(page)

            success = False
            for _ in range(20):
                await asyncio.sleep(2)
                await self._dismiss_overlays(page)
                await self._handle_continue_to_post(page)
                if "/content" in page.url or "manage" in page.url:
                    success = True
                    break
                body_ok = await page.evaluate("""() => {
                    const t = (document.body.innerText || '').toLowerCase();
                    return t.includes('upload another') || t.includes('tải lên video khác')
                        || t.includes('manage your posts') || t.includes('quản lý bài')
                        || t.includes('is scheduled') || t.includes('đã được lên lịch')
                        || t.includes('đã lên lịch');
                }""")
                if body_ok:
                    success = True
                    break

            if not success:
                await self._shot(page, "tt_schedule_fail")
                logger.error("TikTok chưa xác nhận lên lịch (không thấy Content / thông báo).", "TIKTOK")
                return await fail_with_ai(
                    page, "tiktok",
                    "Đã bấm Lên lịch nhưng TikTok chưa xác nhận (không đăng ngay).",
                    goal=SCHEDULE_GOAL,
                )

            post_url = await self._copy_scheduled_post_link(page, caption)
            if not post_url:
                logger.warning("Đã lên lịch TikTok nhưng chưa Copy được link bài.", "TIKTOK")
            logger.success(
                f"Đã lên lịch TikTok công khai lúc {native['label']}! Link: {post_url or TT_CONTENT}",
                "TIKTOK",
            )
            return {"success": True, "url": post_url or TT_CONTENT, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên TikTok: {str(ex)}", "TIKTOK")
            await self._shot(page, "tt_exception")
            return await fail_with_ai(page, "tiktok", str(ex), goal=SCHEDULE_GOAL)


tiktok_poster = TikTokPoster()
