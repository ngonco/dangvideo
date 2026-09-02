import asyncio
from typing import List, Dict, Any, Optional
from core.logger import logger
from core.database import db
from core.config_manager import config_mgr
from automation.browser_engine import browser_engine
from automation.hatbuinho_crawler import hatbuinho_crawler
from automation.posters.youtube_poster import youtube_poster
from automation.posters.tiktok_poster import tiktok_poster
from automation.posters.facebook_poster import facebook_poster
from automation.posters.instagram_poster import instagram_poster

class WorkflowManager:
    def __init__(self):
        self._is_busy = False
        self._lock = asyncio.Lock()

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    async def scan_and_download(
        self,
        max_items: Optional[int] = None,
        force_latest: bool = False,
        oldest_first: bool = True,
        exclude_today: bool = False,
        fallback_latest: bool = False,
    ) -> List[Dict[str, Any]]:
        if self._is_busy:
            logger.warning("Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi...", "WORKFLOW")
            return []

        async with self._lock:
            self._is_busy = True
            try:
                safety_str = " (Lọc an toàn: Bỏ qua video tạo hôm nay)" if exclude_today else ""
                mode_name = "TEST ÉP TẢI VIDEO MỚI NHẤT" if force_latest else f"QUÉT TẢI VIDEO 'CHƯA TẢI XUỐNG' ({'Cũ nhất' if oldest_first else 'Mới nhất'}){safety_str}"
                if fallback_latest and not force_latest:
                    mode_name += " (hết Chưa tải thì lấy video mới nhất)"
                logger.info(f"Bắt đầu tác vụ: {mode_name} từ hatbuinho.com...", "WORKFLOW")
                results = await hatbuinho_crawler.scan_and_download(
                    max_items=max_items,
                    force_latest=force_latest,
                    oldest_first=oldest_first,
                    exclude_today=exclude_today,
                    fallback_latest=fallback_latest,
                )
                return results
            finally:
                self._is_busy = False

    async def batch_download_to_queue(self, max_items: int = 50) -> Dict[str, Any]:
        """Tải hàng loạt toàn bộ video 'Chưa tải xuống' vào kho hàng đợi để đăng đa ngày"""
        if self._is_busy:
            logger.warning("Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi...", "WORKFLOW")
            return {"success": False, "error": "Hệ thống đang bận thực hiện tác vụ khác"}

        async with self._lock:
            self._is_busy = True
            try:
                logger.info(f"🚀 Bắt đầu quét & tải hàng loạt toàn bộ video 'Chưa tải xuống' vào Kho Hàng Đợi...", "WORKFLOW")
                results = await hatbuinho_crawler.scan_and_download(max_items=max_items, force_latest=False, oldest_first=True)
                
                slots = config_mgr.get("schedule", {}).get("post_time_slots", ["08:00", "11:30", "19:30"])
                queue_summary = db.get_queue_summary(slots_per_day=len(slots))
                
                return {
                    "success": True,
                    "downloaded_count": len(results),
                    "total_pending": queue_summary["total_pending"],
                    "estimated_days": queue_summary["estimated_days"],
                    "message": f"Đã tải về thành công {len(results)} video vào Kho Hàng Đợi! (Hiện có {queue_summary['total_pending']} video, dự kiến đăng trong {queue_summary['estimated_days']} ngày)."
                }
            except Exception as ex:
                logger.error(f"Lỗi khi tải hàng loạt vào hàng đợi: {ex}", "WORKFLOW")
                return {"success": False, "error": str(ex)}
            finally:
                self._is_busy = False

    async def publish_video_to_platforms(
        self,
        video_id: int,
        target_platforms: Optional[List[str]] = None,
        schedule_time: Optional[str] = None,
        enforce_ig_gap: bool = True,
    ) -> Dict[str, Any]:
        if self._is_busy:
            logger.warning("Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi...", "WORKFLOW")
            return {"success": False, "error": "Hệ thống đang bận"}

        async with self._lock:
            self._is_busy = True
            try:
                video = db.get_video_by_id(video_id)
                if not video:
                    logger.error(f"Không tìm thấy video ID #{video_id} trong cơ sở dữ liệu.", "WORKFLOW")
                    return {"success": False, "error": "Video không tồn tại"}

                logger.info(f"Bắt đầu đăng tải video ID #{video_id}: '{video.get('suggested_title') or video.get('title')}'...", "WORKFLOW")
                
                platforms_cfg = config_mgr.get("platforms", {})
                if target_platforms is None:
                    target_platforms = [p for p, cfg in platforms_cfg.items() if cfg.get("enabled", False)]

                from core.schedule_helper import get_native_schedule, get_instagram_min_gap_hours
                from datetime import datetime
                native = get_native_schedule(schedule_time or "")
                sched_time = native["time"]
                logger.info(
                    f"Hẹn native công khai: {native['label']} (tải lên ngay, hiện lúc {sched_time} sáng mai). Instagram: chia sẻ ngay.",
                    "WORKFLOW",
                )

                results = {}
                for plat in target_platforms:
                    logger.info(f"--- Đang chuẩn bị đăng lên {plat.upper()} ---", "WORKFLOW")

                    if plat == "instagram" and enforce_ig_gap:
                        gap_hours = get_instagram_min_gap_hours()
                        last_ig = db.get_last_success_at("instagram")
                        if last_ig:
                            elapsed = (datetime.now() - last_ig).total_seconds() / 3600.0
                            if elapsed < gap_hours:
                                remain = round(gap_hours - elapsed, 1)
                                msg = (
                                    f"Instagram chưa đủ {gap_hours:g} tiếng kể lần đăng trước "
                                    f"({last_ig.strftime('%d/%m %H:%M')}). Bỏ qua kênh này, còn {remain} tiếng."
                                )
                                logger.info(msg, "INSTAGRAM")
                                db.record_post(
                                    video_id=video_id,
                                    platform="instagram",
                                    status="skipped",
                                    post_url="",
                                    error_message=msg,
                                )
                                results[plat] = {"success": True, "skipped": True, "url": "", "error": msg}
                                await asyncio.sleep(1)
                                continue
                    res = {"success": False, "error": "Nền tảng chưa hỗ trợ", "url": ""}
                    page = None

                    try:
                        ctx = await browser_engine.get_context()
                        page = await browser_engine.get_page(ctx)

                        if plat == "youtube":
                            res = await youtube_poster.post_video(page, video, schedule_time=sched_time)
                        elif plat == "tiktok":
                            res = await tiktok_poster.post_video(page, video, schedule_time=sched_time)
                        elif plat == "facebook":
                            res = await facebook_poster.post_video(page, video, schedule_time=sched_time)
                        elif plat == "instagram":
                            res = await instagram_poster.post_video(page, video, schedule_time=sched_time)

                    except Exception as ex:
                        import traceback
                        tb = traceback.format_exc()
                        logger.error(f"Lỗi ngoại lệ khi đăng lên {plat.upper()}: {str(ex)}", "WORKFLOW")
                        try:
                            from automation.ai_fallback import fail_with_ai, SCHEDULE_GOAL
                            if page is not None:
                                res = await fail_with_ai(page, plat, str(ex), goal=SCHEDULE_GOAL)
                                if res.get("error_details"):
                                    res["error_details"] = (res.get("error_details") or "") + "\n" + tb
                            else:
                                res = {"success": False, "error": str(ex), "url": ""}
                        except Exception:
                            res = {"success": False, "error": str(ex), "url": ""}

                    status = "success" if res.get("success") else "failed"
                    if status == "failed" and res.get("error"):
                        try:
                            from core.email_reporter import email_reporter
                            v_title = video.get('suggested_title') or video.get('title') or f"Video #{video_id}"
                            email_reporter.send_error_alert(
                                platform=plat,
                                error_message=res.get("error"),
                                step=f"Đăng bài '{v_title}' lên {plat.upper()} — AI không xử lý được, bỏ kênh này, tiếp tục kênh khác",
                                details=res.get("error_details") or res.get("ai_diagnosis") or "",
                            )
                        except Exception:
                            pass

                    db.record_post(
                        video_id=video_id,
                        platform=plat,
                        status=status,
                        post_url=res.get("url", ""),
                        error_message=res.get("error", "")
                    )
                    results[plat] = res

                    # Delay between platforms
                    await asyncio.sleep(4)

                return {"success": True, "details": results}

            finally:
                self._is_busy = False

    async def open_login_browser(self, target_url: str = "https://hatbuinho.com/"):
        logger.info(f"Mở trình duyệt cho người dùng đăng nhập tài khoản: {target_url}", "AUTH")
        ctx = await browser_engine.get_context(headless=False)
        page = await browser_engine.get_page(ctx)
        await page.goto(target_url)

workflow_mgr = WorkflowManager()
