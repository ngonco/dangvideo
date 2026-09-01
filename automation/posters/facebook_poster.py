import os
import asyncio
from typing import Dict, Any
from playwright.async_api import Page
from automation.posters.base_poster import BasePoster
from core.logger import logger
from core.config_manager import config_mgr

class FacebookPoster(BasePoster):
    def __init__(self):
        super().__init__("Facebook")

    async def _extract_fb_url(self, page: Page) -> str:
        """Trích xuất URL Facebook Reels / Video vừa đăng"""
        try:
            url = await page.evaluate("""() => {
                const reelLink = document.querySelector('a[href*="/reel/"], a[href*="/videos/"], a[href*="/watch/"]');
                if (reelLink && reelLink.href) return reelLink.href;
                return 'https://www.facebook.com';
            }""")
            return url or "https://www.facebook.com"
        except Exception:
            return "https://www.facebook.com"

    async def post_video(self, page: Page, video_data: Dict[str, Any]) -> Dict[str, Any]:
        file_path = video_data.get("file_path", "")
        if not self.validate_video_file(file_path):
            return {"success": False, "error": "File video không hợp lệ"}

        caption = self.format_caption(video_data)
        fb_config = config_mgr.get("platforms", {}).get("facebook", {})

        try:
            logger.info("Mở Facebook (https://www.facebook.com)...", "FACEBOOK")
            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Check if login is needed
            if "login" in page.url or await page.locator('input#email, input[name="email"]').first.is_visible():
                logger.error("Chưa đăng nhập Facebook. Vui lòng mở Profile để đăng nhập trước.", "FACEBOOK")
                return {"success": False, "error": "Cần đăng nhập Facebook"}

            # Click 'Ảnh/video' hoặc ô tạo bài viết trên Feed
            photo_btn = page.locator('div[role="button"]:has-text("Ảnh/video"), div[role="button"]:has-text("Photo/video"), div[role="button"]:has-text("Bạn đang nghĩ gì"), div[role="button"]:has-text("What\'s on your mind")').first
            if await photo_btn.is_visible(timeout=8000):
                await photo_btn.click(force=True)
                await asyncio.sleep(2.5)

            # Attach video file
            file_input = page.locator('div[role="dialog"] input[type="file"], input[type="file"]').first
            await file_input.wait_for(state="attached", timeout=15000)
            await file_input.set_input_files(os.path.abspath(file_path))
            logger.info("Đã đính kèm tệp video lên Facebook...", "FACEBOOK")
            await asyncio.sleep(5)

            # Fill caption inside dialog
            editor = page.locator('div[role="dialog"] div[role="textbox"], div[role="dialog"] div[contenteditable="true"]').first
            if await editor.is_visible(timeout=8000):
                await editor.click(force=True)
                await page.keyboard.type(caption, delay=20)
                logger.info("Đã điền mô tả và Hashtags cho Facebook.", "FACEBOOK")
                await asyncio.sleep(1)

            # -------------------------------------------------------------
            # CHẾ ĐỘ TEST (AUDIENCE: ONLY ME / CHỈ MÌNH TÔI)
            # -------------------------------------------------------------
            try:
                logger.info("Cài đặt quyền riêng tư Facebook: Chọn 'Chỉ mình tôi' (Test Mode)...", "FACEBOOK")
                # Open audience selector
                await page.evaluate("""() => {
                    const dialogs = document.querySelectorAll('div[role="dialog"]');
                    const mainDialog = dialogs[dialogs.length - 1];
                    if (mainDialog) {
                        const audBtn = Array.from(mainDialog.querySelectorAll('div[role="button"], div[aria-haspopup="menu"]')).find(b => {
                            const t = (b.innerText || '').toLowerCase();
                            return t.includes('công khai') || t.includes('public') || t.includes('bạn bè') || t.includes('friends');
                        });
                        if (audBtn) audBtn.click();
                    }
                }""")
                await asyncio.sleep(1.5)

                # Select 'Chỉ mình tôi' / 'Only me'
                await page.evaluate("""() => {
                    const onlyMe = Array.from(document.querySelectorAll('div[role="radio"], div[role="button"], span')).find(el => {
                        const t = (el.innerText || '').toLowerCase();
                        return t.includes('chỉ mình tôi') || t.includes('only me');
                    });
                    if (onlyMe) onlyMe.click();
                }""")
                await asyncio.sleep(1)

                # Close audience sub-dialog (Done / Save / Back)
                await page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('div[role="button"], div[aria-label]')).filter(b => {
                        const aria = (b.getAttribute('aria-label') || '').toLowerCase();
                        const text = (b.innerText || '').toLowerCase();
                        return aria.includes('quay lại') || aria.includes('back') || aria.includes('lưu') || aria.includes('save') || aria.includes('xong') || aria.includes('done') || text === 'xong' || text === 'lưu' || text === 'save' || text === 'done';
                    });
                    if (btns.length > 0) btns[btns.length - 1].click();
                }""")
                await asyncio.sleep(1.5)
                logger.success("Đã cài đặt đối tượng 'Chỉ mình tôi' thành công trên Facebook.", "FACEBOOK")
            except Exception as e:
                logger.warning(f"Lưu ý khi chọn quyền riêng tư Facebook: {e}", "FACEBOOK")

            # Click Post / Đăng
            post_btn = page.locator('div[aria-label="Đăng"], div[aria-label="Post"], div[role="button"]:has-text("Đăng"), div[role="button"]:has-text("Post")').last
            await post_btn.wait_for(state="visible", timeout=15000)
            await post_btn.click(force=True)
            logger.info("Đã bấm Đăng video trên Facebook (Chế độ Test), đang chờ hoàn tất tải lên...", "FACEBOOK")
            await asyncio.sleep(12)

            post_url = await self._extract_fb_url(page)
            logger.success(f"Đăng thành công Facebook (Chế độ Test)! Link: {post_url}", "FACEBOOK")
            return {"success": True, "url": post_url, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên Facebook: {str(ex)}", "FACEBOOK")
            return {"success": False, "error": str(ex)}

facebook_poster = FacebookPoster()
