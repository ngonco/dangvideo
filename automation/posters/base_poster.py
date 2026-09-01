import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from playwright.async_api import Page, BrowserContext
from core.logger import logger
from core.config_manager import config_mgr
from automation.hashtag_manager import hashtag_mgr

class BasePoster(ABC):
    def __init__(self, platform_name: str):
        self.platform_name = platform_name

    def format_caption(self, video_data: Dict[str, Any]) -> str:
        """Ghép tiêu đề, hashtag đạo lý ngẫu nhiên và chữ ký theo cấu hình"""
        title = video_data.get("suggested_title") or video_data.get("title") or ""
        hashtags = video_data.get("hashtags")
        
        # Nếu video chưa có hashtag trong database, tự sinh bộ hashtag mới
        if not hashtags:
            raw_script = video_data.get("raw_script", "")
            hashtags = hashtag_mgr.generate_random_hashtags(raw_script, count=5)

        custom_cfg = config_mgr.get("custom_caption", {})
        prefix = custom_cfg.get("prefix_text", "").strip()
        append = custom_cfg.get("append_text", "").strip()

        parts = []
        if prefix:
            parts.append(prefix)
        if title:
            parts.append(title)
        if hashtags:
            parts.append(hashtags)
        if append:
            parts.append(append)

        return "\n\n".join(parts).strip()

    def validate_video_file(self, file_path: str) -> bool:
        if not file_path or not os.path.exists(file_path):
            logger.error(f"Tệp video không tồn tại: {file_path}", self.platform_name.upper())
            return False
        if os.path.getsize(file_path) == 0:
            logger.error(f"Tệp video rỗng (0 bytes): {file_path}", self.platform_name.upper())
            return False
        return True

    @abstractmethod
    async def post_video(self, page: Page, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """Thực hiện đăng video lên nền tảng. Trả về {'success': bool, 'url': str, 'error': str}"""
        pass
