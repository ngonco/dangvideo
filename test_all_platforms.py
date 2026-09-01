import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import asyncio
import os

from core.logger import logger
from core.database import db
from core.config_manager import config_mgr
from automation.browser_engine import browser_engine
from automation.workflow_manager import workflow_mgr

async def main():
    print("=" * 65)
    print("  KIỂM THỬ ĐĂNG VIDEO ĐA NỀN TẢNG (YOUTUBE, TIKTOK, FB, IG)")
    print("=" * 65)

    # Lấy video mới nhất có sẵn trong Database
    videos = db.list_videos(limit=10)
    target_video = None
    for v in videos:
        if v.get("file_path") and os.path.exists(v.get("file_path")):
            target_video = v
            break

    if not target_video:
        print("⚠️ Không tìm thấy video hợp lệ trong database. Hãy quét tải trước!")
        return

    print(f"\n[INFO] Chọn Video ID #{target_video['id']}: '{target_video.get('suggested_title') or target_video.get('title')}'")
    print(f"[INFO] Tệp: {target_video.get('file_path')}")
    print(f"[INFO] Hashtags: {target_video.get('hashtags')}")

    # Bật tất cả 4 nền tảng
    target_platforms = ["youtube", "tiktok", "facebook", "instagram"]
    print(f"\n[INFO] Bắt đầu đăng tải lên các nền tảng: {', '.join(target_platforms).upper()}...")

    result = await workflow_mgr.publish_video_to_platforms(
        video_id=target_video["id"],
        target_platforms=target_platforms
    )

    print("\n" + "=" * 65)
    print("📊 KẾT QUẢ ĐĂNG BÀI ĐA NỀN TẢNG:")
    print("=" * 65)
    details = result.get("details", {})
    for plat, res in details.items():
        status_icon = "✅ THÀNH CÔNG" if res.get("success") else "❌ THẤT BÀI"
        url = res.get("url", "Chưa có link")
        err = f" (Lỗi: {res.get('error')})" if res.get("error") else ""
        print(f"- {plat.upper():<10} : {status_icon} | Link: {url}{err}")
    print("=" * 65)

    await browser_engine.close()

if __name__ == "__main__":
    asyncio.run(main())
