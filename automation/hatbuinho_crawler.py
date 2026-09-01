import os
import re
import asyncio
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from core.logger import logger
from core.config_manager import config_mgr
from core.database import db
from automation.browser_engine import browser_engine, DOWNLOADS_DIR
from automation.hashtag_manager import hashtag_mgr

class HatBuiNhoCrawler:
    def __init__(self):
        self.base_url = "https://hatbuinho.com/"

    async def login_if_needed(self, page: Page) -> bool:
        hat_config = config_mgr.get("hatbuinho", {})
        username = hat_config.get("username", "cun")
        password = hat_config.get("password", "123")

        logger.info(f"Kiểm tra trạng thái đăng nhập hatbuinho.com (User: {username})...", "HATBUINHO")
        await page.goto(self.base_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2)

        # Check if login button is present
        login_btn = page.locator('button:has-text("Đăng nhập")').first
        if await login_btn.is_visible():
            logger.info("Chưa đăng nhập, tiến hành đăng nhập tự động...", "HATBUINHO")
            await login_btn.click()
            await asyncio.sleep(1)

            # Fill credentials
            await page.fill('input#email', username)
            await page.fill('input#password', password)

            # Check remember if available
            remember_cb = page.locator('input#remember')
            if await remember_cb.is_visible():
                try:
                    await remember_cb.check()
                except Exception:
                    pass

            # Click Submit button
            submit_btn = page.locator('button:has-text("BẮT ĐẦU NGAY")').first
            await submit_btn.click()
            await asyncio.sleep(3)
            logger.success("Đã gửi thông tin đăng nhập.", "HATBUINHO")

        # Dismiss announcement dialog if visible
        try:
            read_btn = page.locator('button:has-text("Đã đọc")').first
            if await read_btn.is_visible(timeout=3000):
                await read_btn.click()
                logger.info("Đã đóng thông báo hệ thống ('Đã đọc').", "HATBUINHO")
                await asyncio.sleep(1)
        except Exception:
            pass

        return True

    def _clean_script_text(self, text: str) -> str:
        """Làm sạch văn bản kịch bản, loại bỏ các icon, nhãn thừa và dấu thời gian"""
        if not text:
            return ""
        cleaned = re.sub(r'^\s*\d{1,2}:\d{2}\s*', '', text)
        for word in ["Chưa tải xuống", "Hoàn thành", "Đã tải xuống", "▲ Đóng", "▼ Mở", "Đóng", "Mở"]:
            cleaned = cleaned.replace(word, "")
        cleaned = re.sub(r'[✅📝✨🎉💡👉📌▼▲🥰🧠]', '', cleaned)
        return cleaned.strip()

    def _extract_clean_first_sentence(self, script_text: str, max_length: int = 85) -> str:
        """Trích câu đầu tiên hoàn chỉnh, ngắt chuẩn theo từ ngữ không bao giờ bị cắt cụt từ"""
        if not script_text:
            return "Video Đạo Lý Hay"
        
        sentences = re.split(r'[\.\!\?\n]', script_text)
        first = sentences[0].strip() if sentences else script_text.strip()
        first = re.sub(r'\s+', ' ', first)

        if len(first) <= max_length:
            return first

        truncated = first[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > 30:
            truncated = truncated[:last_space]
        return truncated.strip()

    def _parse_suggestion(self, text: str) -> Dict[str, str]:
        """Tách Tiêu đề từ hộp gợi ý của HatBuiNho (bỏ số thứ tự 1., 2.)"""
        if not text or "Chưa có gợi ý" in text or "Bấm `TẢI XUỐNG` để xem" in text:
            return {"suggested_title": "", "hashtags": ""}

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        title_candidates = []

        for line in lines:
            if "#" not in line:
                clean_line = re.sub(r'^\d+[\.\)]\s*', '', line)
                clean_line = clean_line.replace("🧠", "").replace("Gợi ý tiêu đề & hashtag", "").replace("Vuốt để xem thêm", "").strip()
                if clean_line and len(clean_line) > 3:
                    title_candidates.append(clean_line)

        suggested_title = title_candidates[0] if title_candidates else ""
        return {"suggested_title": suggested_title}

    async def scan_and_download(self, max_items: Optional[int] = None, force_latest: bool = False) -> List[Dict[str, Any]]:
        """Quét danh sách video 'Đã xong' và tải về kèm hashtag đạo lý ngẫu nhiên"""
        downloaded_videos = []
        page = await browser_engine.get_page()

        try:
            await self.login_if_needed(page)

            # Open Video History view via toggleHistory()
            mode_str = "[CHẾ ĐỘ TEST: Ép tải video mới nhất]" if force_latest else "[CHẾ ĐỘ CHUẨN: Chỉ tải video 'Chưa tải xuống']"
            logger.info(f"Mở mục Lịch sử Video (#btn_view_history)... {mode_str}", "HATBUINHO")
            
            await page.evaluate("""() => {
                if (typeof toggleHistory === 'function') {
                    toggleHistory();
                } else {
                    const btn = document.getElementById('btn_view_history');
                    if (btn) btn.click();
                }
            }""")
            await asyncio.sleep(2)

            # Ensure 'Đã xong' tab is active
            await page.evaluate("""() => {
                const doneTab = document.getElementById('history_tab_done');
                if (doneTab) doneTab.click();
            }""")
            await asyncio.sleep(2)

            # Query all video items
            items = await page.locator('details.history-order').all()
            logger.info(f"Tìm thấy tổng cộng {len(items)} mục video trên trang.", "HATBUINHO")

            count = 0
            for idx in range(len(items)):
                if max_items and count >= max_items:
                    logger.info(f"Đã đạt giới hạn quét ({max_items} video).", "HATBUINHO")
                    break

                try:
                    item_locator = page.locator('details.history-order').nth(idx)
                    
                    if not force_latest:
                        badge = item_locator.locator('summary span:has-text("Chưa tải xuống")').first
                        if not await badge.is_visible():
                            continue

                    # Extract raw script text / summary
                    summary_el = item_locator.locator('summary').first
                    summary_text = await summary_el.inner_text()
                    raw_script = self._clean_script_text(summary_text)
                    item_hash = hashlib.md5(raw_script.encode('utf-8')).hexdigest()[:12]

                    logger.info(f"Xử lý video #{idx+1} ({'Test ép tải' if force_latest else 'Chưa tải xuống'}): '{raw_script[:60]}...'", "HATBUINHO")

                    # Open details and trigger download modal
                    await item_locator.evaluate("""el => {
                        el.open = true;
                        const btns = el.querySelectorAll('button');
                        for (let b of btns) {
                            if (b.innerText.includes('Tải xuống')) {
                                b.click();
                                break;
                            }
                        }
                    }""")
                    await asyncio.sleep(2)

                    # Wait for download modal #download_reminder_modal
                    modal = page.locator('#download_reminder_modal').first
                    await modal.wait_for(state="visible", timeout=10000)

                    # Extract suggested title if available
                    sug_el = modal.locator('#download_title_hashtag_suggestions').first
                    suggestion_text = await sug_el.inner_text() if await sug_el.is_visible() else ""
                    parsed_meta = self._parse_suggestion(suggestion_text)
                    suggested_title = parsed_meta["suggested_title"]
                    
                    # Nếu trên web chưa có gợi ý AI sẵn -> trích câu đầu tiên chuẩn xác không cụt từ
                    if not suggested_title:
                        suggested_title = self._extract_clean_first_sentence(raw_script)
                    
                    # Sinh bộ Hashtag Đạo Lý & Phật Pháp ngẫu nhiên chuẩn xác
                    hashtags = hashtag_mgr.generate_random_hashtags(raw_script, count=5)

                    logger.info(f"-> Tiêu đề hoàn chỉnh: '{suggested_title}'", "HATBUINHO")
                    logger.info(f"-> Bộ Hashtag tự động: '{hashtags}'", "HATBUINHO")

                    # Trigger download via button #btn_confirm_download_2 ('Tải xuống 2 - có tên')
                    btn_download_2 = modal.locator('button#btn_confirm_download_2, button:has-text("Tải xuống 2")').first
                    await btn_download_2.wait_for(state="visible", timeout=8000)

                    async with page.expect_download(timeout=90000) as download_info:
                        await btn_download_2.click()
                        logger.info("Đã bấm 'Tải xuống 2 - có tên', đang nhận tệp video...", "HATBUINHO")

                    download = await download_info.value
                    original_name = download.suggested_filename or f"video_{item_hash}.mp4"
                    
                    # Sanitize filename
                    clean_name = re.sub(r'[\\/*?:"<>|]', "", original_name)
                    if not clean_name.endswith(".mp4"):
                        clean_name += ".mp4"

                    target_file_path = os.path.join(DOWNLOADS_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{clean_name}")
                    await download.save_as(target_file_path)

                    file_size = os.path.getsize(target_file_path) if os.path.exists(target_file_path) else 0
                    logger.success(f"Tải video thành công: {os.path.basename(target_file_path)} ({file_size // 1024} KB)", "HATBUINHO")

                    video_record = {
                        "hatbuinho_id": item_hash if not force_latest else f"{item_hash}_{datetime.now().strftime('%H%M%S')}",
                        "title": clean_name.replace(".mp4", ""),
                        "raw_script": raw_script,
                        "suggested_title": suggested_title,
                        "hashtags": hashtags,
                        "file_path": target_file_path,
                        "file_size": file_size,
                        "status": "downloaded",
                        "created_date_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

                    # Save to DB
                    db.add_or_update_video(video_record)
                    downloaded_videos.append(video_record)
                    count += 1

                    # Close modal dialog
                    try:
                        close_btn = modal.locator('button:has-text("×")').first
                        if await close_btn.is_visible():
                            await close_btn.click()
                            await asyncio.sleep(1)
                    except Exception:
                        pass

                except Exception as e:
                    logger.error(f"Lỗi khi xử lý video item #{idx+1}: {str(e)}", "HATBUINHO")
                    try:
                        await page.evaluate("""() => {
                            const m = document.getElementById('download_reminder_modal');
                            if (m) m.classList.add('hidden');
                        }""")
                    except Exception:
                        pass
                    continue

            logger.success(f"Hoàn thành quét: Đã tải về {len(downloaded_videos)} video mới.", "HATBUINHO")
            return downloaded_videos

        except Exception as ex:
            logger.error(f"Lỗi trong quá trình quét HatBuiNho: {str(ex)}", "HATBUINHO")
            return downloaded_videos

hatbuinho_crawler = HatBuiNhoCrawler()
