import os
import re
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from playwright.async_api import Page
from automation.posters.base_poster import BasePoster
from core.logger import logger
from automation.ai_fallback import fail_with_ai, INSTAGRAM_SHARE_GOAL

IG_HOME = "https://www.instagram.com/"
SHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "debug_screenshots")
PERMALINK_RE = re.compile(r"instagram\.com/(p|reel)/[A-Za-z0-9_-]+", re.I)


class InstagramPoster(BasePoster):
    def __init__(self):
        super().__init__("Instagram")

    async def _shot(self, page: Page, name: str):
        try:
            os.makedirs(SHOT_DIR, exist_ok=True)
            path = os.path.join(SHOT_DIR, f"{name}.png")
            await page.screenshot(path=path)
            logger.info(f"Ảnh Instagram: {path}", "INSTAGRAM")
        except Exception:
            pass

    async def _dismiss_ig_dialogs(self, page: Page):
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

    @staticmethod
    def _normalize_url(url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        path = (parsed.path or "").rstrip("/")
        if not path:
            return f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else url
        return f"{parsed.scheme}://{parsed.netloc}{path}/"

    @classmethod
    def _is_permalink(cls, url: str) -> bool:
        return bool(url and PERMALINK_RE.search(url))

    async def _wait_login(self, page: Page) -> bool:
        login_needed = "accounts/login" in page.url or await page.locator(
            'input[name="username"]'
        ).first.is_visible(timeout=4000)
        if not login_needed:
            return True

        logger.warning(
            "👉 Chưa đăng nhập Instagram! Vui lòng hoàn tất đăng nhập trên cửa sổ trình duyệt "
            "(hệ thống sẽ tự động chờ tối đa 5 phút)...",
            "INSTAGRAM",
        )
        try:
            await page.bring_to_front()
        except Exception:
            pass

        for sec in range(0, 300, 3):
            if sec > 0 and sec % 30 == 0:
                logger.info(f"⏳ [INSTAGRAM] Đang chờ bạn đăng nhập... (Đã qua {sec}/300s)", "INSTAGRAM")
            await asyncio.sleep(3)
            await self._dismiss_ig_dialogs(page)
            if "accounts/login" not in page.url and not await page.locator(
                'input[name="username"]'
            ).first.is_visible(timeout=1000):
                logger.success("Đã phát hiện đăng nhập Instagram thành công!", "INSTAGRAM")
                await asyncio.sleep(2)
                return True
        return False

    async def _open_new_post(self, page: Page) -> bool:
        logger.info("Mở Bài viết mới / New post trên Instagram...", "INSTAGRAM")
        clicked = await page.evaluate("""() => {
            const labels = ['New post', 'Bài viết mới', 'Create', 'Tạo'];
            const nodes = Array.from(document.querySelectorAll(
                'svg[aria-label], a[aria-label], div[aria-label], span[aria-label], a, div[role="link"]'
            ));
            const hit = nodes.find(el => labels.includes((el.getAttribute('aria-label') || '').trim()));
            if (!hit) return false;
            const btn = hit.closest('a, div[role="button"], button, div[role="link"]') || hit;
            btn.click();
            return true;
        }""")
        await asyncio.sleep(1.5)
        return bool(clicked)

    async def _choose_post_type(self, page: Page) -> bool:
        logger.info("Chọn Bài viết / Post (không Story, không Reel)...", "INSTAGRAM")
        clicked = await page.evaluate("""() => {
            const exact = ['Post', 'Bài viết'];
            const nodes = Array.from(document.querySelectorAll(
                'a, div[role="button"], span, div[role="menuitem"], span[dir="auto"]'
            ));
            const hit = nodes.find(el => exact.includes((el.innerText || '').trim()));
            if (!hit) return false;
            const btn = hit.closest('a, div[role="button"], button, div[role="menuitem"]') || hit;
            btn.click();
            return true;
        }""")
        await asyncio.sleep(2.5)
        return bool(clicked)

    async def _attach_file(self, page: Page, file_path: str) -> bool:
        abs_path = os.path.abspath(file_path)
        file_input = page.locator('div[role="dialog"] form input[type="file"], form input[type="file"]').first
        try:
            if await file_input.count() > 0:
                await file_input.set_input_files(abs_path)
                logger.info("Đã đính kèm tệp video Instagram qua form input[type=file]...", "INSTAGRAM")
                await asyncio.sleep(4)
                return True
        except Exception as ex:
            logger.warning(f"Không set được input file Instagram: {ex}", "INSTAGRAM")

        select_btn = page.locator(
            'div[role="dialog"] button:has-text("Select from computer"), '
            'div[role="dialog"] button:has-text("Chọn từ máy tính"), '
            'button:has-text("Select from computer"), button:has-text("Chọn từ máy tính")'
        ).first
        try:
            await select_btn.wait_for(state="visible", timeout=12000)
            async with page.expect_file_chooser(timeout=15000) as fc_info:
                await select_btn.click()
            chooser = await fc_info.value
            await chooser.set_files(abs_path)
            logger.info("Đã đính kèm tệp video Instagram qua File Chooser...", "INSTAGRAM")
            await asyncio.sleep(4)
            return True
        except Exception as ex:
            logger.error(f"Không đính kèm được video Instagram: {ex}", "INSTAGRAM")
            return False

    async def _click_dialog_exact(self, page: Page, labels: list) -> bool:
        labels_js = list(labels)
        return bool(await page.evaluate(
            """(labels) => {
                const dialog = document.querySelector('div[role="dialog"]') || document.body;
                const btns = Array.from(dialog.querySelectorAll('div[role="button"], button'));
                const hit = btns.find(b => labels.includes((b.innerText || '').trim().split('\\n')[0].trim()));
                if (!hit) return false;
                hit.click();
                return true;
            }""",
            labels_js,
        ))

    async def _click_next_twice(self, page: Page) -> bool:
        ok = 0
        for i in range(2):
            await self._dismiss_ig_dialogs(page)
            clicked = await self._click_dialog_exact(page, ["Next", "Tiếp"])
            if not clicked:
                next_btn = page.locator(
                    'div[role="dialog"] div[role="button"]:has-text("Next"), '
                    'div[role="dialog"] div[role="button"]:has-text("Tiếp"), '
                    'div[role="dialog"] button:has-text("Next"), '
                    'div[role="dialog"] button:has-text("Tiếp")'
                ).last
                try:
                    if await next_btn.is_visible(timeout=8000):
                        await next_btn.click(force=True)
                        clicked = True
                except Exception:
                    clicked = False
            if clicked:
                ok += 1
                logger.info(f"Đã bấm Tiếp / Next lần {i + 1}.", "INSTAGRAM")
                await asyncio.sleep(3)
            else:
                logger.warning(f"Không thấy nút Tiếp / Next lần {i + 1}.", "INSTAGRAM")
        return ok >= 1

    async def _fill_caption(self, page: Page, caption: str) -> bool:
        box = page.locator(
            '[aria-label="Write a caption..."], [aria-label="Viết chú thích..."], '
            '[aria-label*="Write a caption"], [aria-label*="Viết chú thích"]'
        ).first
        try:
            await box.wait_for(state="visible", timeout=12000)
            await box.click(force=True)
            await asyncio.sleep(0.3)
            await page.keyboard.type(caption, delay=18)
            logger.info("Đã điền chú thích Instagram (Bài viết).", "INSTAGRAM")
            await asyncio.sleep(0.8)
            return True
        except Exception as ex:
            logger.warning(f"Không điền được chú thích Instagram: {ex}", "INSTAGRAM")
            return False

    async def _click_share(self, page: Page) -> bool:
        logger.info("Instagram web không có hẹn giờ — bấm Chia sẻ / Share ngay (công khai).", "INSTAGRAM")
        clicked = await page.evaluate("""() => {
            const dialog = document.querySelector('div[role="dialog"]') || document.body;
            const btns = Array.from(dialog.querySelectorAll('div[role="button"], button'));
            const hit = btns.find(b => {
                const t = ((b.innerText || '').split('\\n')[0] || '').trim();
                return t === 'Share' || t === 'Chia sẻ';
            });
            if (!hit) return false;
            hit.click();
            return true;
        }""")
        if clicked:
            logger.info("Đã bấm Chia sẻ / Share trong dialog tạo bài.", "INSTAGRAM")
            return True
        logger.error("Không thấy nút Chia sẻ / Share (đúng chữ, không Chia sẻ bài viết).", "INSTAGRAM")
        return False

    async def _wait_and_click_done(self, page: Page) -> bool:
        logger.info("Đã gửi chia sẻ Instagram, đang chờ Xong / Done (có thể 2–4 phút)...", "INSTAGRAM")
        for loop_i in range(48):
            await asyncio.sleep(5)

            done_visible = await page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('div[role="button"], button'));
                return btns.some(b => {
                    const t = ((b.innerText || '').split('\\n')[0] || '').trim();
                    return t === 'Done' || t === 'Xong';
                });
            }""")
            if done_visible:
                logger.success("Instagram đã hiện Xong / Done.", "INSTAGRAM")
                clicked = await page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('div[role="button"], button'));
                    const hit = btns.find(b => {
                        const t = ((b.innerText || '').split('\\n')[0] || '').trim();
                        return t === 'Done' || t === 'Xong';
                    });
                    if (!hit) return false;
                    hit.click();
                    return true;
                }""")
                if clicked:
                    logger.info("Đã bấm Xong / Done.", "INSTAGRAM")
                    await asyncio.sleep(4)
                    return True

            if loop_i % 3 == 0:
                sharing = await page.locator(
                    ':has-text("Sharing"), :has-text("Đang chia sẻ"), '
                    ':has-text("Your post has been shared"), :has-text("Bài viết của bạn đã được chia sẻ"), '
                    ':has-text("Your reel has been shared")'
                ).first.is_visible(timeout=400)
                if sharing:
                    logger.info("Đang xử lý Instagram (Sharing)...", "INSTAGRAM")
                else:
                    logger.info(f"Chờ Instagram hoàn tất chia sẻ... ({(loop_i + 1) * 5}s)", "INSTAGRAM")

        return False

    async def _goto_own_profile(self, page: Page) -> None:
        clicked = await page.evaluate("""() => {
            const labels = ['Profile', 'Trang cá nhân'];
            const nodes = Array.from(document.querySelectorAll(
                'svg[aria-label], a[aria-label], span[aria-label], img[alt]'
            ));
            const hit = nodes.find(el => {
                const a = (el.getAttribute('aria-label') || '').trim();
                const alt = (el.getAttribute('alt') || '').trim();
                return labels.includes(a) || labels.includes(alt);
            });
            if (!hit) return false;
            const btn = hit.closest('a, div[role="link"], div[role="button"]') || hit;
            btn.click();
            return true;
        }""")
        if clicked:
            await asyncio.sleep(3)

    async def _open_latest_and_read_url(self, page: Page) -> str:
        if self._is_permalink(page.url):
            return self._normalize_url(page.url)

        await asyncio.sleep(2)
        grid = page.locator(
            'section main a[href*="/p/"], section main a[href*="/reel/"]'
        )
        try:
            if await grid.count() == 0:
                await self._goto_own_profile(page)
                await asyncio.sleep(3)
        except Exception:
            await self._goto_own_profile(page)
            await asyncio.sleep(3)

        first = page.locator(
            'section main a[href*="/p/"], section main a[href*="/reel/"]'
        ).first
        try:
            await first.wait_for(state="visible", timeout=20000)
            href = await first.get_attribute("href") or ""
            logger.info(f"Mở video Instagram mới nhất trên profile ({href})...", "INSTAGRAM")
            await first.click(force=True)
        except Exception as ex:
            logger.warning(f"Không click được ô lưới Instagram: {ex}", "INSTAGRAM")
            href = await page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll(
                    'section main a[href*="/p/"], section main a[href*="/reel/"]'
                ));
                const a = links[0];
                if (!a) return '';
                a.click();
                return a.getAttribute('href') || '';
            }""")
            if not href:
                return ""

        for _ in range(15):
            await asyncio.sleep(1)
            if self._is_permalink(page.url):
                return self._normalize_url(page.url)

        return self._normalize_url(page.url) if self._is_permalink(page.url) else ""

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

        try:
            logger.info("Mở Instagram (https://www.instagram.com)...", "INSTAGRAM")
            await page.goto(IG_HOME, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)
            await self._dismiss_ig_dialogs(page)

            if not await self._wait_login(page):
                logger.error("Hết thời gian chờ đăng nhập Instagram (5 phút). Vui lòng đăng nhập trước!", "INSTAGRAM")
                return {"success": False, "error": "Hết thời gian chờ đăng nhập Instagram"}

            await self._dismiss_ig_dialogs(page)
            if not await self._open_new_post(page):
                await self._shot(page, "ig_01_create_fail")
                return await fail_with_ai(
                    page, "instagram",
                    "Không bấm được Bài viết mới / New post.",
                    goal=INSTAGRAM_SHARE_GOAL,
                )

            await self._choose_post_type(page)
            await asyncio.sleep(1)
            await self._shot(page, "ig_01_start")

            if not await self._attach_file(page, file_path):
                await self._shot(page, "ig_file_fail")
                return await fail_with_ai(
                    page, "instagram",
                    "Không đính kèm được tệp video (Select from computer / form input).",
                    goal=INSTAGRAM_SHARE_GOAL,
                )

            await self._dismiss_ig_dialogs(page)
            await asyncio.sleep(1)

            if not await self._click_next_twice(page):
                await self._shot(page, "ig_next_fail")
                return await fail_with_ai(
                    page, "instagram",
                    "Không bấm được Tiếp / Next sau khi chọn video.",
                    goal=INSTAGRAM_SHARE_GOAL,
                )

            await self._fill_caption(page, caption)

            if not await self._click_share(page):
                await self._shot(page, "ig_share_fail")
                return await fail_with_ai(
                    page, "instagram",
                    "Không bấm được Chia sẻ / Share trong dialog tạo bài (không bấm Chia sẻ bài viết).",
                    goal=INSTAGRAM_SHARE_GOAL,
                )

            if not await self._wait_and_click_done(page):
                await self._shot(page, "ig_done_fail")
                return await fail_with_ai(
                    page, "instagram",
                    "Instagram chưa hiện Xong / Done sau khi chia sẻ (xử lý quá lâu).",
                    goal=INSTAGRAM_SHARE_GOAL,
                )

            await self._shot(page, "ig_02_after_post")
            post_url = await self._open_latest_and_read_url(page)
            if not self._is_permalink(post_url):
                await self._shot(page, "ig_permalink_fail")
                logger.error(
                    f"Instagram đã chia sẻ nhưng thanh địa chỉ chưa phải permalink /p/ hoặc /reel/ (url={page.url}).",
                    "INSTAGRAM",
                )
                return await fail_with_ai(
                    page, "instagram",
                    f"Đã Share + Xong nhưng không mở được video để copy link thanh địa chỉ. URL hiện tại: {page.url}",
                    goal=INSTAGRAM_SHARE_GOAL,
                )

            logger.success(f"Đã chia sẻ Instagram Bài viết (đăng ngay)! Link: {post_url}", "INSTAGRAM")
            return {"success": True, "url": post_url, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên Instagram: {str(ex)}", "INSTAGRAM")
            await self._shot(page, "ig_exception")
            return await fail_with_ai(page, "instagram", str(ex), goal=INSTAGRAM_SHARE_GOAL)


instagram_poster = InstagramPoster()
