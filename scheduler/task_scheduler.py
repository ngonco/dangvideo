import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from core.logger import logger
from core.config_manager import config_mgr
from core.database import db
from automation.workflow_manager import workflow_mgr

class TaskScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    def start(self):
        if not self.is_running:
            self.reload_jobs()
            self.scheduler.start()
            self.is_running = True
            logger.info("Đã khởi động Trình Lên Lịch Tự Động (Background Scheduler).", "SCHEDULER")
            # Run cleanup check on startup
            asyncio.create_task(self._scheduled_cleanup())

    def stop(self):
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("Đã tạm dừng Trình Lên Lịch Tự Động.", "SCHEDULER")

    def reload_jobs(self):
        self.scheduler.remove_all_jobs()
        sched_cfg = config_mgr.get("schedule", {})
        scan_interval = sched_cfg.get("scan_interval_minutes", 60)
        time_slots = sched_cfg.get("post_time_slots", ["08:00", "11:30", "19:30"])

        # Periodic scan job
        self.scheduler.add_job(
            self._scheduled_scan_and_post_check,
            trigger=IntervalTrigger(minutes=scan_interval),
            id="periodic_scan_job",
            replace_existing=True
        )

        # Golden hours cron jobs
        for slot in time_slots:
            try:
                hour, minute = slot.strip().split(":")
                self.scheduler.add_job(
                    self._scheduled_slot_trigger,
                    trigger=CronTrigger(hour=int(hour), minute=int(minute)),
                    id=f"slot_job_{hour}_{minute}",
                    replace_existing=True
                )
                logger.info(f"Đã lập lịch đăng tự động vào khung giờ: {slot}", "SCHEDULER")
            except Exception as e:
                logger.warning(f"Lỗi khi cài đặt lịch khung giờ '{slot}': {e}", "SCHEDULER")

        # Daily auto-cleanup job at 00:05 midnight
        self.scheduler.add_job(
            self._scheduled_cleanup,
            trigger=CronTrigger(hour=0, minute=5),
            id="daily_cleanup_job",
            replace_existing=True
        )
        logger.info("Đã lập lịch tự động dọn dẹp video đã đăng cũ (> 2 ngày) hàng ngày lúc 00:05.", "SCHEDULER")

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

    async def _scheduled_slot_trigger(self):
        """Kích hoạt đăng bài tự động khi chạm đúng khung giờ vàng"""
        sched_cfg = config_mgr.get("schedule", {})
        if not sched_cfg.get("auto_mode", False):
            return

        logger.info("⏰ Khung giờ vàng đã đến! Kiểm tra video để đăng tự động...", "SCHEDULER")
        await self._auto_process_next_video()

    async def _scheduled_scan_and_post_check(self):
        """Quét định kỳ từ HatBuiNho"""
        sched_cfg = config_mgr.get("schedule", {})
        if not sched_cfg.get("auto_mode", False):
            return

        logger.info("Bắt đầu quét định kỳ video mới từ hatbuinho.com...", "SCHEDULER")
        await workflow_mgr.scan_and_download(max_items=2)

    async def _auto_process_next_video(self):
        sched_cfg = config_mgr.get("schedule", {})
        max_today = sched_cfg.get("max_posts_per_day", 3)
        stats = db.get_stats()

        if stats["posts_today"] >= max_today:
            logger.info(f"Đã đạt giới hạn đăng trong ngày ({stats['posts_today']}/{max_today} video). Tạm hoãn đăng tiếp.", "SCHEDULER")
            return

        # Find first downloaded video that has not been fully posted
        videos = db.list_videos(limit=20)
        pending_video = None
        for v in videos:
            if v.get("status") == "downloaded":
                pending_video = v
                break

        if pending_video:
            logger.info(f"Tự động chọn video ID #{pending_video['id']} để đăng tải...", "SCHEDULER")
            await workflow_mgr.publish_video_to_platforms(pending_video["id"])
        else:
            logger.info("Chưa có video nào đang chờ đăng trong hàng đợi. Tiến hành quét hatbuinho...", "SCHEDULER")
            new_vids = await workflow_mgr.scan_and_download(max_items=1)
            if new_vids:
                first_vid = db.get_video_by_hatbuinho_id(new_vids[0]["hatbuinho_id"])
                if first_vid:
                    await workflow_mgr.publish_video_to_platforms(first_vid["id"])

task_scheduler = TaskScheduler()
