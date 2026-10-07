import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from core.posting_store import VIETNAM
from core.logger import logger
from core.config_manager import config_mgr
from core.database import db
from automation.workflow_manager import workflow_mgr

DAILY_POST_CHECK_INTERVAL_MINUTES = 30


class TaskScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=VIETNAM)
        self._cycle_lock = asyncio.Lock()
        self.is_running = False

    def start(self):
        if not self.is_running:
            db.recover_interrupted_uploads()
            self.reload_jobs()
            self.scheduler.start()
            self.is_running = True
            logger.info(
                "Đã khởi động tự động đăng: kiểm tra ngay khi mở ứng dụng, "
                f"sau đó mỗi {DAILY_POST_CHECK_INTERVAL_MINUTES} phút để hoàn tất đủ các kênh của lượt hôm nay.",
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
            next_run_time=datetime.now(VIETNAM),
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

        self.scheduler.add_job(self._scheduled_reserve_fill,
            trigger=IntervalTrigger(minutes=60, timezone=VIETNAM), next_run_time=datetime.now(VIETNAM),
            id='reserve_fill_job', replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=None)
        self.scheduler.add_job(self._scheduled_link_repair,
            trigger=IntervalTrigger(minutes=30, timezone=VIETNAM),
            id='link_repair_job', replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=None)

        # Daily auto-cleanup job at 00:05 midnight
        self.scheduler.add_job(
            self._scheduled_cleanup,
            trigger=CronTrigger(hour=0, minute=5, timezone=VIETNAM),
            id="daily_cleanup_job",
            replace_existing=True
        )
        logger.info("Đã lập lịch tự động dọn dẹp video đã đăng cũ (> 2 ngày) hàng ngày lúc 00:05.", "SCHEDULER")

        # Daily summary email report job at 22:00
        self.scheduler.add_job(
            self._scheduled_daily_email_report,
            trigger=CronTrigger(hour=22, minute=0, timezone=VIETNAM),
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

    async def _notify_reserve(self):
        count = db.reserve_count()
        state = 'empty' if count == 0 else 'low' if count < 3 else 'ready'
        detail = {'empty': 'Kho dự phòng rỗng; cần video mới để tiếp tục đăng.',
                  'low': 'Kho dự phòng còn dưới 3 video.',
                  'ready': 'Kho dự phòng đã đủ mức an toàn.'}[state]
        if db.set_health('reserve', state, detail):
            logger.info(detail, 'SCHEDULER')
            from core.email_reporter import email_reporter
            email_reporter.send_error_alert('reserve', detail, step='Theo dõi kho dự phòng')

    async def _fill_reserve(self):
        need = max(0, 7 - db.reserve_count())
        if need and not workflow_mgr.is_busy:
            await workflow_mgr.scan_and_download(max_items=need, force_latest=False,
                oldest_first=True, exclude_today=False)
        await self._notify_reserve()

    async def _scheduled_reserve_fill(self):
        if not config_mgr.get('schedule', {}).get('auto_mode', False):
            return
        async with self._cycle_lock:
            await self._fill_reserve()

    async def _scheduled_daily_post_check(self):
        if not config_mgr.get('schedule', {}).get('auto_mode', False) or workflow_mgr.is_busy or self._cycle_lock.locked():
            return
        async with self._cycle_lock:
            try:
                await self._auto_process_next_video()
            except Exception as exc:
                logger.error(f'Lỗi chu kỳ tự động; sẽ tiếp tục ở lần sau: {exc}', 'SCHEDULER')
                db.set_health('scheduler', 'error', str(exc)[:250])

    async def _auto_process_next_video(self):
        if workflow_mgr.is_busy:
            return
        from core.posting_store import local_now
        run = db.get_daily_run()
        enabled = [p for p, cfg in config_mgr.get('platforms', {}).items() if cfg.get('enabled', False)]
        if not run and enabled:
            if db.reserve_count() == 0:
                await self._fill_reserve()
            video_id = db.assign_daily_video(enabled)
            run = db.get_daily_run()
            if video_id:
                logger.info(f'Lượt mới {local_now().date()}: video #{video_id}', 'SCHEDULER')
        due = db.pending_delivery_videos()
        if run:
            successes = set(db.get_successful_platforms_for_video(run['video_id']))
            current_video = db.get_video_by_id(run['video_id'])
            if current_video and current_video['status'] != 'cleaned' and not set(run['platforms']).issubset(successes):
                due = [run['video_id']] + [v for v in due if v != run['video_id']]
        for video_id in due:
            if workflow_mgr.is_busy:
                break
            # An old run repairs its own channels without consuming today's assignment.
            targets = enabled
            if targets:
                await workflow_mgr.publish_video_to_platforms(video_id, target_platforms=targets,
                    enforce_ig_gap=True, respect_retry=True)
        health = db.get_posting_health()
        db.set_health('scheduler', 'complete' if health['complete'] else 'pending',
            'Đã hoàn tất các kênh của lượt hôm nay.' if health['complete'] else 'Tiếp tục kiểm tra các kênh còn thiếu mỗi 30 phút.')
        await self._notify_reserve()

    async def _scheduled_link_repair(self):
        if not config_mgr.get('schedule', {}).get('auto_mode', False):
            return
        async with self._cycle_lock:
            await workflow_mgr.repair_requested_captions()
            await workflow_mgr.repair_pending_links()


task_scheduler = TaskScheduler()
