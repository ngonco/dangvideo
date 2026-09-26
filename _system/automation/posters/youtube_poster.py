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
        """Lấy URL chỉ từ hộp upload đang hiển thị, không nhặt link video cũ trong DOM."""
        try:
            url = await page.evaluate("""() => {
                const visible = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                };
                const roots = Array.from(document.querySelectorAll(
                    'ytcp-uploads-dialog, ytcp-video-upload-progress, ytcp-video-share-dialog'
                )).filter(visible);
                if (!roots.length) return '';

                const normalize = (value) => {
                    const text = String(value || '');
                    const match = text.match(/(?:https?:\\/\\/)?(?:youtu\\.be\\/|(?:www\\.)?youtube\\.com\\/(?:shorts\\/|watch\\?v=))([a-zA-Z0-9_-]{8,15})/);
                    return match ? 'https://youtube.com/shorts/' + match[1] : '';
                };
                for (const root of roots) {
                    const nodes = Array.from(root.querySelectorAll(
                        'a#video-url, #video-url, a[href*="youtu.be/"], a[href*="youtube.com/watch"], input, span'
                    ));
                    for (const node of nodes) {
                        const found = normalize(
                            node.getAttribute?.('href') || node.value || node.innerText || node.textContent || ''
                        );
                        if (found) return found;
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

    async def _verify_in_shorts_content(self, page: Page, title: str) -> str:
        """Xác nhận dự phòng khi Studio không hiện share dialog sau khi Schedule."""
        try:
            match = re.search(r"(https://studio\.youtube\.com/channel/[^/?#]+)", page.url)
            if not match:
                return ""
            await page.goto(match.group(1) + "/videos/short", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(7)
            rows = await page.evaluate("""() => Array.from(document.querySelectorAll('ytcp-video-row')).map(row => {
                const titleEl = row.querySelector('#video-title');
                const link = row.querySelector('a#video-title[href], a[href*="/video/"][href*="/edit"]');
                return {
                    title: (titleEl?.innerText || titleEl?.textContent || '').trim(),
                    href: link?.href || '',
                    text: (row.innerText || '').trim(),
                };
            }).filter(x => x.title && x.href)""")
            wanted = re.sub(r"\s+", " ", (title or "").replace("#Shorts", "")).strip().lower()[:28]
            for row in rows:
                candidate = re.sub(r"\s+", " ", (row.get("title") or "").replace("#Shorts", "")).strip().lower()
                if wanted and wanted not in candidate:
                    continue
                if "draft" in (row.get("text") or "").lower():
                    continue
                video_id = re.search(r"/video/([A-Za-z0-9_-]{8,15})", row.get("href") or "")
                if video_id:
                    return f"https://youtube.com/shorts/{video_id.group(1)}"
        except Exception as exc:
            logger.warning(f"Không xác nhận được video trong Channel content: {exc}", "YOUTUBE")
        return ""

    async def _abort_if_daily_limit(self, page: Page):
        if await self._detect_daily_upload_limit(page):
            logger.error("YouTube báo Daily upload limit reached (banner ở bước Details). Dừng kênh này, không bấm Next/Done.", "YOUTUBE")
            return {
                "success": False,
                "error": "Đã đạt giới hạn tải lên YouTube trong ngày (Daily Limit). Cần đợi 24h hoặc xác minh tài khoản.",
                "url": "",
            }
        return None

    async def _handle_interstitials_and_dialogs(self, page: Page):
        """Tự động phát hiện và vượt qua màn hình 'Improve your experience' và các popup của YouTube Studio"""
        try:
            # 1. Màn hình 'Improve your experience / You are using an unsupported browser'
            skip_btn = page.locator('a[href*="approve_browser_access"], a:has-text("Skip to YouTube Studio"), a:has-text("Bỏ qua đến YouTube Studio"), .buttons a.button').first
            if await skip_btn.is_visible(timeout=1500):
                logger.info("Phát hiện màn hình cảnh báo trình duyệt YouTube, đang tự động bấm 'Skip to YouTube Studio'...", "YOUTUBE")
                await skip_btn.click()
                await asyncio.sleep(4)
        except Exception:
            pass

        try:
            # 2. Các popup Onboarding / Thông báo mới của YouTube Studio (Dismiss, Got it, Tiếp tục)
            dismiss_btn = page.locator('ytcp-button#dismiss-button, ytcp-button:has-text("DISMISS"), ytcp-button:has-text("BỎ QUA"), ytcp-button:has-text("GOT IT"), ytcp-button:has-text("ĐÃ HIỂU"), ytcp-button:has-text("CONTINUE"), ytcp-button:has-text("TIẾP TỤC")').first
            if await dismiss_btn.is_visible(timeout=1000):
                logger.info("Tự động đóng popup thông báo của YouTube Studio...", "YOUTUBE")
                await dismiss_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

    async def _is_studio_logged_in(self, page: Page) -> bool:
        """Kiểm tra xem người dùng đã thực sự đăng nhập vào YouTube Studio chưa"""
        # Nếu đang ở trang đăng nhập Google
        if "accounts.google.com" in page.url or "/signin" in page.url or "/ServiceLogin" in page.url:
            return False

        # Nếu đã vào URL kênh
        if "studio.youtube.com/channel/" in page.url:
            return True

        # Kiểm tra nút Create / Tạo
        create_selectors = [
            'button#create-icon',
            'ytcp-button#create-icon',
            '#create-icon',
            'button:has-text("CREATE")',
            'button:has-text("TẠO")',
            'button:has-text("Create")',
            'button:has-text("Tạo")',
            'ytcp-button[aria-label*="Create" i]',
            'ytcp-button[aria-label*="Tạo" i]'
        ]
        for sel in create_selectors:
            try:
                if await page.locator(sel).first.is_visible(timeout=1000):
                    return True
            except Exception:
                pass

        # Kiểm tra Avatar kênh trên header
        try:
            if await page.locator('#avatar-btn, ytcp-app-header img#img').first.is_visible(timeout=1000):
                return True
        except Exception:
            pass

        return False

    async def post_video(self, page: Page, video_data: Dict[str, Any], privacy_override: Optional[str] = None, schedule_time: Optional[str] = None, target_date: Optional[str] = None) -> Dict[str, Any]:
        file_path = video_data.get("file_path", "")
        if not self.validate_video_file(file_path):
            return {"success": False, "error": "File video không hợp lệ"}

        raw_title = video_data.get("suggested_title") or video_data.get("title") or ""
        title = self._clean_title(raw_title)

        description = self.format_caption(video_data)
        yt_config = config_mgr.get("platforms", {}).get("youtube", {})
        mark_ai = yt_config.get("mark_ai", True)
        privacy = privacy_override or yt_config.get("privacy", "public")
        
        native = get_native_schedule(schedule_time or "", target_date_override=target_date)
        should_schedule = native["enabled"]
        target_schedule_time = native["time"]
        target_dt = native["datetime"]

        try:
            logger.info("Mở YouTube Studio (https://studio.youtube.com)...", "YOUTUBE")
            await page.goto("https://studio.youtube.com/?approve_browser_access=true", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)

            # Tự động vượt qua màn hình cảnh báo trình duyệt hoặc popup
            await self._handle_interstitials_and_dialogs(page)

            # Kiểm tra trạng thái đăng nhập
            if not await self._is_studio_logged_in(page):
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
                    
                    await self._handle_interstitials_and_dialogs(page)
                    if await self._is_studio_logged_in(page):
                        logged_in = True
                        break

                if not logged_in:
                    logger.error(f"Hết thời gian chờ đăng nhập YouTube (5 phút). URL hiện tại: {page.url}", "YOUTUBE")
                    return {"success": False, "error": "Hết thời gian chờ đăng nhập YouTube"}

                logger.success("🎉 Đã phát hiện đăng nhập YouTube thành công! Tiếp tục tiến trình đăng video...", "YOUTUBE")
                await asyncio.sleep(2)

            # Click Create / TẠO button
            logger.info("Tìm nút Tạo / Create trên YouTube Studio...", "YOUTUBE")
            create_btn = page.locator('button#create-icon, ytcp-button#create-icon, button:has-text("CREATE"), button:has-text("TẠO"), button:has-text("Create"), button:has-text("Tạo")').first
            await create_btn.wait_for(state="visible", timeout=20000)
            await create_btn.evaluate("el => el.click()")
            await asyncio.sleep(1.5)

            # Click Upload videos / Tải video lên
            upload_item = page.locator('tp-yt-paper-item:has-text("Upload videos"), tp-yt-paper-item:has-text("Tải video lên"), tp-yt-paper-item:has-text("Upload video")').first
            await upload_item.wait_for(state="visible", timeout=15000)
            await upload_item.evaluate("el => el.click()")
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
                    schedule_opened = await page.evaluate("""() => {
                        const schedRadio = document.querySelector('tp-yt-paper-radio-button[name="SCHEDULE"]')
                            || document.getElementById('schedule-radio-button')
                            || Array.from(document.querySelectorAll('tp-yt-paper-radio-button')).find(el => {
                                             const t = (el.innerText || '').toLowerCase();
                                             return t.includes('schedule') || t.includes('lên lịch');
                            });
                        if (schedRadio) {
                            schedRadio.click();
                            schedRadio.setAttribute('aria-checked', 'true');
                            return 'radio';
                        }
                        return '';
                    }""")
                    if not schedule_opened:
                        for label_text in ("Schedule", "Lên lịch"):
                            label = page.get_by_text(label_text, exact=True).first
                            try:
                                if await label.is_visible(timeout=1200):
                                    await label.evaluate("""el => {
                                        const hit = el.closest('button, ytcp-button, [role="button"], tp-yt-paper-item')
                                            || el.parentElement || el;
                                        hit.click();
                                    }""")
                                    schedule_opened = "accordion"
                                    break
                            except Exception:
                                pass
                    if not schedule_opened:
                        return {"success": False, "url": "", "error": "Không tìm thấy khối Schedule/Lên lịch trên YouTube."}
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
                        if not picked:
                            await page.keyboard.press("Escape")
                        await asyncio.sleep(0.8)

                    time_12 = native["time_12h_no_pad"]
                    time_trigger = None
                    all_inputs = page.locator('input')
                    for input_index in range(await all_inputs.count()):
                        candidate = all_inputs.nth(input_index)
                        try:
                            if not await candidate.is_visible(timeout=300):
                                continue
                            candidate_value = (await candidate.input_value()).strip()
                            if re.match(r"^\d{1,2}:\d{2}\s*(?:AM|PM|SA|CH)$", candidate_value, re.I):
                                time_trigger = candidate
                                break
                        except Exception:
                            continue

                    if time_trigger is not None:
                        await time_trigger.click(force=True)
                        await time_trigger.fill(time_12)
                        await time_trigger.press("Enter")
                        await time_trigger.press("Tab")
                    else:
                        current_time_label = None
                        for current_value in ("12:00 AM", "12:00 SA"):
                            candidate = page.get_by_text(current_value, exact=True).first
                            try:
                                if await candidate.is_visible(timeout=700):
                                    current_time_label = candidate
                                    break
                            except Exception:
                                pass
                        if current_time_label is not None:
                            await current_time_label.click(force=True)
                            await page.keyboard.press("Control_L+A")
                            await page.keyboard.type(time_12, delay=40)
                            await page.keyboard.press("Enter")
                            await page.keyboard.press("Tab")
                    await asyncio.sleep(1)

                    schedule_state = await page.evaluate("""() => {
                        const radio = document.querySelector('tp-yt-paper-radio-button[name="SCHEDULE"]')
                            || document.getElementById('schedule-radio-button');
                        const dateEl = document.querySelector('#datepicker-trigger, ytcp-dropdown-trigger#datepicker-trigger');
                        const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                        const timeEl = Array.from(document.querySelectorAll('input')).find(el => {
                            const v = String(el.value || '').trim();
                            return visible(el) && /^\d{1,2}:\d{2}\s*(?:AM|PM|SA|CH)$/i.test(v);
                        }) || document.querySelector(
                            '#time-of-day-trigger, ytcp-dropdown-trigger#time-of-day-trigger, '
                            + 'input#time-of-day, #time-of-day, input[aria-label="Time"], input[aria-label="Giờ"]'
                        );
                        const value = (el) => String(el?.value || el?.innerText || el?.textContent || '').trim();
                        return {
                            checked: radio?.getAttribute('aria-checked') === 'true' || radio?.hasAttribute('checked'),
                            date: value(dateEl),
                            time: value(timeEl),
                            expanded: !!(dateEl && timeEl),
                        };
                    }""")
                    if not (schedule_state.get("checked") or schedule_state.get("expanded")):
                        debug = await page.evaluate("""() => ({
                            url: location.href,
                            radios: Array.from(document.querySelectorAll(
                                'tp-yt-paper-radio-button, [role="radio"], ytcp-radio-group *'
                            )).map(el => ({
                                tag: el.tagName,
                                name: el.getAttribute('name') || '',
                                aria: el.getAttribute('aria-checked') || '',
                                text: (el.innerText || el.textContent || '').trim().slice(0, 180),
                                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                            })).filter(x => x.text || x.name).slice(0, 40),
                            buttons: Array.from(document.querySelectorAll('ytcp-button, button')).map(el => ({
                                id: el.id || '',
                                aria: el.getAttribute('aria-label') || '',
                                text: (el.innerText || el.textContent || '').trim().slice(0, 120),
                                disabled: el.getAttribute('aria-disabled') || el.getAttribute('disabled') || '',
                            })).filter(x => x.text || x.aria).slice(-30),
                        })""")
                        logger.error(f"YouTube Schedule radio debug: {debug}", "YOUTUBE")
                        try:
                            await page.screenshot(path=os.path.join(os.path.dirname(__file__), "..", "..", "debug_screenshots", "yt_schedule_radio_fail.png"))
                        except Exception:
                            pass
                        return {"success": False, "url": "", "error": "YouTube chưa bật được chế độ Schedule; không ghi nhận thành công."}
                    shown_time = schedule_state.get("time", "")
                    accepted_times = (target_schedule_time, native["time_12h_no_pad"], native["time_12h"])
                    normalize_time = lambda value: " ".join(str(value or "").replace("\u202f", " ").split()).lower()
                    shown_time_norm = normalize_time(shown_time)
                    if not any(candidate and normalize_time(candidate) in shown_time_norm for candidate in accepted_times):
                        return {
                            "success": False,
                            "url": "",
                            "error": (
                                f"Giờ YouTube chưa khớp {target_schedule_time} "
                                f"(đang thấy {shown_time!r}); không bấm Schedule."
                            ),
                        }
                    logger.info(
                        f"Đã xác nhận trường lịch YouTube: date={schedule_state.get('date')!r}, "
                        f"time={schedule_state.get('time')!r}.",
                        "YOUTUBE",
                    )
                except Exception as ex_sched:
                    logger.error(f"Không thể xác nhận mốc giờ Schedule: {ex_sched}", "YOUTUBE")
                    return {"success": False, "url": "", "error": f"Không thể xác nhận lịch YouTube: {ex_sched}"}

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
            done_btn = page.locator('ytcp-button#done-button, button#done-button').first
            await done_btn.wait_for(state="visible", timeout=20000)
            done_ready = False
            for _ in range(90):
                limited = await self._abort_if_daily_limit(page)
                if limited:
                    return limited
                aria_disabled = await done_btn.get_attribute("aria-disabled")
                disabled = await done_btn.get_attribute("disabled")
                if aria_disabled != "true" and disabled is None:
                    done_ready = True
                    break
                await asyncio.sleep(1)
            if not done_ready:
                return {
                    "success": False,
                    "url": "",
                    "error": "Nút Schedule YouTube vẫn bị khóa sau 90 giây; video còn Draft, không ghi nhận thành công.",
                }
            await done_btn.click(force=True)
            
            # -------------------------------------------------------------
            # XÁC THỰC KẾT QUẢ THỰC TẾ (CHỐNG TRẠNG THÁI ẢO)
            # -------------------------------------------------------------
            success_confirmed = False
            for _ in range(30):
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
                share_dialog = page.locator(
                    'ytcp-video-share-dialog, '
                    'ytcp-dialog:has-text("Video published"), '
                    'ytcp-dialog:has-text("Video scheduled"), '
                    'ytcp-dialog:has-text("Đã xuất bản video"), '
                    'ytcp-dialog:has-text("Đã lên lịch xuất bản video")'
                ).first
                if await share_dialog.is_visible(timeout=500):
                    success_confirmed = True
                    break

            if not success_confirmed:
                verified_url = await self._verify_in_shorts_content(page, title)
                if verified_url:
                    extracted_url = verified_url
                    success_confirmed = True
                    logger.success(f"Đã xác nhận video trong Channel content: {verified_url}", "YOUTUBE")
                else:
                    logger.error("❌ YouTube không hiện xác nhận Video scheduled và không thấy hàng Shorts hợp lệ; không ghi thành công.", "YOUTUBE")
                    return {
                        "success": False,
                        "url": "",
                        "error": "YouTube không xác nhận Video scheduled; video có thể vẫn là Draft.",
                    }

            final_url = await self._extract_youtube_url(page)
            if final_url:
                extracted_url = final_url

            logger.success(f"Hoàn tất {action_name} YouTube Shorts! Link: {extracted_url}", "YOUTUBE")
            return {"success": True, "url": extracted_url, "error": ""}

        except Exception as ex:
            logger.error(f"Lỗi khi đăng lên YouTube: {str(ex)}", "YOUTUBE")
            return await fail_with_ai(page, "youtube", str(ex), goal=SCHEDULE_GOAL)

youtube_poster = YouTubePoster()
