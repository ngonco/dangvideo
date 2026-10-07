import asyncio
import gc
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock, patch
from core.database import Database
from core.posting_store import local_now, stamp
from core.schedule_helper import get_next_post_time_slot
from automation.hatbuinho_crawler import HatBuiNhoCrawler
from automation.workflow_manager import WorkflowManager
from scheduler.task_scheduler import TaskScheduler


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.temp.name, 'data.db'))

    def tearDown(self):
        self.db = None
        gc.collect()
        self.temp.cleanup()

    def video(self, name, content=b'first'):
        path = os.path.join(self.temp.name, name+'.mp4')
        with open(path, 'wb') as f:
            f.write(content)
        return self.db.add_or_update_video({'hatbuinho_id':name, 'title':name,'file_path':path,'file_size':len(content)})

    def test_same_size_different_content_is_not_duplicate(self):
        first = self.video('a', b'AAAA')
        second = self.video('b', b'BBBB')
        third = self.video('c', b'AAAA')
        self.assertIsNone(self.db.find_content_duplicate(self.db.get_video_by_id(second)['file_path'], exclude_id=second))
        self.assertEqual(self.db.find_content_duplicate(self.db.get_video_by_id(third)['file_path'], exclude_id=third), first)

    def test_concurrent_assignment_is_one_video(self):
        first = self.video('a'); self.video('b')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.db.assign_daily_video(['youtube']), range(2)))
        self.assertEqual(results, [first, first])
        self.assertEqual(self.db.reserve_count(),1)

    def test_backfill_success_does_not_consume_new_day(self):
        old = self.video('old'); new = self.video('new')
        self.db.assign_daily_video(['facebook'], day='2026-10-06')
        self.db.record_post(old,'facebook','success')
        self.assertEqual(self.db.assign_daily_video(['facebook'],day='2026-10-07'),new)

    def test_submitted_crash_never_becomes_upload_retry(self):
        vid = self.video('v'); self.db.ensure_posting_task(vid,'youtube')
        self.db.begin_posting(vid,'youtube'); self.db.mark_submitting(vid,'youtube','https://youtube.com/shorts/ABCDEFGHIJK')
        self.db.recover_interrupted_uploads()
        self.db.finish_posting_task(vid,'youtube','failed','Timeout')
        task = self.db.get_posting_task(vid,'youtube')
        self.assertEqual(task['state'],'verifying')
        self.assertTrue(task['submitted_at'])
        self.assertTrue(task['post_url'])

    def test_real_poster_checkpoint_uses_lowercase_channel_key(self):
        from automation.posters.youtube_poster import YouTubePoster
        vid=self.video('checkpoint');self.db.ensure_posting_task(vid,'youtube')
        poster=YouTubePoster();poster.delivery_video_id=vid
        with patch('core.database.db',self.db):
            poster.checkpoint_submission('https://youtube.com/shorts/ABCDEFGHIJK')
        self.assertTrue(self.db.get_posting_task(vid,'youtube')['submitted_at'])

    def test_pre_submit_retry_backoff_and_restart(self):
        vid = self.video('v'); self.db.ensure_posting_task(vid,'facebook')
        for delay in [30,60,120,120]:
            self.db.begin_posting(vid,'facebook'); self.db.finish_posting_task(vid,'facebook','failed','Network')
            task = self.db.get_posting_task(vid,'facebook')
            remaining = (datetime.strptime(task['next_retry'],'%Y-%m-%d %H:%M:%S')-local_now()).total_seconds()/60
            self.assertAlmostEqual(remaining,delay,delta=0.1)
        self.db.begin_posting(vid,'facebook'); self.db.recover_interrupted_uploads()
        self.assertEqual(self.db.get_posting_task(vid,'facebook')['state'],'failed')

    def test_hidden_deleted_and_bilingual_badges(self):
        classify = HatBuiNhoCrawler.classify_source_labels
        self.assertEqual(classify(['22:34','🗑️ Video đã xoá']),'deleted')
        self.assertEqual(classify(['Video deleted']),'deleted')
        self.assertEqual(classify(['Chưa tải xuống']),'pending')
        self.assertEqual(classify(['Not downloaded']),'pending')
        self.assertEqual(classify(['Đã tải xuống']),'downloaded')
        self.assertEqual(classify(['???']),'unknown')

    def test_configured_slots_and_fallback(self):
        now=datetime(2026,10,7,9)
        with patch('core.schedule_helper.config_mgr.get',side_effect=lambda k,*a: {'post_time_slots':['11:30','20:00']} if k=='schedule' else {}):
            self.assertEqual(get_next_post_time_slot(now)['time'],'11:30')
        with patch('core.schedule_helper.config_mgr.get',side_effect=lambda k,*a: {'post_time_slots':[]} if k=='schedule' else {'default_time':'10:00','target_date':'tomorrow'}):
            self.assertEqual(get_next_post_time_slot(now)['datetime'],datetime(2026,10,8,10))

    def test_removed_video_is_never_assigned_again(self):
        vid=self.video('removed')
        self.db.remove_video_from_queue(vid)
        self.assertTrue(self.db.get_video_by_id(vid)['queue_removed_at'])
        self.assertIsNone(self.db.assign_daily_video(['youtube']))

    def test_needs_login_waits_for_user(self):
        vid=self.video('login');self.db.ensure_posting_task(vid,'facebook')
        self.db.finish_posting_task(vid,'facebook','needs_login','Đăng nhập hết hạn')
        self.assertEqual(self.db.get_posting_task(vid,'facebook')['next_retry'],'')
        self.assertNotIn(vid,self.db.pending_delivery_videos())

    def test_changing_enabled_channels_keeps_daily_video(self):
        vid=self.video('targets');self.db.assign_daily_video(['youtube','facebook'])
        self.db.record_post(vid,'youtube','success')
        self.db.update_today_targets(['youtube'])
        self.assertEqual(self.db.get_daily_run()['video_id'],vid)
        self.assertTrue(self.db.get_posting_health()['complete'])
        self.db.update_today_targets(['youtube','instagram'])
        self.assertEqual(self.db.get_daily_run()['platforms'],['youtube','instagram'])
        self.assertEqual(self.db.get_posting_task(vid,'instagram')['state'],'pending')
        self.assertFalse(self.db.get_posting_health()['complete'])

    def test_youtube_schedule_requires_exact_date_and_time(self):
        from automation.posting_verifier import schedule_fields_match
        self.assertTrue(schedule_fields_match('Oct 7, 2026','8:00\u202fPM','2026-10-07 20:00:00'))
        self.assertTrue(schedule_fields_match('7 thg 10, 2026','20:00','2026-10-07 20:00:00'))
        self.assertFalse(schedule_fields_match('Oct 8, 2026','8:00 PM','2026-10-07 20:00:00'))
        self.assertFalse(schedule_fields_match('Oct 7, 2026','8:00 AM','2026-10-07 20:00:00'))

    def test_supervisor_honors_exit_and_retries_only_crashes(self):
        from core.app_supervisor import supervise
        exe=os.path.join(self.temp.name,'Tu_dong_dang_video.exe')
        with open(exe,'wb') as f:f.write(b'exe')
        with patch('core.app_supervisor.subprocess.Popen') as launch,patch('core.app_supervisor.time.sleep'):
            launch.return_value.wait.side_effect=[1,1,0]
            supervise(exe)
            self.assertEqual(launch.call_count,3)
        with patch('core.app_supervisor.subprocess.Popen') as launch:
            launch.return_value.wait.return_value=0
            supervise(exe)
            self.assertEqual(launch.call_count,1)


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(os.path.join(self.temp.name,'db'))
        path=os.path.join(self.temp.name,'video.mp4')
        with open(path,'wb') as f:f.write(b'video')
        self.vid=self.db.add_or_update_video({'hatbuinho_id':'test','title':'Test','file_path':path})

    async def asyncTearDown(self):
        self.db=None;gc.collect();self.temp.cleanup()

    async def test_manual_one_channel_keeps_other_channels_pending(self):
        poster=Mock(post_video=AsyncMock(return_value={'success':True,'url':'https://youtube.com/shorts/ABCDEFGHIJK'}))
        browser=Mock(get_context=AsyncMock(),get_page=AsyncMock(),close=AsyncMock())
        with patch('automation.workflow_manager.db',self.db),patch('automation.workflow_manager.youtube_poster',poster),patch('automation.workflow_manager.browser_engine',browser),patch('automation.workflow_manager.asyncio.sleep',AsyncMock()),patch('automation.posting_verifier.verify_delivery',AsyncMock(return_value={'verified':True,'url':'https://youtube.com/shorts/ABCDEFGHIJK','state':'scheduled'})),patch('automation.workflow_manager.config_mgr.get',return_value={p:{'enabled':True} for p in ['youtube','tiktok','facebook','instagram']}):
            result=await WorkflowManager().publish_video_to_platforms(self.vid,target_platforms=['youtube'])
        self.assertFalse(result['completed'])
        self.assertEqual(self.db.get_video_by_id(self.vid)['status'],'downloaded')

    async def test_uncertain_submission_only_reconciles(self):
        self.db.ensure_posting_task(self.vid,'youtube');self.db.mark_submitting(self.vid,'youtube')
        poster=Mock(post_video=AsyncMock())
        browser=Mock(get_context=AsyncMock(),get_page=AsyncMock())
        with patch('automation.workflow_manager.db',self.db),patch('automation.workflow_manager.youtube_poster',poster),patch('automation.workflow_manager.browser_engine',browser),patch('automation.workflow_manager.asyncio.sleep',AsyncMock()),patch('automation.posting_verifier.verify_delivery',AsyncMock(return_value={'verified':False,'url':''})),patch('core.email_reporter.email_reporter.send_error_alert'):
            await WorkflowManager().publish_video_to_platforms(self.vid,target_platforms=['youtube'])
        poster.post_video.assert_not_awaited()
        self.assertEqual(self.db.get_posting_task(self.vid,'youtube')['state'],'verifying')

    async def test_source_failure_still_posts_from_reserve(self):
        scheduler=TaskScheduler()
        fake_workflow=Mock(is_busy=False,publish_video_to_platforms=AsyncMock(),scan_and_download=AsyncMock())
        with patch('scheduler.task_scheduler.db',self.db),patch('scheduler.task_scheduler.workflow_mgr',fake_workflow),patch('scheduler.task_scheduler.config_mgr.get',side_effect=lambda k,*a: {'auto_mode':True} if k=='schedule' else {'youtube':{'enabled':True}}),patch('core.email_reporter.email_reporter.send_error_alert'):
            self.db.set_health('source','network_error','Offline')
            await scheduler._scheduled_daily_post_check()
        fake_workflow.scan_and_download.assert_not_awaited()
        fake_workflow.publish_video_to_platforms.assert_awaited_once()

if __name__=='__main__':unittest.main()
