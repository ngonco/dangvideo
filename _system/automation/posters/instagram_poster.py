import os
import asyncio
from typing import Dict, Any
from playwright.async_api import Page
from automation.posters.base_poster import BasePoster
from core.logger import logger
from core.config_manager import config_mgr

class InstagramPoster(BasePoster):
    def __init__(self):
        super().__init__("Instagram")

    async def _dismiss_ig_dialogs(self, page: Page):
        """Tự động đóng các thông báo như 'Video posts are now shared as reels'"""
        try:
            await page.evaluate("""() => {
                const okBtns = Array.from(document.querySelectorAll('button, div[role="button"]')).filter(b => {
                    const t = (b.innerText || '').trim().toLowerCase();
                    return t === 'ok' || t === 'đã hiểu' || t === 'got it' || t === 'not now' || t === 'lúc khác';
                });
                okBtns.forEach(b => b.click());
            }""")
        except Exception:
            pass

    async def _extract_ig_url(self, page: Page) -> str:
        """Trích xuất URL Instagram Reels vừa đăng"""
        try:
            url = await page.evaluate("""() => {
                const postLinks = Array.from(document.querySelectorAll('a[href*="/reel/"], a[href*="/p/"]'));
                if (postLinks.length > 0) {
                    return postLinks[postLinks.length - 1].href;
                }
                return 'https://www.instagram.com';
            }""")
            return url or "https://www.instagram.com"
        except Exception:
            return "https://www.instagram.com"

    async def post_video(self, page: Page, video_data: Dict[str, Any]) -> Dict[str, Any]:
        file_path = video_data.get("file_path", "")
        if not self.validate_video_file(file_path):
            return {"success": False, "error": "File video không hợp lệ"}

        caption = self.format_caption(video_data)

        try:
            logger.info("Mở Instagram (https://www.instagram.com)...", "INSTAGRAM")
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Check if login is needed
            if "accounts/login" in page.url or await page.locator('input[name="username"]').first.is_visible():
                logger.error("Chưa đăng nhập Instagram. Vui lòng mở Profile để đăng nhập trước.", "INSTAGRAM")
                return {"success": False, "error": "Cần đăng nhập Instagram"}

            # 1. Click Create (+) in left sidebar
            logger.info("Mở menu Tạo / Create trên Instagram...", "INSTAGRAM")
            await page.evaluate("""() => {
                const createSvg = document.querySelector('svg[aria-label="New post"], svg[aria-label="Bài viết mới"], svg[aria-label="Tạo"]');
                if (createSvg) {
                    const btn = createSvg.closest('a, div[role="button"], button') || createSvg;
                    btn.click();
                }
            }""")
            await asyncio.sleep(2)

            # 2. Click 'Post' / 'Bài viết' in submenu
            await page.evaluate("""() => {
                const postLink = Array.from(document.querySelectorAll('a, div[role="button"], span')).find(el => {
                    const t = (el.innerText || '').trim().toLowerCase();
                    return t === 'post' || t === 'bài viết';
                });
                if (postLink) postLink.click();
            }""")
            await asyncio.sleep(3)

            # 3. File Chooser via 'Select from computer'
            select_btn = page.locator('button:has-text("Select from computer"), button:has-text("Chọn từ máy tính")').first
            await select_btn.wait_for(state="visible", timeout=12000)
            
            async with page.expect_file_chooser(timeout=15000) as fc_info:
                await select_btn.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(os.path.abspath(file_path))
            logger.info("Đã đính kèm tệp video lên Instagram qua File Chooser...", "INSTAGRAM")
            await asyncio.sleep(4)

            # Dismiss Reels intro dialog if present
            await self._dismiss_ig_dialogs(page)
            await asyncio.sleep(1)

            # 4. Click Next (Crop step -> Filter step)
            next_btn = page.locator('div[role="button"]:has-text("Next"), div[role="button"]:has-text("Tiếp"), button:has-text("Next"), button:has-text("Tiếp")').last
            if await next_btn.is_visible(timeout=10000):
                await next_btn.click(force=True)
                await asyncio.sleep(3)

            await self._dismiss_ig_dialogs(page)

            # Click Next (Filter step -> Caption step)
            if await next_btn.is_visible(timeout=10000):
                await next_btn.click(force=True)
                await asyncio.sleep(3)

            # 5. Caption editor
            caption_box = page.locator('div[aria-label*="caption"], div[aria-label*="chú thích"], div[contenteditable="true"]').first
            if await caption_box.is_visible(timeout=10000):
                await caption_box.click(force=True)
                await page.keyboard.type(caption, delay=20)
                logger.info("Đã điền Caption và Hashtags cho Instagram Reels.", "INSTAGRAM")
                await asyncio.sleep(1)

            # 6. Click Share / Chia sẻ
            share_btn = page.locator('div[role="button"]:has-text("Share"), div[role="button"]:has-text("Chia sẻ"), button:has-text("Share"), button:has-text("Chia sẻ")').first
            await share_btn.wait_for(state="visible", timeout=10000)
            await share_btn.click(force=True)
            logger.info("Đã nhấn Chia sẻ Instagram Reels, đang hoàn tất tải lên...", "INSTAGRAM")
            await asyncio.sleep(12)

            post_url = await self._extract_ig_url(page)
            logger.success(f"Đăng thành công video lên Instagram Reels! Link: {post_url}", "INSTAGRAM")
            return {"success": True, "url": post_url, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên Instagram: {str(ex)}", "INSTAGRAM")
            return {"success": False, "error": str(ex)}

instagram_poster = InstagramPoster()
