import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import asyncio
import os
import argparse
from datetime import datetime

from core.logger import logger
from core.database import db
from core.config_manager import config_mgr
from automation.browser_engine import browser_engine
from automation.posters.youtube_poster import youtube_poster
from automation.posters.tiktok_poster import tiktok_poster
from automation.posters.facebook_poster import facebook_poster
from automation.posters.instagram_poster import instagram_poster

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "debug_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

async def capture(page, name: str):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    try:
        await page.screenshot(path=path, full_page=False)
        print(f"📸 [SCREENSHOT] Đã chụp ảnh: {path}")
    except Exception as e:
        print(f"⚠️ Không thể chụp ảnh: {e}")

async def test_youtube(video_data):
    print("\n" + "=" * 65)
    print("  [DEBUG REAL] KIỂM THỬ THỰC TẾ TRÊN YOUTUBE STUDIO")
    print("=" * 65)
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    
    await capture(page, "yt_01_start")
    res = await youtube_poster.post_video(page, video_data, schedule_time="09:00")
    await capture(page, "yt_02_after_post")
    
    print(f"\n📊 KẾT QUẢ YOUTUBE: {res}")
    return res

async def test_tiktok(video_data):
    print("\n" + "=" * 65)
    print("  [DEBUG REAL] KIỂM THỬ THỰC TẾ TRÊN TIKTOK CREATOR")
    print("=" * 65)
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    
    await capture(page, "tt_01_start")
    res = await tiktok_poster.post_video(page, video_data, schedule_time="09:00")
    await capture(page, "tt_02_after_post")
    
    print(f"\n📊 KẾT QUẢ TIKTOK: {res}")
    return res

async def test_facebook(video_data):
    print("\n" + "=" * 65)
    print("  [DEBUG REAL] KIỂM THỬ THỰC TẾ TRÊN FACEBOOK")
    print("=" * 65)
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    
    await capture(page, "fb_01_start")
    res = await facebook_poster.post_video(page, video_data, schedule_time="09:00")
    await capture(page, "fb_02_after_post")
    
    print(f"\n📊 KẾT QUẢ FACEBOOK: {res}")
    return res

async def test_instagram(video_data):
    print("\n" + "=" * 65)
    print("  [DEBUG REAL] KIỂM THỬ THỰC TẾ TRÊN INSTAGRAM")
    print("=" * 65)
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    
    await capture(page, "ig_01_start")
    res = await instagram_poster.post_video(page, video_data, schedule_time="09:00")
    await capture(page, "ig_02_after_post")
    
    print(f"\n📊 KẾT QUẢ INSTAGRAM: {res}")
    return res

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["youtube", "tiktok", "facebook", "instagram", "all"], default="all")
    args = parser.parse_args()

    # Get sample video
    videos = db.list_videos(limit=10)
    target = None
    for v in videos:
        if v.get("file_path") and os.path.exists(v.get("file_path")):
            target = v
            break
            
    if not target:
        print("⚠️ Không tìm thấy video hợp lệ trong CSDL.")
        return

    print(f"🎯 Target video: #{target['id']} - {target.get('title')}")
    print(f"📁 File: {target.get('file_path')}")

    if args.step in ["youtube", "all"]:
        await test_youtube(target)
    if args.step in ["tiktok", "all"]:
        await test_tiktok(target)
    if args.step in ["facebook", "all"]:
        await test_facebook(target)
    if args.step in ["instagram", "all"]:
        await test_instagram(target)

    await browser_engine.close()

if __name__ == "__main__":
    asyncio.run(main())
