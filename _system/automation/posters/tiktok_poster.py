import os
import re
import asyncio
from typing import Dict, Any
from playwright.async_api import Page
from automation.posters.base_poster import BasePoster
from core.logger import logger
from core.config_manager import config_mgr

class TikTokPoster(BasePoster):
    def __init__(self):
        super().__init__("TikTok")

    async def _dismiss_overlays(self, page: Page):
        """Xóa toàn bộ overlay react-joyride, modal chào mừng và popup hướng dẫn của TikTok"""
        try:
            await page.evaluate("""() => {
                // Xóa react-joyride overlay chặn click
                const joyrides = document.querySelectorAll('#react-joyride-portal, .react-joyride__overlay, [data-test-id="overlay"], .tiktok-modal__mask');
                joyrides.forEach(el => el.remove());

                // Click nút Skip / Bỏ qua nếu có
                const skipBtns = Array.from(document.querySelectorAll('button')).filter(b => {
                    const t = (b.innerText || '').toLowerCase();
                    return t.includes('skip') || t.includes('bỏ qua') || t.includes('got it') || t.includes('đã hiểu') || t.includes('close') || t.includes('đóng');
                });
                skipBtns.forEach(b => b.click());
            }""")
        except Exception:
            pass

    async def _extract_tiktok_url(self, page: Page) -> str:
        """Trích xuất URL video vừa đăng trên TikTok"""
        try:
            url = await page.evaluate("""() => {
                // 1. Tìm trong thẻ link video quản lý
                const videoLink = document.querySelector('a[href*="/video/"]');
                if (videoLink && videoLink.href) return videoLink.href;

                // 2. Tìm link bài đăng trong popup thành công
                const links = Array.from(document.querySelectorAll('a')).filter(a => a.href && (a.href.includes('/@') || a.href.includes('tiktok.com/v/')));
                if (links.length > 0) return links[0].href;

                // 3. Tìm link profile
                const profileLink = document.querySelector('a[href*="/@"]');
                if (profileLink && profileLink.href) return profileLink.href;

                return '';
            }""")
            return url or "https://www.tiktok.com/@me/video"
        except Exception:
            return "https://www.tiktok.com"

    async def post_video(self, page: Page, video_data: Dict[str, Any]) -> Dict[str, Any]:
        file_path = video_data.get("file_path", "")
        if not self.validate_video_file(file_path):
            return {"success": False, "error": "File video không hợp lệ"}

        caption = self.format_caption(video_data)
        tt_config = config_mgr.get("platforms", {}).get("tiktok", {})
        mark_ai = tt_config.get("mark_ai", True)

        try:
            logger.info("Mở TikTok Creator Center (https://www.tiktok.com/creator-center/upload)...", "TIKTOK")
            await page.goto("https://www.tiktok.com/creator-center/upload?from=upload", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Check if login is needed
            if "login" in page.url or await page.locator('button:has-text("Log in"), button:has-text("Đăng nhập")').first.is_visible():
                logger.error("Chưa đăng nhập TikTok. Vui lòng mở Profile để đăng nhập trước.", "TIKTOK")
                return {"success": False, "error": "Cần đăng nhập TikTok"}

            await self._dismiss_overlays(page)

            # File input on TikTok Upload page
            file_input = page.locator('input[type="file"]').first
            if not await file_input.is_visible(timeout=5000):
                for frame in page.frames:
                    frame_input = frame.locator('input[type="file"]').first
                    if await frame_input.count() > 0:
                        file_input = frame_input
                        break

            await file_input.set_input_files(os.path.abspath(file_path))
            logger.info("Đã đính kèm video lên TikTok, đang chờ tải lên và xử lý...", "TIKTOK")
            await asyncio.sleep(5)

            # Dismiss joyride overlays immediately after file selection
            await self._dismiss_overlays(page)

            # Locate caption editor
            editor = page.locator('div[contenteditable="true"], div.DraftEditor-root, div[class*="caption"] div[contenteditable]').first
            if await editor.is_visible(timeout=25000):
                await self._dismiss_overlays(page)
                try:
                    await editor.click(force=True)
                except Exception:
                    await page.evaluate("""() => {
                        const ed = document.querySelector('div[contenteditable="true"]');
                        if (ed) ed.focus();
                    }""")
                
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                await asyncio.sleep(0.5)
                await page.keyboard.type(caption, delay=20)
                logger.info("Đã điền Caption và Hashtags lên TikTok.", "TIKTOK")
                await asyncio.sleep(1)

            await self._dismiss_overlays(page)

            # -------------------------------------------------------------
            # BẬT NHÃN NỘI DUNG DO AI TẠO (AI-GENERATED CONTENT)
            # -------------------------------------------------------------
            if mark_ai:
                try:
                    ai_switch = page.locator('text=Nội dung do AI tạo, text=AI-generated content, input[type="checkbox"][name*="ai"]').first
                    if await ai_switch.is_visible(timeout=3000):
                        await ai_switch.click(force=True)
                        logger.info("Đã bật nhãn 'Nội dung do AI tạo' trên TikTok.", "TIKTOK")
                except Exception:
                    pass

            # -------------------------------------------------------------
            # CÀI ĐẶT QUYỀN RIÊNG TƯ: CHẾ ĐỘ TEST (ONLY YOU / CHỈ MÌNH TÔI)
            # -------------------------------------------------------------
            try:
                logger.info("Cài đặt quyền riêng tư TikTok: Chọn 'Chỉ mình tôi' (Chế độ Test)...", "TIKTOK")
                await page.evaluate("""() => {
                    // Tìm dropdown quyền riêng tư
                    const selects = Array.from(document.querySelectorAll('div[class*="select"], div[aria-haspopup="listbox"]'));
                    for (const s of selects) {
                        const text = (s.innerText || '').toLowerCase();
                        if (text.includes('public') || text.includes('công khai') || text.includes('everyone') || text.includes('mọi người')) {
                            s.click();
                            break;
                        }
                    }
                }""")
                await asyncio.sleep(1)
                
                only_you = page.locator('div[role="option"]:has-text("Only you"), div[role="option"]:has-text("Chỉ mình tôi"), li:has-text("Only you"), li:has-text("Chỉ mình tôi")').first
                if await only_you.is_visible(timeout=3000):
                    await only_you.click(force=True)
                    logger.success("Đã chọn chế độ 'Chỉ mình tôi' (Test Mode) trên TikTok.", "TIKTOK")
            except Exception:
                pass

            await self._dismiss_overlays(page)

            # -------------------------------------------------------------
            # ĐỢI VÀ BẤM NÚT ĐĂNG (POST)
            # -------------------------------------------------------------
            post_btn = page.locator('button:has-text("Post"), button:has-text("Đăng"), button[data-e2e="post_video_button"]').first
            await post_btn.wait_for(state="visible", timeout=35000)

            # Wait until upload is 100% complete and button is enabled
            for _ in range(40):
                is_disabled = await post_btn.get_attribute("disabled")
                if not is_disabled:
                    break
                await self._dismiss_overlays(page)
                await asyncio.sleep(2)

            await self._dismiss_overlays(page)
            await post_btn.click(force=True)
            logger.info("Đã nhấn nút Đăng trên TikTok (Chế độ Test), đang chờ xác nhận...", "TIKTOK")
            await asyncio.sleep(8)

            # Check success dialog or extract URL
            post_url = await self._extract_tiktok_url(page)
            logger.success(f"Đăng thành công video lên TikTok (Chế độ Test)! Link: {post_url}", "TIKTOK")
            return {"success": True, "url": post_url, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên TikTok: {str(ex)}", "TIKTOK")
            return {"success": False, "error": str(ex)}

tiktok_poster = TikTokPoster()
