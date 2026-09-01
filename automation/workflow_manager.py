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

    async def scan_and_download(self, max_items: Optional[int] = None, force_latest: bool = False) -> List[Dict[str, Any]]:
        if self._is_busy:
            logger.warning("Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi...", "WORKFLOW")
            return []

        async with self._lock:
            self._is_busy = True
            try:
                mode_name = "TEST ÉP TẢI VIDEO MỚI NHẤT" if force_latest else "QUÉT TẢI VIDEO 'CHƯA TẢI XUỐNG'"
                logger.info(f"Bắt đầu tác vụ: {mode_name} từ hatbuinho.com...", "WORKFLOW")
                results = await hatbuinho_crawler.scan_and_download(max_items=max_items, force_latest=force_latest)
                return results
            finally:
                self._is_busy = False

    async def publish_video_to_platforms(self, video_id: int, target_platforms: Optional[List[str]] = None) -> Dict[str, Any]:
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

                results = {}
                for plat in target_platforms:
                    logger.info(f"--- Đang chuẩn bị đăng lên {plat.upper()} ---", "WORKFLOW")
                    res = {"success": False, "error": "Nền tảng chưa hỗ trợ", "url": ""}

                    try:
                        # Ensure browser and page are active for each platform
                        ctx = await browser_engine.get_context()
                        page = await browser_engine.get_page(ctx)

                        if plat == "youtube":
                            res = await youtube_poster.post_video(page, video)
                        elif plat == "tiktok":
                            res = await tiktok_poster.post_video(page, video)
                        elif plat == "facebook":
                            res = await facebook_poster.post_video(page, video)
                        elif plat == "instagram":
                            res = await instagram_poster.post_video(page, video)

                    except Exception as ex:
                        logger.error(f"Lỗi ngoại lệ khi đăng lên {plat.upper()}: {str(ex)}", "WORKFLOW")
                        res = {"success": False, "error": str(ex), "url": ""}

                    status = "success" if res.get("success") else "failed"
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
