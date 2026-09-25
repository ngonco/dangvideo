import os
import re
import asyncio
import hashlib
import urllib.request
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from core.logger import logger
from core.config_manager import config_mgr, SYSTEM_DIR
from core.database import db
from automation.browser_engine import browser_engine, DOWNLOADS_DIR
from automation.hashtag_manager import hashtag_mgr

class VersionSelectionResult(dict):
    """Kết quả chọn phiên bản, kế thừa dict để truy xuất thuộc tính và hỗ trợ int(result)."""
    def __int__(self):
        return int(self.get("version_n", 1))

    def __index__(self):
        return int(self.get("version_n", 1))

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

    async def _ensure_history_item_open(self, item_locator) -> None:
        """Mở <details> bằng click summary (nhìn thấy được), không chỉ gán el.open."""
        await item_locator.scroll_into_view_if_needed()
        await asyncio.sleep(0.35)
        is_open = await item_locator.evaluate("el => !!el.open")
        if not is_open:
            await item_locator.locator("summary").first.click(force=True)
            await asyncio.sleep(0.5)
            await item_locator.evaluate("el => { el.open = true; }")
        await asyncio.sleep(0.6)

    async def _click_download_button(self, target_locator, fallback_target=None) -> bool:
        """Bấm nút Tải xuống / Tải lại với cơ chế định vị linh hoạt và fallback JavaScript."""
        for label in ["Tải xuống", "Tải lại", "TẢI XUỐNG", "TẢI LẠI", "Download"]:
            try:
                dl_btn = target_locator.locator("button").filter(has_text=label).first
                if await dl_btn.is_visible(timeout=1500):
                    await dl_btn.scroll_into_view_if_needed()
                    await asyncio.sleep(0.2)
                    await dl_btn.click(timeout=4000)
                    logger.info(f"Đã bấm nút '{label}' qua locator.", "HATBUINHO")
                    return True
            except Exception:
                pass

        try:
            clicked_label = await target_locator.evaluate("""el => {
                const btns = Array.from(el.querySelectorAll('button'));
                const dl = btns.find(b => {
                    const t = (b.innerText || b.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const oc = (b.getAttribute('onclick') || '').toLowerCase();
                    return t.includes('tải xuống') || t.includes('tải lại') || t.includes('download') || oc.includes('safemobiledownload');
                });
                if (dl) {
                    dl.scrollIntoView({ block: 'center' });
                    dl.click();
                    return dl.innerText || dl.textContent || 'Download button';
                }
                return null;
            }""")
            if clicked_label:
                logger.info(f"Đã bấm nút tải qua JS fallback: '{clicked_label.strip()}'.", "HATBUINHO")
                return True
        except Exception:
            pass

        if fallback_target is not None:
            return await self._click_download_button(fallback_target)

        return False

    def _check_url_alive(self, url: str, timeout: int = 5) -> bool:
        """Kiểm tra nhanh xem URL media có phản hồi 200 OK (tệp còn tồn tại trên CDN) hay không."""
        if not url:
            return False
        try:
            clean_url = url.split("?")[0]
            req = urllib.request.Request(clean_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def _direct_download_media(self, page: Page, media_url: str, target_file_path: str, order_id: Optional[str] = None) -> bool:
        """Tải trực tiếp video từ media_url về target_file_path bằng stream khi modal download của trình duyệt bị hủy hoặc lỗi."""
        try:
            clean_url = media_url.split("?")[0]
            logger.info(f"Tiến hành tải trực tiếp từ URL: {clean_url}...", "HATBUINHO")
            
            def _stream_dl():
                req = urllib.request.Request(clean_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=90) as resp, open(target_file_path, "wb") as out_f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        out_f.write(chunk)

            await asyncio.to_thread(_stream_dl)

            if os.path.exists(target_file_path) and os.path.getsize(target_file_path) > 0:
                logger.success(f"Tải trực tiếp thành công: {os.path.basename(target_file_path)} ({os.path.getsize(target_file_path) // 1024} KB).", "HATBUINHO")
                if order_id:
                    try:
                        await page.evaluate("""([oid, url]) => {
                            if (typeof postTrackDownload === 'function') {
                                postTrackDownload(oid, url);
                            }
                        }""", [order_id, media_url])
                    except Exception:
                        pass
                return True
            return False
        except Exception as e:
            logger.error(f"Lỗi tải trực tiếp dự phòng: {e}", "HATBUINHO")
            return False

    async def _select_highest_version_and_open_download(self, item_locator) -> Optional[VersionSelectionResult]:
        """Phân tích các phiên bản (nếu có) hoặc video đơn bản duy nhất.
        - Tự động chọn phiên bản có ngày tạo mới nhất (timestamp) và còn tồn tại trên máy chủ (HTTP 200).
        - Nếu phiên bản mới nhất bị 404, tự động thử các phiên bản khác còn sống.
        - Với video đơn bản (không có tab), bấm trực tiếp nút Tải xuống của thẻ video.
        - Bấm nút Tải xuống tương ứng để mở modal #download_reminder_modal.
        """
        await self._ensure_history_item_open(item_locator)

        # Trích xuất thông tin các tab và nút tải bằng JavaScript evaluate
        extracted = await item_locator.evaluate("""el => {
            const tabs = Array.from(el.querySelectorAll('button.history-variant-tab, button[id^="hvt-"]'));
            const panels = Array.from(el.querySelectorAll('.hist-ver-panel'));

            function parseMediaFromRoot(root) {
                if (!root) return null;
                const buttons = Array.from(root.querySelectorAll('button'));
                for (const b of buttons) {
                    const oc = b.getAttribute('onclick') || '';
                    const m = oc.match(/https:\\/\\/media\\.hatbuinho\\.com\\/[^'"]+/);
                    if (m) {
                        const fnMatch = oc.match(/safeMobileDownload\\([^,]+,\\s*[^,]+,\\s*['"]([^'"]+)['"]\\)/);
                        const orderMatch = oc.match(/safeMobileDownload\\([^,]+,\\s*['"]([^'"]+)['"]/);
                        return {
                            mediaUrl: m[0],
                            orderId: orderMatch ? orderMatch[1] : '',
                            suggestedFilename: fnMatch ? fnMatch[1] : '',
                        };
                    }
                }
                return null;
            }

            if (tabs.length > 1) {
                const variants = [];
                for (let i = 0; i < tabs.length; i++) {
                    const tab = tabs[i];
                    const tabText = (tab.textContent || tab.innerText || '').replace(/\\s+/g, ' ').trim();
                    const isActive = tab.classList.contains('history-variant-tab--active');
                    const panel = panels[i] || document.getElementById(tab.id.replace('hvt-', 'hvp-'));
                    const media = parseMediaFromRoot(panel);
                    variants.push({
                        index: i,
                        tabId: tab.id,
                        tabText: tabText || ('Phiên bản ' + (i + 1)),
                        isActive: isActive,
                        panelId: panel ? panel.id : null,
                        mediaUrl: media ? media.mediaUrl : '',
                        orderId: media ? media.orderId : '',
                        suggestedFilename: media ? media.suggestedFilename : ''
                    });
                }
                return { isMulti: true, variants: variants };
            } else {
                const media = parseMediaFromRoot(el);
                return {
                    isMulti: false,
                    variants: media ? [{
                        index: 0,
                        tabId: null,
                        tabText: 'Bản gốc',
                        isActive: true,
                        panelId: null,
                        mediaUrl: media.mediaUrl,
                        orderId: media.orderId,
                        suggestedFilename: media.suggestedFilename
                    }] : []
                };
            }
        }""")

        is_multi = extracted.get("isMulti", False)
        variants = extracted.get("variants", [])

        if not variants:
            logger.info("Không trích xuất được link video trong DOM, bấm nút Tải xuống mặc định...", "HATBUINHO")
            clicked = await self._click_download_button(item_locator)
            if not clicked:
                raise RuntimeError("Không thấy hoặc không thể bấm nút Tải xuống của video này.")
            return VersionSelectionResult(version_n=1, media_url="", order_id="", suggested_filename="")

        # Trường hợp 1: Video đơn bản (chỉ có 1 bản duy nhất, không có tab)
        if not is_multi or len(variants) <= 1:
            single_var = variants[0]
            media_url = single_var.get("mediaUrl") or ""
            logger.info(f"Video đơn bản (không có tab phiên bản phụ). Link: {media_url[:65]}...", "HATBUINHO")
            
            if media_url:
                is_alive = await asyncio.to_thread(self._check_url_alive, media_url, 4)
                if not is_alive:
                    logger.warning(f"File video của mục này đã bị máy chủ CDN xóa hoặc hết hạn (404): {media_url}", "HATBUINHO")
                    return None

            clicked = await self._click_download_button(item_locator)
            if not clicked:
                raise RuntimeError("Không bấm được nút Tải xuống của video đơn bản.")
            return VersionSelectionResult(
                version_n=1,
                media_url=media_url,
                order_id=single_var.get("orderId", ""),
                suggested_filename=single_var.get("suggestedFilename", "")
            )

        # Trường hợp 2: Video có nhiều phiên bản (variant tabs)
        def get_timestamp_score(v):
            url = v.get("mediaUrl", "")
            m = re.search(r'/(\d{8}_\d{6})_', url)
            if m:
                return m.group(1)
            return "00000000_000000"

        # Sắp xếp ưu tiên: timestamp mới nhất trước, nếu bằng nhau thì ưu tiên tab đang active
        sorted_candidates = sorted(
            variants,
            key=lambda v: (get_timestamp_score(v), 1 if v.get("isActive") else 0),
            reverse=True
        )

        variants_summary = ', '.join([f"{v.get('tabText')} ({get_timestamp_score(v)})" for v in sorted_candidates])
        logger.info(
            f"Phát hiện {len(variants)} phiên bản: {variants_summary}.",
            "HATBUINHO"
        )

        chosen_candidate = None
        for cand in sorted_candidates:
            m_url = cand.get("mediaUrl")
            if not m_url:
                continue
            is_alive = await asyncio.to_thread(self._check_url_alive, m_url, 4)
            cand_label = cand.get('tabText', '')
            if is_alive:
                chosen_candidate = cand
                logger.info(
                    f"-> Đã chọn '{cand_label}' ({get_timestamp_score(cand)}) - Link hoạt động tốt (HTTP 200).",
                    "HATBUINHO"
                )
                break
            else:
                logger.warning(
                    f"-> Bỏ qua '{cand_label}' vì link máy chủ trả về lỗi hoặc hết hạn (404): {m_url[:65]}...",
                    "HATBUINHO"
                )

        if not chosen_candidate:
            logger.error("Tất cả phiên bản của video này đều bị lỗi 404 trên CDN máy chủ!", "HATBUINHO")
            return None

        # Chuyển tab sang phiên bản đã chọn nếu tab đó chưa active
        chosen_label = chosen_candidate.get('tabText', '')
        if not chosen_candidate.get("isActive"):
            idx = chosen_candidate.get("index", 0)
            tab_locator = item_locator.locator(f"button.history-variant-tab, button[id^='hvt-']").nth(idx)
            try:
                await tab_locator.scroll_into_view_if_needed()
                await tab_locator.click(timeout=3000)
            except Exception:
                await tab_locator.evaluate("el => el.click()")
            logger.info(f"Đã chuyển sang tab '{chosen_label}'.", "HATBUINHO")
            await asyncio.sleep(0.6)

        # Bấm nút Tải xuống trong panel của phiên bản đã chọn
        panel_id = chosen_candidate.get("panelId")
        if panel_id:
            panel_locator = item_locator.locator(f"#{panel_id}")
            clicked = await self._click_download_button(panel_locator, fallback_target=item_locator)
        else:
            visible_panel = item_locator.locator(".hist-ver-panel:not(.hidden)").first
            clicked = await self._click_download_button(visible_panel, fallback_target=item_locator)

        if not clicked:
            raise RuntimeError(f"Không thể bấm nút Tải xuống của {chosen_candidate.get('tabText')}.")

        match = re.search(r"(\d+)", chosen_candidate.get("tabText", ""))
        v_num = int(match.group(1)) if match else (chosen_candidate.get("index", 0) + 1)

        return VersionSelectionResult(
            version_n=v_num,
            media_url=chosen_candidate.get("mediaUrl", ""),
            order_id=chosen_candidate.get("orderId", ""),
            suggested_filename=chosen_candidate.get("suggestedFilename", "")
        )

    async def login_if_needed(self, page: Page) -> bool:
        hat_config = config_mgr.get("hatbuinho", {})
        username = (hat_config.get("username") or "").strip()
        password = hat_config.get("password") or ""

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
            if not username or not password:
                logger.warning(
                    "Chưa có tài khoản HatBuiNho trong Dashboard. Điền tài khoản/mật khẩu rồi thử lại.",
                    "HATBUINHO",
                )
                return False
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
            await asyncio.sleep(2)

            # Xử lý thông báo giới hạn 2 thiết bị nếu xuất hiện
            kick_btn = page.locator('button:has-text("Đăng nhập và đăng xuất máy cũ")').first
            try:
                if await kick_btn.is_visible(timeout=3000):
                    logger.info("Phát hiện cảnh báo 2 thiết bị: Bấm 'Đăng nhập và đăng xuất máy cũ'...", "HATBUINHO")
                    await kick_btn.click()
                    await asyncio.sleep(3)
            except Exception:
                pass

            logger.success("Đã gửi thông tin đăng nhập.", "HATBUINHO")
            await asyncio.sleep(2)

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
        force_repost: bool = False,
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
            logger.info(f"Tìm thấy tổng cộng {total_items} mục video trên trang HatBuiNho.", "HATBUINHO")

            # Tìm danh sách index các video 'Chưa tải xuống'
            pending_indexes = []
            downloaded_count_on_page = 0
            other_status_count = 0
            for idx in range(total_items):
                try:
                    item_locator = page.locator('details.history-order').nth(idx)
                    if force_latest or force_repost:
                        pending_indexes.append(idx)
                    else:
                        badge_pending = item_locator.locator('summary span:has-text("Chưa tải xuống")').first
                        if await badge_pending.is_visible():
                            pending_indexes.append(idx)
                        else:
                            badge_done = item_locator.locator('summary span:has-text("Đã tải xuống")').first
                            if await badge_done.is_visible():
                                downloaded_count_on_page += 1
                            else:
                                other_status_count += 1
                except Exception:
                    pass

            logger.info(
                f"Phân tích trạng thái {total_items} video trên HatBuiNho: "
                f"{len(pending_indexes)} 'Chưa tải xuống', "
                f"{downloaded_count_on_page} 'Đã tải xuống'"
                f"{f', {other_status_count} trạng thái khác' if other_status_count else ''}.",
                "HATBUINHO"
            )

            use_latest = bool(force_latest or force_repost)
            if not pending_indexes and not use_latest:
                slots = config_mgr.get("schedule", {}).get("post_time_slots", ["08:00", "11:30", "19:30"])
                queue_summary = db.get_queue_summary(slots_per_day=len(slots))
                total_pending = queue_summary.get("total_pending", 0)
                logger.info(
                    f"Toàn bộ {total_items} video hiển thị trên HatBuiNho đều đã có nhãn 'Đã tải xuống' hoặc đã tải về trước đó. "
                    f"Kho hàng đợi hiện có {total_pending} video sẵn sàng đăng (chống đăng trùng: BẬT).",
                    "HATBUINHO"
                )
                return downloaded_videos

            if not pending_indexes and fallback_latest and total_items > 0:
                if force_repost:
                    logger.info(
                        "Đã hết video 'Chưa tải xuống' trên HatBuiNho và người dùng đã xác nhận ép đăng lại (force_repost=True). Chuyển sang tải video mới nhất.",
                        "HATBUINHO",
                    )
                    pending_indexes = list(range(total_items))
                    use_latest = True
                    oldest_first = False
                else:
                    slots = config_mgr.get("schedule", {}).get("post_time_slots", ["08:00", "11:30", "19:30"])
                    queue_summary = db.get_queue_summary(slots_per_day=len(slots))
                    total_pending = queue_summary.get("total_pending", 0)
                    logger.info(
                        f"Đã hết video 'Chưa tải xuống' trên HatBuiNho. Dừng lại an toàn, không tự ý đăng lại video cũ (chống đăng trùng). Kho hiện có {total_pending} video sẵn sàng.",
                        "HATBUINHO",
                    )
                    return downloaded_videos

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

                    # LỚP 1: CHẶN TRÙNG TRƯỚC KHI TẢI (KIỂM TRA DB THEO HASH HOẶC KỊCH BẢN)
                    if not force_repost and db.is_video_already_processed(item_hash, raw_script):
                        logger.info(
                            f"[CHẶN TRÙNG LỚP 1] Bỏ qua video #{idx+1} (hash: {item_hash}, '{raw_script[:40]}...') vì đã có trong kho/lịch sử đăng.",
                            "HATBUINHO"
                        )
                        continue

                    logger.info(f"Xử lý video #{idx+1} ({'Ép đăng lại / Video mới nhất' if use_latest else 'Chưa tải xuống'}): '{raw_script[:60]}...'", "HATBUINHO")

                    version_info = await self._select_highest_version_and_open_download(item_locator)
                    if version_info is None:
                        logger.warning(f"Bỏ qua video #{idx+1} vì tệp trên máy chủ không còn khả dụng (404).", "HATBUINHO")
                        continue

                    await asyncio.sleep(1.5)

                    # Wait for download modal #download_reminder_modal
                    modal = page.locator('#download_reminder_modal').first
                    try:
                        await modal.wait_for(state="visible", timeout=10000)
                    except PlaywrightTimeoutError:
                        shot_path = os.path.join(SYSTEM_DIR, "debug_screenshots", f"hbn_modal_timeout_{idx+1}.png")
                        try:
                            await page.screenshot(path=shot_path, full_page=False)
                        except Exception:
                            pass
                        logger.warning(
                            f"Không thấy modal tải xuống (#download_reminder_modal) của video #{idx+1}. Ảnh debug: {shot_path}",
                            "HATBUINHO"
                        )
                        continue

                    # Extract suggested title if available
                    sug_el = modal.locator('#download_title_hashtag_suggestions').first
                    suggestion_text = await sug_el.inner_text() if await sug_el.is_visible() else ""
                    parsed_meta = self._parse_suggestion(suggestion_text)
                    suggested_title = parsed_meta["suggested_title"]
                    
                    # Nếu trên web chưa có gợi ý AI sẵn -> trích câu đầu tiên chuẩn xác không cụt từ
                    if not suggested_title:
                        suggested_title = self._extract_clean_first_sentence(raw_script)
                    
                    # Sinh bộ Hashtag Đạo Lý (100% kho đạo lý thuần túy, không phụ thuộc external AI)
                    hashtags = hashtag_mgr.generate_random_hashtags(raw_script, count=5)

                    logger.info(f"-> Tiêu đề hoàn chỉnh: '{suggested_title}'", "HATBUINHO")
                    logger.info(f"-> Bộ Hashtag tự động: '{hashtags}'", "HATBUINHO")

                    # Sanitize filename
                    file_name_candidate = version_info.get("suggested_filename") or f"video_{item_hash}.mp4"
                    clean_name = re.sub(r'[\\/*?:"<>|]', "", file_name_candidate)
                    if not clean_name.endswith(".mp4"):
                        clean_name += ".mp4"

                    target_file_path = os.path.join(DOWNLOADS_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{clean_name}")

                    download_succeeded = False

                    # Cách 1: Tải qua sự kiện modal của trình duyệt
                    try:
                        btn_download_2 = modal.locator('button#btn_confirm_download_2, button:has-text("Tải xuống 2")').first
                        if await btn_download_2.is_visible(timeout=5000):
                            async with page.expect_download(timeout=45000) as download_info:
                                await btn_download_2.click()
                                logger.info("Đã bấm 'Tải xuống 2 - có tên', đang nhận tệp video qua trình duyệt...", "HATBUINHO")
                            download = await download_info.value
                            await download.save_as(target_file_path)
                            if os.path.exists(target_file_path) and os.path.getsize(target_file_path) > 0:
                                download_succeeded = True
                    except Exception as dl_ex:
                        logger.warning(f"Tải qua modal trình duyệt chưa thành công ({dl_ex}). Kích hoạt cơ chế tải trực tiếp dự phòng...", "HATBUINHO")

                    # Cách 2: Tải trực tiếp stream từ media_url nếu Cách 1 không thành công
                    if not download_succeeded and version_info.get("media_url"):
                        logger.info("Tiến hành tải trực tiếp dự phòng từ link media...", "HATBUINHO")
                        download_succeeded = await self._direct_download_media(
                            page,
                            version_info.get("media_url"),
                            target_file_path,
                            version_info.get("order_id")
                        )

                    if not download_succeeded or not os.path.exists(target_file_path) or os.path.getsize(target_file_path) == 0:
                        raise RuntimeError(f"Không thể tải tệp video cho video #{idx+1} bằng cả 2 cách.")

                    file_size = os.path.getsize(target_file_path)
                    logger.success(f"Tải video thành công: {os.path.basename(target_file_path)} ({file_size // 1024} KB)", "HATBUINHO")

                    # LỚP 2: CHẶN TRÙNG DUNG LƯỢNG FILE (BYTE-TO-BYTE)
                    if not force_repost and file_size > 0:
                        dup_vid = db.get_video_by_file_size(file_size)
                        if dup_vid:
                            logger.warning(
                                f"[CHẶN TRÙNG LỚP 2 - DUNG LƯỢNG] Tệp vừa tải có dung lượng {file_size:,} bytes trùng khớp 100% với video #{dup_vid['id']} ('{dup_vid.get('title')}') đã có trong DB. Đã xóa tệp tạm và bỏ qua không đăng lại!",
                                "HATBUINHO"
                            )
                            try:
                                if os.path.exists(target_file_path):
                                    os.remove(target_file_path)
                            except Exception:
                                pass
                            continue

                    video_record = {
                        "hatbuinho_id": item_hash if not force_repost else f"{item_hash}_{datetime.now().strftime('%H%M%S')}",
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
                    shot_path = os.path.join(SYSTEM_DIR, "debug_screenshots", f"hbn_item_err_{idx+1}.png")
                    try:
                        await page.screenshot(path=shot_path, full_page=False)
                        logger.error(f"Lỗi khi xử lý video item #{idx+1}: {str(e)} (Ảnh debug: {shot_path})", "HATBUINHO")
                    except Exception:
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
            shot_path = os.path.join(SYSTEM_DIR, "debug_screenshots", "hbn_scan_err.png")
            try:
                if page is not None:
                    await page.screenshot(path=shot_path, full_page=False)
            except Exception:
                pass
            logger.error(f"Lỗi trong quá trình quét HatBuiNho: {str(ex)} (Ảnh debug: {shot_path})", "HATBUINHO")
            try:
                from core.email_reporter import email_reporter
                email_reporter.send_error_alert(
                    platform="hatbuinho",
                    error_message=str(ex),
                    step="Quét tải video HatBuiNho",
                    details=shot_path,
                )
            except Exception:
                pass
            return downloaded_videos

hatbuinho_crawler = HatBuiNhoCrawler()
