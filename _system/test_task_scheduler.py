import os
import gc
import tempfile
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.database import Database
from scheduler.task_scheduler import DAILY_POST_CHECK_INTERVAL_MINUTES, TaskScheduler


class DailyPostDatabaseTests(unittest.TestCase):
    def test_successful_video_today_only_accepts_success_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_db = Database(os.path.join(temp_dir, "scheduler.db"))
            video_id = test_db.add_or_update_video(
                {
                    "hatbuinho_id": "daily-check-video",
                    "title": "Video test",
                    "file_path": "video.mp4",
                }
            )

            self.assertFalse(test_db.has_successful_video_today())
            test_db.record_post(video_id, "youtube", "failed", error_message="test")
            self.assertFalse(test_db.has_successful_video_today())
            test_db.record_post(video_id, "tiktok", "success", post_url="https://example.test/video")
            self.assertTrue(test_db.has_successful_video_today())
            del test_db
            gc.collect()


class DailyPostSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_runs_immediately_and_repeats_every_30_minutes(self):
        scheduler = TaskScheduler()
        before = datetime.now() - timedelta(seconds=1)
        scheduler.reload_jobs()

        job = scheduler.scheduler.get_job("daily_post_opportunity_job")
        self.assertIsNotNone(job)
        self.assertEqual(job.trigger.interval, timedelta(minutes=DAILY_POST_CHECK_INTERVAL_MINUTES))
        self.assertGreaterEqual(job.next_run_time.replace(tzinfo=None), before)
        self.assertIsNone(job.misfire_grace_time)
        self.assertIsNone(scheduler.scheduler.get_job("periodic_scan_job"))

    async def test_daily_check_stops_after_a_success_today(self):
        scheduler = TaskScheduler()
        fake_db = SimpleNamespace(has_successful_video_today=lambda: True)
        scheduler._auto_process_next_video = AsyncMock()

        with (
            patch("scheduler.task_scheduler.db", fake_db),
            patch("scheduler.task_scheduler.config_mgr.get", return_value={"auto_mode": True}),
        ):
            await scheduler._scheduled_daily_post_check()

        scheduler._auto_process_next_video.assert_not_awaited()

    async def test_daily_check_posts_when_today_has_no_success(self):
        scheduler = TaskScheduler()
        fake_db = SimpleNamespace(has_successful_video_today=lambda: False)
        fake_workflow = SimpleNamespace(is_busy=False)
        scheduler._auto_process_next_video = AsyncMock()

        with (
            patch("scheduler.task_scheduler.db", fake_db),
            patch("scheduler.task_scheduler.workflow_mgr", fake_workflow),
            patch("scheduler.task_scheduler.config_mgr.get", return_value={"auto_mode": True}),
        ):
            await scheduler._scheduled_daily_post_check()

        scheduler._auto_process_next_video.assert_awaited_once()

    async def test_failed_publish_does_not_mark_the_day_complete(self):
        scheduler = TaskScheduler()
        success_checks = iter((False, False))
        fake_db = SimpleNamespace(
            has_successful_video_today=lambda: next(success_checks),
            get_last_success_at=lambda platform: None,
            get_oldest_pending_video=lambda: {"id": 7, "title": "Video test"},
        )
        fake_workflow = SimpleNamespace(publish_video_to_platforms=AsyncMock())

        with (
            patch("scheduler.task_scheduler.db", fake_db),
            patch("scheduler.task_scheduler.workflow_mgr", fake_workflow),
            patch(
                "scheduler.task_scheduler.config_mgr.get",
                return_value={"min_delay_between_posts_minutes": 180},
            ),
        ):
            await scheduler._auto_process_next_video()

        fake_workflow.publish_video_to_platforms.assert_awaited_once_with(7, enforce_ig_gap=True)

    async def test_empty_queue_downloads_completed_video_even_when_created_today(self):
        scheduler = TaskScheduler()
        success_checks = iter((False, True))
        pending_checks = iter((None, {"id": 17, "title": "Video mới"}))
        fake_db = SimpleNamespace(
            has_successful_video_today=lambda: next(success_checks),
            get_last_success_at=lambda platform: None,
            get_oldest_pending_video=lambda: next(pending_checks),
        )
        fake_workflow = SimpleNamespace(
            scan_and_download=AsyncMock(return_value=[{"id": 17}]),
            publish_video_to_platforms=AsyncMock(),
        )

        with (
            patch("scheduler.task_scheduler.db", fake_db),
            patch("scheduler.task_scheduler.workflow_mgr", fake_workflow),
            patch("scheduler.task_scheduler.logger", Mock()),
            patch(
                "scheduler.task_scheduler.config_mgr.get",
                return_value={"min_delay_between_posts_minutes": 180},
            ),
        ):
            await scheduler._auto_process_next_video()

        fake_workflow.scan_and_download.assert_awaited_once_with(
            max_items=1,
            force_latest=False,
            oldest_first=True,
            exclude_today=False,
        )
        fake_workflow.publish_video_to_platforms.assert_awaited_once_with(
            17, enforce_ig_gap=True
        )


if __name__ == "__main__":
    unittest.main()
