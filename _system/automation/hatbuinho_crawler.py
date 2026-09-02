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
from automation.ai_fallback import diagnose_and_recover, DOWNLOAD_GOAL

class HatBuiNhoCrawler:
    def __init__(self):
        self.base_url = "https://hatbuinho.com/"

    async def _dismiss_announcements(self, page: Page):
        """Đóng overlay thông báo ('Đã đọc') vì nó chặn nút Video."""
        try:
            await page.evaluate("""() => {
                const readBtn = Array.from(document.querySelectorAll('button')).find(b =>
                    (b.innerText || '').includes('Đã đọc')
                );
                if (readBtn) readBtn.click();
            }""")
            await asyncio.sleep(1)
        except Exception:
            pass

    async def _open_done_video_list(self, page: Page) -> bool:
        """Bắt buộc bấm nút Video (#btn_view_history) rồi mới vào tab Đã xong."""
        await self._dismiss_announcements(page)

        video_btn = page.locator('#btn_view_history').first
        if not await video_btn.is_visible(timeout=8000):
            video_btn = page.locator('button:has-text("Video")').first

        try:
            await video_btn.wait_for(state="visible", timeout=15000)
            await video_btn.click(force=True)
            logger.info("Đã bấm nút Video (#btn_view_history) để mở danh sách lịch sử.", "HATBUINHO")
        except Exception:
            clicked = await page.evaluate("""() => {
                const btn = document.getElementById('btn_view_history');
                if (btn) { btn.click(); return true; }
                return false;
            }""")
            if not clicked:
                logger.error("Không tìm thấy nút Video trên HatBuiNho.", "HATBUINHO")
                return False

        await asyncio.sleep(2)

        await page.evaluate("""() => {
            const doneTab = document.getElementById('history_tab_done');
            if (doneTab) doneTab.click();
        }""")
        logger.info("Đã chuyển sang tab Đã xong.", "HATBUINHO")
        await asyncio.sleep(2)

        count = await page.locator('details.history-order').count()
        if count == 0:
            logger.info("Danh sách trống, bấm Làm mới...", "HATBUINHO")
            try:
                refresh = page.locator('#btn_history_refresh, #btn_history_retry_inline').first
                if await refresh.is_visible(timeout=2000):
                    await refresh.click(force=True)
                    await asyncio.sleep(3)
            except Exception:
                pass

        try:
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.8)
        except Exception:
            pass

        return True

    async def login_if_needed(self, page: Page) -> bool:
        hat_config = config_mgr.get("hatbuinho", {})
        username = hat_config.get("username", "cun")
        password = hat_config.get("password", "123")

        logger.info(f"Kiểm tra session HatBuiNho (cookies trước, User: {username})...", "HATBUINHO")
        await page.goto(self.base_url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2)
        await self._dismiss_announcements(page)

        # Cookie-first: đã vào được khu làm video thì không đăng nhập lại
        video_btn = page.locator('#btn_view_history').first
        if await video_btn.is_visible(timeout=4000):
            logger.success("Session HatBuiNho còn hiệu lực (cookies). Bỏ qua form đăng nhập.", "HATBUINHO")
            return True

        login_btn = page.locator('button:has-text("Đăng nhập")').first
        if await login_btn.is_visible():
            logger.info("Chưa đăng nhập, tiến hành đăng nhập tự động...", "HATBUINHO")
            await login_btn.click()
            await asyncio.sleep(1)

            await page.fill('input#email', username)
            await page.fill('input#password', password)

            remember_cb = page.locator('input#remember')
            if await remember_cb.is_visible():
                try:
                    await remember_cb.check()
                except Exception:
                    pass

            submit_btn = page.locator('button:has-text("BẮT ĐẦU NGAY")').first
            await submit_btn.click()
            await asyncio.sleep(3)
            logger.success("Đã gửi thông tin đăng nhập.", "HATBUINHO")

            try:
                limit_msg = page.locator('text=Tài khoản đang hoạt động nơi khác, text=giới hạn 2 thiết bị').first
                if await limit_msg.is_visible(timeout=2000):
                    logger.error("HatBuiNho báo giới hạn 2 thiết bị. Không spam login — cần session cookie hoặc Admin reset.", "HATBUINHO")
                    return False
            except Exception:
                pass

        await self._dismiss_announcements(page)
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

    def _is_created_today(self, text: str) -> bool:
        """
        Kiểm tra xem video có phải vừa được tạo trong ngày hôm nay hay không.
        - Nếu text chỉ có giờ (ví dụ: '14:20', '08:15') -> Được tạo trong ngày hôm nay.
        - Nếu text có ngày khớp với ngày hôm nay -> Được tạo trong ngày hôm nay.
        - Nếu text có ngày của hôm qua hoặc cũ hơn -> False (an toàn để tải).
        """
        if not text:
            return True

        today = datetime.now()
        today_dmy = today.strftime("%d/%m/%Y")
        today_ymd = today.strftime("%Y-%m-%d")
        today_d_m = today.strftime("%d/%m")

        if today_dmy in text or today_ymd in text or today_d_m in text:
            return True

        date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', text)
        if date_match:
            try:
                d, m, y = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                if y < 100:
                    y += 2000
                vid_date = datetime(y, m, d).date()
                if vid_date >= today.date():
                    return True
                else:
                    return False
            except Exception:
                pass

        if re.match(r'^\s*\d{1,2}:\d{2}', text):
            return True

        return False

    async def scan_and_download(
        self,
        max_items: Optional[int] = None,
        force_latest: bool = False,
        oldest_first: bool = True,
        exclude_today: bool = False,
        fallback_latest: bool = False,
    ) -> List[Dict[str, Any]]:
        """Quét danh sách video 'Đã xong' và tải về kèm hashtag đạo lý ngẫu nhiên"""
        downloaded_videos = []
        page = None
        try:
            ctx = await browser_engine.get_context()
            page = await browser_engine.get_page(ctx)

            logged_in = await self.login_if_needed(page)
            if not logged_in:
                logger.error("Không có session HatBuiNho hợp lệ. Dừng quét tải.", "HATBUINHO")
                return downloaded_videos

            logger.info("Mở danh sách video: bấm nút Video rồi tab Đã xong...", "HATBUINHO")
            opened = await self._open_done_video_list(page)
            if not opened:
                logger.error("Không mở được danh sách video HatBuiNho.", "HATBUINHO")
                return downloaded_videos

            # Query all video items
            total_items = await page.locator('details.history-order').count()
            logger.info(f"Tìm thấy tổng cộng {total_items} mục video trên trang.", "HATBUINHO")

            # Tìm danh sách index các video 'Chưa tải xuống'
            pending_indexes = []
            for idx in range(total_items):
                try:
                    item_locator = page.locator('details.history-order').nth(idx)
                    if force_latest:
                        pending_indexes.append(idx)
                    else:
                        badge = item_locator.locator('summary span:has-text("Chưa tải xuống")').first
                        if await badge.is_visible():
                            pending_indexes.append(idx)
                except Exception:
                    pass

            logger.info(f"Phát hiện {len(pending_indexes)} video 'Chưa tải xuống'.", "HATBUINHO")

            use_latest = bool(force_latest)
            if not pending_indexes and fallback_latest and total_items > 0:
                logger.info(
                    "Đã hết video 'Chưa tải xuống' trên HatBuiNho. Chuyển sang tải video mới nhất.",
                    "HATBUINHO",
                )
                pending_indexes = list(range(total_items))
                use_latest = True
                oldest_first = False

            # Nếu oldest_first = True: đảo ngược danh sách để lấy video cũ nhất trước
            if oldest_first and not use_latest:
                target_indexes = list(reversed(pending_indexes))
            else:
                target_indexes = pending_indexes

            count = 0
            for idx in target_indexes:
                if max_items and count >= max_items:
                    logger.info(f"Đã đạt giới hạn quét ({max_items} video).", "HATBUINHO")
                    break

                try:
                    item_locator = page.locator('details.history-order').nth(idx)
                    
                    if not use_latest:
                        badge = item_locator.locator('summary span:has-text("Chưa tải xuống")').first
                        if not await badge.is_visible():
                            continue

                    # Extract raw script text / summary
                    summary_el = item_locator.locator('summary').first
                    summary_text = await summary_el.inner_text()

                    # BỘ LỌC AN TOÀN: Bỏ qua video tạo trong ngày hôm nay khi chạy tự động
                    if exclude_today and not use_latest:
                        if self._is_created_today(summary_text):
                            logger.info(f"Bỏ qua video #{idx+1} vì được tạo trong ngày hôm nay (để tránh video đang chỉnh sửa dở).", "HATBUINHO")
                            continue

                    raw_script = self._clean_script_text(summary_text)
                    item_hash = hashlib.md5(raw_script.encode('utf-8')).hexdigest()[:12]

                    logger.info(f"Xử lý video #{idx+1} ({'Video mới nhất' if use_latest else 'Chưa tải xuống'}): '{raw_script[:60]}...'", "HATBUINHO")

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
                    
                    # Sinh bộ Hashtag Đạo Lý rồi AI bổ sung hashtag phổ biến (không chữ ký thương hiệu)
                    hashtags = hashtag_mgr.generate_random_hashtags(raw_script, count=5)
                    try:
                        hashtags = await asyncio.to_thread(
                            hashtag_mgr.enrich_with_popular,
                            suggested_title,
                            raw_script,
                            hashtags,
                        )
                    except Exception as tag_ex:
                        logger.warning(f"Không bổ sung hashtag AI (giữ kho đạo lý): {tag_ex}", "HATBUINHO")

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
                        "hatbuinho_id": item_hash if not use_latest else f"{item_hash}_{datetime.now().strftime('%H%M%S')}",
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
                    recovered = await diagnose_and_recover(page, "hatbuinho", str(e), goal=DOWNLOAD_GOAL)
                    if recovered.get("ok"):
                        logger.success("AI đã xử lý xong bước lệch trên HatBuiNho, tiếp tục quét.", "HATBUINHO")
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
            try:
                if page is not None:
                    recovered = await diagnose_and_recover(page, "hatbuinho", str(ex), goal=DOWNLOAD_GOAL)
                    if recovered.get("ok"):
                        return downloaded_videos
                    diag = recovered.get("diagnosis") or str(ex)
                    shot = recovered.get("screenshot") or ""
                else:
                    diag = str(ex)
                    shot = ""
                from core.email_reporter import email_reporter
                email_reporter.send_error_alert(
                    platform="hatbuinho",
                    error_message=diag,
                    step="Quét tải video HatBuiNho",
                    details=shot,
                )
            except Exception:
                pass
            return downloaded_videos

hatbuinho_crawler = HatBuiNhoCrawler()
