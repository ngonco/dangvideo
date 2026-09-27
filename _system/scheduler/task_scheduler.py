import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from core.logger import logger
from core.config_manager import config_mgr
from core.database import db
from automation.workflow_manager import workflow_mgr

DAILY_POST_CHECK_INTERVAL_MINUTES = 30


class TaskScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    def start(self):
        if not self.is_running:
            self.reload_jobs()
            self.scheduler.start()
            self.is_running = True
            logger.info(
                "Đã khởi động tự động đăng: kiểm tra ngay khi mở ứng dụng, "
                f"sau đó mỗi {DAILY_POST_CHECK_INTERVAL_MINUTES} phút cho tới khi hôm nay đã đăng video.",
                "SCHEDULER",
            )
            # Run cleanup check on startup
            asyncio.create_task(self._scheduled_cleanup())

    def stop(self):
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("Đã tạm dừng Trình Lên Lịch Tự Động.", "SCHEDULER")

    def reload_jobs(self):
        self.scheduler.remove_all_jobs()

        # Kiểm tra ngay khi app mở/reload cấu hình, rồi lặp lại mỗi 30 phút.
        # post_time_slots chỉ còn dùng để chọn giờ công khai native gần nhất.
        self.scheduler.add_job(
            self._scheduled_daily_post_check,
            trigger=IntervalTrigger(minutes=DAILY_POST_CHECK_INTERVAL_MINUTES),
            next_run_time=datetime.now(),
            id="daily_post_opportunity_job",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=None,
        )
        logger.info(
            f"Đã lập lịch kiểm tra cơ hội đăng ngay bây giờ và mỗi {DAILY_POST_CHECK_INTERVAL_MINUTES} phút.",
            "SCHEDULER",
        )

        # Daily auto-cleanup job at 00:05 midnight
        self.scheduler.add_job(
            self._scheduled_cleanup,
            trigger=CronTrigger(hour=0, minute=5),
            id="daily_cleanup_job",
            replace_existing=True
        )
        logger.info("Đã lập lịch tự động dọn dẹp video đã đăng cũ (> 2 ngày) hàng ngày lúc 00:05.", "SCHEDULER")

        # Daily summary email report job at 22:00
        self.scheduler.add_job(
            self._scheduled_daily_email_report,
            trigger=CronTrigger(hour=22, minute=0),
            id="daily_email_report_job",
            replace_existing=True
        )
        logger.info("Đã lập lịch tự động gửi báo cáo tổng kết hàng ngày qua Email lúc 22:00.", "SCHEDULER")

    async def _scheduled_daily_email_report(self):
        """Tự động tổng hợp và gửi email báo cáo tổng kết video đã đăng trong ngày"""
        try:
            from core.email_reporter import email_reporter
            logger.info("Bắt đầu tổng hợp và gửi báo cáo ngày qua Email...", "EMAIL")
            email_reporter.send_daily_summary()
        except Exception as ex:
            logger.warning(f"Lỗi gửi báo cáo ngày qua email: {ex}", "EMAIL")

    async def _scheduled_cleanup(self):
        """Tự động dọn dẹp các tệp video đã đăng cũ hơn N ngày (mặc định 2 ngày)"""
        cleanup_cfg = config_mgr.get("cleanup", {})
        if not cleanup_cfg.get("auto_cleanup", True):
            return

        retention_days = cleanup_cfg.get("retention_days", 2)
        logger.info(f"Bắt đầu kiểm tra dọn dẹp video đã đăng cũ hơn {retention_days} ngày...", "CLEANUP")
        res = db.clean_old_posted_videos(retention_days=retention_days)
        if res["deleted_count"] > 0:
            logger.success(f"Dọn dẹp hoàn tất: Đã xóa {res['deleted_count']} tệp video cũ, giải phóng {res['freed_mb']} MB ổ cứng.", "CLEANUP")
        else:
            logger.info("Không có tệp video cũ nào cần dọn dẹp.", "CLEANUP")

    async def _scheduled_daily_post_check(self):
        """Đăng ngay khi có cơ hội nếu hôm nay chưa có video thành công."""
        sched_cfg = config_mgr.get("schedule", {})
        if not sched_cfg.get("auto_mode", False):
            return

        if db.has_successful_video_today():
            logger.info("Hôm nay đã đăng video thành công. Bỏ qua lần kiểm tra này.", "SCHEDULER")
            return

        if workflow_mgr.is_busy:
            logger.info(
                f"Hôm nay chưa đăng video nhưng hệ thống đang bận. Sẽ thử lại sau {DAILY_POST_CHECK_INTERVAL_MINUTES} phút.",
                "SCHEDULER",
            )
            return

        logger.info("Hôm nay chưa đăng video. Bắt đầu đăng tự động ngay khi có cơ hội...", "SCHEDULER")
        await self._auto_process_next_video()

    async def _auto_process_next_video(self):
        # Kiểm tra lại ngay trước khi lấy video để tránh chạy trùng với thao tác thủ công.
        if db.has_successful_video_today():
            logger.info("Hôm nay vừa có video đăng thành công. Không tạo thêm lượt đăng tự động.", "SCHEDULER")
            return

        # Mỗi lần kích hoạt chỉ 1 video — không bù hàng loạt khi máy vừa mở lại
        sched_cfg = config_mgr.get("schedule", {})
        min_delay = int(sched_cfg.get("min_delay_between_posts_minutes", 180) or 180)
        last_ig = db.get_last_success_at("instagram")
        if last_ig:
            from datetime import datetime
            elapsed_min = (datetime.now() - last_ig).total_seconds() / 60.0
            if elapsed_min < min_delay:
                logger.info(
                    f"Instagram vừa đăng cách đây {elapsed_min:.0f} phút (< {min_delay} phút). "
                    "Vẫn đăng 1 video cho YT/TikTok/Facebook; Instagram sẽ được bỏ qua trong workflow.",
                    "SCHEDULER",
                )

        # 1. Tìm video chưa đăng cũ nhất trong kho hàng đợi (FIFO)
        pending_video = db.get_oldest_pending_video()

        # 2. Nếu kho trống, lấy video "Chưa tải xuống" cũ nhất trong tab Đã xong.
        # HatBuiNho đã đánh dấu Đã xong thì video tạo hôm nay cũng đủ điều kiện đăng.
        if not pending_video:
            logger.info(
                "Kho hàng đợi đang rỗng, tiến hành quét tải 1 video 'Chưa tải xuống' "
                "cũ nhất trong tab Đã xong của HatBuiNho...",
                "SCHEDULER",
            )
            new_vids = await workflow_mgr.scan_and_download(
                max_items=1,
                force_latest=False,
                oldest_first=True,
                exclude_today=False,
            )
            if new_vids:
                pending_video = db.get_oldest_pending_video()

        if pending_video:
            v_title = pending_video.get("suggested_title") or pending_video.get("title")
            logger.info(f"Tự động đăng video #{pending_video['id']}: '{v_title}'...", "SCHEDULER")
            await workflow_mgr.publish_video_to_platforms(pending_video["id"], enforce_ig_gap=True)
            if db.has_successful_video_today():
                logger.success("Đã hoàn thành lượt đăng video tự động của hôm nay.", "SCHEDULER")
            else:
                logger.warning(
                    f"Lượt đăng chưa có kênh nào thành công. Sẽ thử lại sau {DAILY_POST_CHECK_INTERVAL_MINUTES} phút.",
                    "SCHEDULER",
                )
        else:
            logger.info("Hiện không có video 'Chưa tải xuống' hợp lệ cần đăng trên HatBuiNho.", "SCHEDULER")

task_scheduler = TaskScheduler()
