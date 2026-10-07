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

    async def test_completed_daily_run_does_not_select_another_video(self):
        scheduler=TaskScheduler()
        fake_db=SimpleNamespace(get_daily_run=lambda: {'video_id':7,'platforms':['youtube']},
            get_video_by_id=lambda v:{'status':'posted'},
            get_successful_platforms_for_video=lambda v:['youtube'],pending_delivery_videos=lambda:[],
            get_posting_health=lambda:{'complete':True},set_health=Mock(return_value=False))
        scheduler._notify_reserve=AsyncMock()
        workflow=SimpleNamespace(is_busy=False,publish_video_to_platforms=AsyncMock())
        with patch('scheduler.task_scheduler.db',fake_db),patch('scheduler.task_scheduler.workflow_mgr',workflow):
            await scheduler._scheduled_daily_post_check()
        workflow.publish_video_to_platforms.assert_not_awaited()

    async def test_partial_daily_run_retries_after_other_channel_succeeds(self):
        scheduler=TaskScheduler()
        fake_db=SimpleNamespace(get_daily_run=lambda: {'video_id':7,'platforms':['youtube','facebook']},
            get_video_by_id=lambda v:{'status':'downloaded'},
            get_successful_platforms_for_video=lambda v:['youtube'],pending_delivery_videos=lambda:[7],
            required_platforms=lambda v:['youtube','facebook'],get_posting_health=lambda:{'complete':False},
            set_health=Mock(return_value=False))
        scheduler._notify_reserve=AsyncMock()
        workflow=SimpleNamespace(is_busy=False,publish_video_to_platforms=AsyncMock())
        with patch('scheduler.task_scheduler.db',fake_db),patch('scheduler.task_scheduler.workflow_mgr',workflow),patch('scheduler.task_scheduler.config_mgr.get',side_effect=lambda k,*a:{'auto_mode':True} if k=='schedule' else {'youtube':{'enabled':True},'facebook':{'enabled':True}}):
            await scheduler._scheduled_daily_post_check()
        workflow.publish_video_to_platforms.assert_awaited_once_with(7,target_platforms=['youtube','facebook'],enforce_ig_gap=True,respect_retry=True)

    async def test_busy_workflow_is_not_interrupted(self):
        scheduler=TaskScheduler();scheduler._auto_process_next_video=AsyncMock()
        with patch('scheduler.task_scheduler.workflow_mgr',SimpleNamespace(is_busy=True)),patch('scheduler.task_scheduler.config_mgr.get',return_value={'auto_mode':True}):
            await scheduler._scheduled_daily_post_check()
        scheduler._auto_process_next_video.assert_not_awaited()

    async def test_removed_daily_video_is_not_restored(self):
        scheduler=TaskScheduler();scheduler._notify_reserve=AsyncMock()
        fake_db=SimpleNamespace(get_daily_run=lambda:{'video_id':7,'platforms':['youtube']},get_video_by_id=lambda v:{'status':'cleaned'},
            get_successful_platforms_for_video=lambda v:[],pending_delivery_videos=lambda:[],get_posting_health=lambda:{'complete':False},set_health=Mock())
        workflow=SimpleNamespace(is_busy=False,publish_video_to_platforms=AsyncMock())
        with patch('scheduler.task_scheduler.db',fake_db),patch('scheduler.task_scheduler.workflow_mgr',workflow):
            await scheduler._scheduled_daily_post_check()
        workflow.publish_video_to_platforms.assert_not_awaited()

    async def test_reserve_refill_keeps_today_eligible(self):
        scheduler=TaskScheduler();scheduler._notify_reserve=AsyncMock()
        workflow=SimpleNamespace(is_busy=False,scan_and_download=AsyncMock())
        with patch('scheduler.task_scheduler.db',SimpleNamespace(reserve_count=lambda:2)),patch('scheduler.task_scheduler.workflow_mgr',workflow):
            await scheduler._fill_reserve()
        workflow.scan_and_download.assert_awaited_once_with(max_items=5,force_latest=False,oldest_first=True,exclude_today=False)

if __name__ == '__main__':unittest.main()
