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
from automation.posters.youtube_poster import youtube_poster

async def main():
    print("=" * 60)
    print("  BAT DAU BUOC 2: KIEM THU DANG VIDEO LEN YOUTUBE SHORTS")
    print("=" * 60)

    # Get the latest downloaded video from database
    videos = db.list_videos(limit=1)
    if not videos:
        print("[LỖI] Chưa có video nào trong Database. Vui lòng chạy Bước 1 trước!")
        return

    video = videos[0]
    print(f"\n[INFO] Chon video ID #{video['id']}: '{video.get('suggested_title') or video.get('title')}'")
    print(f"[INFO] File: {video.get('file_path')}")

    # Launch headed browser so user can watch live
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)

    print("\n[INFO] Dang tien hanh dang video len YouTube Studio (Che do: Khong cong khai / Unlisted)...")
    res = await youtube_poster.post_video(page, video, privacy_override="unlisted")

    print("\n" + "=" * 60)
    if res.get("success"):
        print(f"✅ THÀNH CÔNG! Video da duoc dang len YouTube Shorts!")
        print(f"🔗 Link video: {res.get('url', 'Da dang tren Studio')}")
        db.record_post(video["id"], "youtube", "success", post_url=res.get("url", ""))
    else:
        print(f"❌ THAT BAI: {res.get('error')}")
        db.record_post(video["id"], "youtube", "failed", error_message=res.get("error", ""))
    print("=" * 60)

    await asyncio.sleep(5)
    await browser_engine.close()

if __name__ == "__main__":
    asyncio.run(main())
