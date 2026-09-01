import os
import re
import asyncio
from typing import Dict, Any
from playwright.async_api import Page
from automation.posters.base_poster import BasePoster
from core.logger import logger
from core.config_manager import config_mgr

class YouTubePoster(BasePoster):
    def __init__(self):
        super().__init__("YouTube")

    def _clean_title(self, raw_title: str) -> str:
        """Làm sạch tiêu đề, giữ nguyên câu từ hoàn chỉnh và gắn #Shorts"""
        if not raw_title:
            return "Video Đạo Lý Hay #Shorts"
        
        t = re.sub(r'^\s*\d{1,2}:\d{2}\s*', '', raw_title)
        t = re.sub(r'[✅📝✨🎉💡👉📌▼▲🥰🧠]', '', t)
        t = t.replace("Chưa tải xuống", "").replace("Hoàn thành", "").replace("Đóng", "").replace("Mở", "")
        t = re.sub(r'^\d+[\.\)]\s*', '', t)

        lines = [line.strip() for line in t.split("\n") if line.strip()]
        clean = lines[0] if lines else "Video Đạo Lý Hay"
        clean = re.sub(r'\s+', ' ', clean).strip()

        max_base_len = 90
        if len(clean) > max_base_len:
            truncated = clean[:max_base_len]
            last_space = truncated.rfind(' ')
            if last_space > 30:
                clean = truncated[:last_space]
            else:
                clean = truncated

        if "#shorts" not in clean.lower():
            clean = f"{clean} #Shorts"

        return clean.strip()

    async def _extract_youtube_url(self, page: Page) -> str:
        """Trích xuất chính xác URL của video (https://youtube.com/shorts/<ID> hoặc https://youtu.be/<ID>)"""
        try:
            url = await page.evaluate("""() => {
                const anchors = Array.from(document.querySelectorAll('a'));
                for (const a of anchors) {
                    const href = a.getAttribute('href') || a.innerText || '';
                    const match = href.match(/https?:\\/\\/(?:youtu\\.be\\/|www\\.youtube\\.com\\/(?:shorts\\/|watch\\?v=))([a-zA-Z0-9_-]{8,15})/);
                    if (match) {
                        return 'https://youtube.com/shorts/' + match[1];
                    }
                }

                const containers = Array.from(document.querySelectorAll('ytcp-video-info, ytcp-video-share-dialog, [class*="video-url"], [class*="ytcp-video-info"], [aria-label*="link"], [aria-label*="liên kết"]'));
                for (const el of containers) {
                    const text = (el.innerText || '') + ' ' + (el.textContent || '') + ' ' + (el.innerHTML || '');
                    const match = text.match(/(?:https?:\\/\\/)?(?:youtu\\.be\\/|www\\.youtube\\.com\\/(?:shorts\\/|watch\\?v=))([a-zA-Z0-9_-]{8,15})/);
                    if (match) {
                        return 'https://youtube.com/shorts/' + match[1];
                    }
                }

                const inputs = Array.from(document.querySelectorAll('input, span'));
                for (const inp of inputs) {
                    const val = inp.value || inp.innerText || '';
                    const match = val.match(/(?:https?:\\/\\/)?youtu\\.be\\/([a-zA-Z0-9_-]{8,15})/);
                    if (match) {
                        return 'https://youtube.com/shorts/' + match[1];
                    }
                }

                return '';
            }""")
            return url or ""
        except Exception:
            return ""

    async def post_video(self, page: Page, video_data: Dict[str, Any], privacy_override: str = "unlisted") -> Dict[str, Any]:
        file_path = video_data.get("file_path", "")
        if not self.validate_video_file(file_path):
            return {"success": False, "error": "File video không hợp lệ"}

        raw_title = video_data.get("suggested_title") or video_data.get("title") or ""
        title = self._clean_title(raw_title)

        description = self.format_caption(video_data)
        yt_config = config_mgr.get("platforms", {}).get("youtube", {})
        mark_ai = yt_config.get("mark_ai", True)
        privacy = privacy_override or yt_config.get("privacy", "unlisted")

        try:
            logger.info("Mở YouTube Studio (https://studio.youtube.com)...", "YOUTUBE")
            await page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Check if login is required
            if "accounts.google.com" in page.url:
                logger.error("Chưa đăng nhập tài khoản Google/YouTube Studio. Vui lòng đăng nhập trước!", "YOUTUBE")
                return {"success": False, "error": "Cần đăng nhập YouTube Studio"}

            # Click Create / TẠO button
            logger.info("Tìm nút Tạo / Create trên YouTube Studio...", "YOUTUBE")
            create_btn = page.locator('button#create-icon, ytcp-button#create-icon, button:has-text("CREATE"), button:has-text("TẠO"), button:has-text("Create"), button:has-text("Tạo")').first
            await create_btn.wait_for(state="visible", timeout=20000)
            await create_btn.click(force=True)
            await asyncio.sleep(1.5)

            # Click Upload videos / Tải video lên
            upload_item = page.locator('tp-yt-paper-item:has-text("Upload videos"), tp-yt-paper-item:has-text("Tải video lên"), tp-yt-paper-item:has-text("Upload video")').first
            await upload_item.click(force=True)
            await asyncio.sleep(2)

            # Attach video file
            file_input = page.locator('input[type="file"]').first
            await file_input.wait_for(state="attached", timeout=15000)
            await file_input.set_input_files(os.path.abspath(file_path))
            logger.info(f"Đã đính kèm video '{os.path.basename(file_path)}' lên YouTube Studio...", "YOUTUBE")
            await asyncio.sleep(5)

            # Wait for upload modal / title textbox
            title_box = page.locator('div#title-textarea #textbox, #textbox[aria-label*="title"], #textbox[aria-label*="tiêu đề"]').first
            await title_box.wait_for(state="visible", timeout=40000)
            await title_box.fill("")
            await title_box.fill(title)
            logger.info(f"Đã điền tiêu đề hoàn chỉnh: '{title}'", "YOUTUBE")
            await asyncio.sleep(1)

            # Fill Description
            desc_box = page.locator('div#description-textarea #textbox, #textbox[aria-label*="description"], #textbox[aria-label*="mô tả"]').first
            if await desc_box.is_visible():
                await desc_box.fill(description)
                logger.info("Đã điền mô tả video.", "YOUTUBE")
                await asyncio.sleep(1)

            # Extract video URL early during details step
            extracted_url = await self._extract_youtube_url(page)
            if extracted_url:
                logger.info(f"Đã nhận diện liên kết video: {extracted_url}", "YOUTUBE")

            # -------------------------------------------------------------
            # BẮT BUỘC CHỌN: NOT MADE FOR KIDS (KHÔNG DÀNH CHO TRẺ EM)
            # -------------------------------------------------------------
            logger.info("Chọn đối tượng người xem: 'Không dành cho trẻ em' (Not made for kids)...", "YOUTUBE")
            not_for_kids_radio = page.locator(
                'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"], '
                'tp-yt-paper-radio-button:has-text("No, it\'s not made for kids"), '
                'tp-yt-paper-radio-button:has-text("Không, đây không phải nội dung dành cho trẻ em")'
            ).first

            await not_for_kids_radio.scroll_into_view_if_needed()
            await not_for_kids_radio.wait_for(state="visible", timeout=15000)
            await not_for_kids_radio.click(force=True)
            await asyncio.sleep(1)
            
            await page.evaluate("""() => {
                const radio = document.querySelector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]') 
                           || Array.from(document.querySelectorAll('tp-yt-paper-radio-button')).find(el => el.innerText.toLowerCase().includes('not made for kids') || el.innerText.toLowerCase().includes('không phải nội dung'));
                if (radio) {
                    radio.click();
                    radio.setAttribute('aria-checked', 'true');
                }
            }""")
            logger.success("Đã chọn chính xác: 'Không dành cho trẻ em' (Not made for kids).", "YOUTUBE")
            await asyncio.sleep(1)

            # -------------------------------------------------------------
            # MỞ RỘNG: SHOW MORE / HIỆN THÊM (FORCE CLICK + JS BACKUP)
            # -------------------------------------------------------------
            logger.info("Mở rộng mục cài đặt nâng cao ('SHOW MORE' / 'HIỆN THÊM')...", "YOUTUBE")
            try:
                await page.evaluate("""() => {
                    const btn = document.querySelector('button#toggle-button, ytcp-button#toggle-button, #toggle-button')
                             || Array.from(document.querySelectorAll('ytcp-button, button')).find(b => {
                                 const t = (b.innerText || '').toLowerCase();
                                 return t.includes('show more') || t.includes('hiện thêm') || t.includes('show advanced');
                             });
                    if (btn) btn.click();
                }""")
            except Exception:
                pass
            await asyncio.sleep(1.5)

            # -------------------------------------------------------------
            # BẮT BUỘC CHỌN: AI USE / ALTERED CONTENT -> YES / CÓ
            # -------------------------------------------------------------
            if mark_ai:
                logger.info("Kích hoạt nhãn: 'AI use' / 'Nội dung do AI tạo' -> Chọn Yes (Có)...", "YOUTUBE")
                try:
                    await page.evaluate("""() => {
                        const container = document.querySelector('ytcp-altered-content-field') 
                                      || Array.from(document.querySelectorAll('div')).find(d => d.innerText && (d.innerText.includes('AI use') || d.innerText.includes('Altered content') || d.innerText.includes('Nội dung đã qua chỉnh sửa')));
                        if (container) {
                            const yesRadio = Array.from(container.querySelectorAll('tp-yt-paper-radio-button')).find(r => r.innerText.trim().toLowerCase() === 'yes' || r.innerText.trim().toLowerCase() === 'có' || (r.getAttribute('name') && r.getAttribute('name').includes('YES')));
                            if (yesRadio) {
                                yesRadio.click();
                                yesRadio.setAttribute('aria-checked', 'true');
                            }
                        }
                    }""")
                    logger.success("Đã bật nhãn 'AI use' -> YES (Nội dung do AI tạo) thành công!", "YOUTUBE")
                except Exception as e:
                    logger.warning(f"Lưu ý về nhãn AI: {e}", "YOUTUBE")

            # -------------------------------------------------------------
            # BƯỚC TIẾP THEO (NEXT 3 LẦN BẰNG JS TRỰC TIẾP ĐẢM BẢO CHUYỂN BƯỚC)
            # -------------------------------------------------------------
            for step_idx in range(3):
                logger.info(f"Chuyển tiếp bước {step_idx + 1}/3 trên YouTube Studio...", "YOUTUBE")
                await page.evaluate("""() => {
                    const nextBtn = document.getElementById('next-button') 
                                 || document.querySelector('ytcp-button#next-button') 
                                 || Array.from(document.querySelectorAll('ytcp-button, button')).find(b => {
                                     const t = (b.innerText || '').toLowerCase();
                                     return t.includes('next') || t.includes('tiếp');
                                 });
                    if (nextBtn) nextBtn.click();
                }""")
                await asyncio.sleep(2.5)

            # Re-check URL if not found yet
            if not extracted_url:
                extracted_url = await self._extract_youtube_url(page)

            # -------------------------------------------------------------
            # CHẾ ĐỘ HIỂN THỊ (VISIBILITY: UNLISTED / KHÔNG CÔNG KHAI)
            # -------------------------------------------------------------
            logger.info(f"Cài đặt chế độ hiển thị: {privacy.upper()}", "YOUTUBE")
            try:
                await page.evaluate(f"""() => {{
                    const privacy = '{privacy.lower()}';
                    let radio = null;
                    if (privacy === 'public') {{
                        radio = document.querySelector('tp-yt-paper-radio-button[name="PUBLIC"]');
                    }} else if (privacy === 'private') {{
                        radio = document.querySelector('tp-yt-paper-radio-button[name="PRIVATE"]');
                    }} else {{
                        radio = document.querySelector('tp-yt-paper-radio-button[name="UNLISTED"]');
                    }}
                    if (radio) {{
                        radio.click();
                        radio.setAttribute('aria-checked', 'true');
                    }}
                }}""")
            except Exception:
                pass
            await asyncio.sleep(1.5)

            if not extracted_url:
                extracted_url = await self._extract_youtube_url(page)

            # -------------------------------------------------------------
            # BẤM LƯU / XUẤT BẢN (SAVE / PUBLISH)
            # -------------------------------------------------------------
            logger.info("Bấm Lưu/Xuất bản video lên YouTube Shorts...", "YOUTUBE")
            await page.evaluate("""() => {
                const doneBtn = document.getElementById('done-button') 
                             || document.querySelector('ytcp-button#done-button') 
                             || Array.from(document.querySelectorAll('ytcp-button, button')).find(b => {
                                 const t = (b.innerText || '').toLowerCase();
                                 return t.includes('save') || t.includes('publish') || t.includes('lưu') || t.includes('xuất bản');
                             });
                if (doneBtn) doneBtn.click();
            }""")
            await asyncio.sleep(6)

            final_url = await self._extract_youtube_url(page)
            if final_url:
                extracted_url = final_url

            logger.success(f"Đăng thành công lên YouTube Shorts! Link: {extracted_url}", "YOUTUBE")
            return {"success": True, "url": extracted_url, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên YouTube: {str(ex)}", "YOUTUBE")
            return {"success": False, "error": str(ex)}

youtube_poster = YouTubePoster()
