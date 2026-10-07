import gc
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from automation.hatbuinho_crawler import HatBuiNhoCrawler
from automation.workflow_manager import WorkflowManager
from core.database import Database


class VideoCompletionDatabaseTests(unittest.TestCase):
    def test_success_history_does_not_finish_video_before_workflow_evaluation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_db = Database(os.path.join(temp_dir, "completion.db"))
            video_id = test_db.add_or_update_video(
                {
                    "hatbuinho_id": "partial-video",
                    "raw_script": "Một kịch bản đủ dài để kiểm tra phục hồi video chưa hoàn tất.",
                    "file_path": "video.mp4",
                    "status": "downloaded",
                }
            )

            test_db.record_post(video_id, "youtube", "success")
            self.assertEqual(test_db.get_video_by_id(video_id)["status"], "downloaded")

            test_db.set_video_status(video_id, "posted")
            self.assertEqual(test_db.get_video_by_id(video_id)["status"], "posted")
            self.assertEqual(test_db.get_processed_video("partial-video")["id"], video_id)
            test_db.set_source_media_key(video_id, "https://media.test/20260927_120000_video.mp4")
            self.assertEqual(
                test_db.get_video_by_source_media_key(
                    "https://media.test/20260927_120000_video.mp4"
                )["id"],
                video_id,
            )
            del test_db
            gc.collect()


class ExistingVideoClassificationTests(unittest.TestCase):
    def test_source_media_key_uses_render_timestamp(self):
        crawler = HatBuiNhoCrawler()
        key = crawler._source_media_key(
            {"media_url": "https://media.test/20260927_053240_20260927_053036_idle_video.mp4"}
        )
        self.assertEqual(key, "media:20260927_053240")

    def test_cleaned_video_with_missing_channel_is_not_automatically_restored(self):
        crawler = HatBuiNhoCrawler()
        fake_db = SimpleNamespace(
            get_video_by_source_media_key=lambda key: {"id": 14, "status": "cleaned"},
            get_legacy_video_by_content=lambda item_hash, raw_script: None,
            set_source_media_key=lambda video_id, key: None,
            get_successful_platforms_for_video=lambda video_id: ["youtube", "tiktok", "facebook"],
        )
        platforms = {
            "youtube": {"enabled": True},
            "tiktok": {"enabled": True},
            "facebook": {"enabled": True},
            "instagram": {"enabled": True},
        }

        with (
            patch("automation.hatbuinho_crawler.db", fake_db),
            patch("automation.hatbuinho_crawler.config_mgr.get", return_value=platforms),
        ):
            state = crawler._get_existing_video_state("hash", "script", "media-key")

        self.assertEqual(state["video"]["id"], 14)
        self.assertEqual(state["missing_platforms"], [])

    def test_complete_video_has_no_missing_channels(self):
        crawler = HatBuiNhoCrawler()
        fake_db = SimpleNamespace(
            get_video_by_source_media_key=lambda key: {"id": 11, "status": "cleaned"},
            get_legacy_video_by_content=lambda item_hash, raw_script: None,
            set_source_media_key=lambda video_id, key: None,
            get_successful_platforms_for_video=lambda video_id: [
                "youtube", "tiktok", "facebook", "instagram"
            ],
        )
        platforms = {
            name: {"enabled": True}
            for name in ("youtube", "tiktok", "facebook", "instagram")
        }

        with (
            patch("automation.hatbuinho_crawler.db", fake_db),
            patch("automation.hatbuinho_crawler.config_mgr.get", return_value=platforms),
        ):
            state = crawler._get_existing_video_state("hash", "script", "media-key")

        self.assertEqual(state["missing_platforms"], [])

    def test_new_media_date_is_not_merged_into_older_legacy_record(self):
        crawler = HatBuiNhoCrawler()
        old_video = {
            "id": 14,
            "status": "cleaned",
            "created_date_str": "2026-09-25 07:39:28",
            "downloaded_at": "2026-09-25 07:39:28",
        }
        fake_db = SimpleNamespace(
            get_video_by_source_media_key=lambda key: None,
            get_legacy_video_by_content=lambda item_hash, raw_script: old_video,
            set_source_media_key=Mock(),
            get_successful_platforms_for_video=lambda video_id: ["youtube"],
        )

        with (
            patch("automation.hatbuinho_crawler.db", fake_db),
            patch("automation.hatbuinho_crawler.config_mgr.get", return_value={}),
        ):
            state = crawler._get_existing_video_state(
                "hash", "script", "https://media.test/20260927_053240_video.mp4"
            )

        self.assertIsNone(state)
        fake_db.set_source_media_key.assert_not_called()


class WorkflowCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def _run_instagram_retry(self, instagram_success):
        temp_dir = tempfile.TemporaryDirectory()
        video_path = os.path.join(temp_dir.name, "video.mp4")
        with open(video_path, "wb") as video_file:
            video_file.write(b"video")

        class FakeDB:
            def __init__(self):
                self.successes = {"youtube", "tiktok", "facebook"}
                self.status = None

            def get_video_by_id(self, video_id):
                return {"id": video_id, "title": "Video test", "file_path": video_path}

            def get_successful_platforms_for_video(self, video_id):
                return sorted(self.successes)

            def get_last_success_at(self, platform):
                return None

            def record_post(self, video_id, platform, status, post_url="", error_message=""):
                if status == "success":
                    self.successes.add(platform)

            def set_video_status(self, video_id, status):
                self.status = status

            def claim_manual_daily_video(self, *args): pass
            def ensure_posting_task(self, *args): return {'next_retry':'','submitted_at':'','state':'pending','attempts':0}
            def get_posting_task(self, *args): return {'next_retry':'','submitted_at':'','state':'pending','attempts':0}
            def begin_posting(self, *args): pass
            def finish_posting_task(self, *args): pass
            def required_platforms(self, *args): return []
            def set_health(self, *args): return False
            def set_posting_candidate_url(self, *args): pass

        fake_db = FakeDB()
        fake_browser = SimpleNamespace(
            get_context=AsyncMock(return_value=object()),
            get_page=AsyncMock(return_value=object()),
        )
        instagram_result = {
            "success": instagram_success,
            "url": "https://example.test/post" if instagram_success else "",
            "error": "",
        }
        fake_instagram = SimpleNamespace(post_video=AsyncMock(return_value=instagram_result))
        workflow = WorkflowManager()

        with (
            patch("automation.workflow_manager.db", fake_db),
            patch("automation.workflow_manager.browser_engine", fake_browser),
            patch("automation.workflow_manager.instagram_poster", fake_instagram),
            patch("automation.workflow_manager.logger", Mock()),
            patch("automation.workflow_manager.asyncio.sleep", AsyncMock()),
            patch("automation.posting_verifier.verify_delivery", AsyncMock(return_value={'verified':instagram_success,'url':instagram_result['url'],'state':'published'})),
        ):
            await workflow.publish_video_to_platforms(
                14,
                target_platforms=["youtube", "tiktok", "facebook", "instagram"],
                enforce_ig_gap=True,
            )

        temp_dir.cleanup()
        return fake_db.status, fake_instagram.post_video

    async def test_partial_video_becomes_posted_after_missing_channel_succeeds(self):
        status, instagram_call = await self._run_instagram_retry(True)
        self.assertEqual(status, "posted")
        instagram_call.assert_awaited_once()

    async def test_partial_video_stays_queued_when_missing_channel_fails(self):
        status, instagram_call = await self._run_instagram_retry(False)
        self.assertEqual(status, "downloaded")
        instagram_call.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
