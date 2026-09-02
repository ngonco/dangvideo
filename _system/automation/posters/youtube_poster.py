import os
import re
import asyncio
from typing import Dict, Any, Optional, List
from playwright.async_api import Page
from automation.posters.base_poster import BasePoster
from core.logger import logger
from core.config_manager import config_mgr
from core.schedule_helper import get_native_schedule
from automation.ai_fallback import fail_with_ai, SCHEDULE_GOAL

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

    async def _detect_daily_upload_limit(self, page: Page) -> bool:
        """YouTube nhét banner 'Daily upload limit reached' vào đáy bước Details, thường trong shadow DOM ytcp-*."""
        try:
            return bool(await page.evaluate("""() => {
                const needles = [
                    'daily upload limit reached',
                    'daily upload limit',
                    'đã đạt giới hạn tải lên',
                    'giới hạn tải lên hàng ngày',
                    'uploaded video will be processed in 24 hours'
                ];
                const hit = (s) => {
                    const t = (s || '').toLowerCase();
                    return needles.some(n => t.includes(n));
                };
                function scan(root) {
                    if (!root) return false;
                    if (hit(root.innerText || root.textContent || '')) return true;
                    const children = root.querySelectorAll ? root.querySelectorAll('*') : [];
                    for (const el of children) {
                        if (hit(el.innerText || el.textContent || '')) return true;
                        if (el.shadowRoot && scan(el.shadowRoot)) return true;
                    }
                    if (root.shadowRoot && scan(root.shadowRoot)) return true;
                    return false;
                }
                return scan(document.body);
            }"""))
        except Exception:
            return False

    async def _abort_if_daily_limit(self, page: Page):
        if await self._detect_daily_upload_limit(page):
            logger.error("YouTube báo Daily upload limit reached (banner ở bước Details). Dừng kênh này, không bấm Next/Done.", "YOUTUBE")
            return {
                "success": False,
                "error": "Đã đạt giới hạn tải lên YouTube trong ngày (Daily Limit). Cần đợi 24h hoặc xác minh tài khoản.",
                "url": "",
            }
        return None

    async def post_video(self, page: Page, video_data: Dict[str, Any], privacy_override: Optional[str] = None, schedule_time: Optional[str] = None) -> Dict[str, Any]:
        file_path = video_data.get("file_path", "")
        if not self.validate_video_file(file_path):
            return {"success": False, "error": "File video không hợp lệ"}

        raw_title = video_data.get("suggested_title") or video_data.get("title") or ""
        title = self._clean_title(raw_title)

        description = self.format_caption(video_data)
        yt_config = config_mgr.get("platforms", {}).get("youtube", {})
        mark_ai = yt_config.get("mark_ai", True)
        privacy = privacy_override or yt_config.get("privacy", "public")
        
        native = get_native_schedule(schedule_time or "")
        should_schedule = native["enabled"]
        target_schedule_time = native["time"]
        target_dt = native["datetime"]

        try:
            logger.info("Mở YouTube Studio (https://studio.youtube.com)...", "YOUTUBE")
            await page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Check if login is required and wait for user
            if "accounts.google.com" in page.url or "signin" in page.url or not await page.locator('button#create-icon, ytcp-button#create-icon, button:has-text("CREATE"), button:has-text("TẠO"), button:has-text("Create"), button:has-text("Tạo")').first.is_visible(timeout=5000):
                logger.warning("👉 Chưa đăng nhập YouTube Studio! Vui lòng hoàn tất đăng nhập trên cửa sổ trình duyệt (hệ thống sẽ tự động chờ tối đa 5 phút)...", "YOUTUBE")
                try:
                    await page.bring_to_front()
                except Exception:
                    pass

                logged_in = False
                for sec in range(0, 300, 3):
                    if sec > 0 and sec % 30 == 0:
                        logger.info(f"⏳ [YOUTUBE] Đang chờ bạn đăng nhập... (Đã qua {sec}/300s)", "YOUTUBE")
                    await asyncio.sleep(3)
                    
                    if "accounts.google.com" not in page.url and "signin" not in page.url:
                        btn = page.locator('button#create-icon, ytcp-button#create-icon, button:has-text("CREATE"), button:has-text("TẠO"), button:has-text("Create"), button:has-text("Tạo")').first
                        if await btn.is_visible(timeout=2000):
                            logged_in = True
                            break

                if not logged_in:
                    logger.error("Hết thời gian chờ đăng nhập YouTube (5 phút). Vui lòng đăng nhập trước!", "YOUTUBE")
                    return {"success": False, "error": "Hết thời gian chờ đăng nhập YouTube"}

                logger.success("🎉 Đã phát hiện đăng nhập YouTube thành công! Tiếp tục tiến trình đăng video...", "YOUTUBE")
                await asyncio.sleep(2)

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
            limited = await self._abort_if_daily_limit(page)
            if limited:
                return limited

            # Wait for upload modal / title textbox
            title_box = page.locator('div#title-textarea #textbox, #textbox[aria-label*="title"], #textbox[aria-label*="tiêu đề"]').first
            await title_box.wait_for(state="visible", timeout=40000)
            await title_box.fill("")
            await title_box.fill(title)
            logger.info(f"Đã điền tiêu đề hoàn chỉnh: '{title}'", "YOUTUBE")
            await asyncio.sleep(1)

            limited = await self._abort_if_daily_limit(page)
            if limited:
                return limited

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
                limited = await self._abort_if_daily_limit(page)
                if limited:
                    return limited
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
            # BƯỚC 4: LÊN LỊCH NATIVE 10:00 SÁNG MAI (CÔNG KHAI)
            # -------------------------------------------------------------
            if should_schedule:
                logger.info(f"Cài đặt LÊN LỊCH XUẤT BẢN YouTube: {native['label']} (công khai)...", "YOUTUBE")
                try:
                    await page.evaluate("""() => {
                        const schedRadio = document.querySelector('tp-yt-paper-radio-button[name="SCHEDULE"]')
                                        || document.getElementById('schedule-radio-button')
                                        || Array.from(document.querySelectorAll('tp-yt-paper-radio-button')).find(el => {
                                            const t = (el.innerText || '').toLowerCase();
                                            return t.includes('schedule') || t.includes('lên lịch');
                                        });
                        if (schedRadio) {
                            schedRadio.click();
                            schedRadio.setAttribute('aria-checked', 'true');
                        }
                    }""")
                    await asyncio.sleep(2)

                    day, month, year = native["day"], native["month"], native["year"]
                    date_trigger = page.locator('#datepicker-trigger, ytcp-dropdown-trigger#datepicker-trigger, ytcp-datetime-picker #datepicker-trigger').first
                    if await date_trigger.is_visible(timeout=5000):
                        await date_trigger.click(force=True)
                        await asyncio.sleep(1.2)
                        picked = await page.evaluate(
                            """({day, month, year}) => {
                                const ariaHit = Array.from(document.querySelectorAll('[aria-label]')).find(el => {
                                    const a = (el.getAttribute('aria-label') || '').toLowerCase();
                                    const d = String(day);
                                    return (a.includes(d) && (
                                        a.includes('september') || a.includes('sep') ||
                                        a.includes('thg 9') || a.includes('tháng 9') ||
                                        a.includes(String(year))
                                    )) && a.includes(d) && !el.getAttribute('aria-disabled');
                                });
                                if (ariaHit) { ariaHit.click(); return 'aria'; }

                                const days = Array.from(document.querySelectorAll(
                                    '.calendar-day, ytcp-date-picker [role="button"], ytcp-date-picker td, [class*="calendar"] span'
                                ));
                                const cell = days.find(d => {
                                    const t = (d.innerText || '').trim();
                                    const disabled = d.getAttribute('aria-disabled') === 'true' ||
                                        (d.className || '').toString().includes('unselectable') ||
                                        (d.className || '').toString().includes('disabled');
                                    return t === String(day) && !disabled;
                                });
                                if (cell) { cell.click(); return 'day'; }
                                return '';
                            }""",
                            {"day": day, "month": month, "year": year},
                        )
                        logger.info(f"Đã chọn ngày YouTube: {native['date_dmy']} ({picked or 'thử time'})", "YOUTUBE")
                        await asyncio.sleep(0.8)

                    time_trigger = page.locator('#time-of-day-trigger, ytcp-dropdown-trigger#time-of-day-trigger, input[aria-label*="time"], input[aria-label*="giờ"]').first
                    if await time_trigger.is_visible(timeout=5000):
                        await time_trigger.click(force=True)
                        await asyncio.sleep(1)
                        time_12 = native["time_12h_no_pad"]
                        time_item = page.locator(
                            f'tp-yt-paper-item:has-text("{target_schedule_time}"), '
                            f'tp-yt-paper-item:has-text("{time_12}")'
                        ).first
                        if await time_item.is_visible(timeout=3000):
                            await time_item.click(force=True)
                        else:
                            await page.keyboard.type(target_schedule_time, delay=40)
                            await page.keyboard.press("Enter")
                    logger.success(f"Đã lên lịch YouTube Shorts công khai lúc {native['label']}!", "YOUTUBE")
                except Exception as ex_sched:
                    logger.warning(f"Không thể chọn mốc giờ Schedule chi tiết, tiếp tục với lịch mặc định: {ex_sched}", "YOUTUBE")

            else:
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
            # BẤM LƯU / XUẤT BẢN / LÊN LỊCH (DONE / SCHEDULE)
            # -------------------------------------------------------------
            limited = await self._abort_if_daily_limit(page)
            if limited:
                return limited

            action_name = "Lên lịch" if should_schedule else "Lưu/Xuất bản"
            logger.info(f"Bấm {action_name} video lên YouTube Shorts...", "YOUTUBE")
            await page.evaluate("""() => {
                const doneBtn = document.getElementById('done-button') 
                             || document.querySelector('ytcp-button#done-button') 
                             || Array.from(document.querySelectorAll('ytcp-button, button')).find(b => {
                                 const t = (b.innerText || '').toLowerCase();
                                 return t.includes('save') || t.includes('publish') || t.includes('schedule') || t.includes('lưu') || t.includes('xuất bản') || t.includes('lên lịch');
                             });
                if (doneBtn) doneBtn.click();
            }""")
            
            # -------------------------------------------------------------
            # XÁC THỰC KẾT QUẢ THỰC TẾ (CHỐNG TRẠNG THÁI ẢO)
            # -------------------------------------------------------------
            success_confirmed = False
            for _ in range(15):
                await asyncio.sleep(2)
                
                # 1. Kiểm tra nếu xuất hiện banner / dialog báo limit
                if await self._detect_daily_upload_limit(page):
                    logger.error("YouTube từ chối: Daily upload limit reached (Daily Limit)!", "YOUTUBE")
                    return {
                        "success": False,
                        "error": "Đã đạt giới hạn tải lên YouTube trong ngày (Daily Limit). Cần đợi 24h hoặc xác minh tài khoản.",
                        "url": "",
                    }

                # 2. Kiểm tra nếu xuất hiện hộp thoại thành công hoặc video published/scheduled
                share_dialog = page.locator('ytcp-video-share-dialog, :has-text("Video published"), :has-text("Video scheduled"), :has-text("Đã xuất bản video"), :has-text("Đã lên lịch xuất bản video")').first
                if await share_dialog.is_visible(timeout=500):
                    success_confirmed = True
                    break

                # 3. Kiểm tra nếu hộp thoại upload đã đóng hoàn toàn
                upload_dialog = page.locator('ytcp-uploads-dialog').first
                if not await upload_dialog.is_visible(timeout=500):
                    success_confirmed = True
                    break

            if not success_confirmed:
                logger.error("❌ Hộp thoại YouTube Studio chưa đóng hoàn tất hoặc gặp lỗi xuất bản!", "YOUTUBE")
                return await fail_with_ai(page, "youtube", "Hộp thoại YouTube Studio chưa đóng hoàn tất (có thể do lỗi xử lý hoặc bị giới hạn).", goal=SCHEDULE_GOAL)

            final_url = await self._extract_youtube_url(page)
            if final_url:
                extracted_url = final_url

            logger.success(f"Hoàn tất {action_name} YouTube Shorts! Link: {extracted_url}", "YOUTUBE")
            return {"success": True, "url": extracted_url, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên YouTube: {str(ex)}", "YOUTUBE")
            return await fail_with_ai(page, "youtube", str(ex), goal=SCHEDULE_GOAL)

youtube_poster = YouTubePoster()
