import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import asyncio
import os
import argparse
import traceback
from datetime import datetime

from core.logger import logger
from core.database import db
from core.config_manager import config_mgr, ROOT_DIR, SYSTEM_DIR, DOWNLOADS_DIR
from core.autostart_manager import autostart_mgr
from core.email_reporter import email_reporter
from automation.browser_engine import browser_engine
from automation.workflow_manager import workflow_mgr
from automation.hatbuinho_crawler import hatbuinho_crawler
from automation.posters.youtube_poster import youtube_poster
from automation.posters.tiktok_poster import tiktok_poster
from automation.posters.facebook_poster import facebook_poster
from automation.posters.instagram_poster import instagram_poster

async def test_api_and_db():
    print("\n" + "="*65)
    print(" [1/6] KIỂM THỬ CƠ SỞ DỮ LIỆU & QUẢN LÝ CẤU HÌNH")
    print("="*65)
    
    # 1. Check DB
    stats = db.get_stats()
    print(f"✅ Thống kê DB: {stats}")
    
    queue = db.get_queue_summary(slots_per_day=3)
    print(f"✅ Kho hàng đợi: {queue['total_pending']} video (Dự kiến {queue['estimated_days']} ngày)")
    
    # 2. Check Config
    cfg = config_mgr.config
    sched_pub = cfg.get("schedule_publish", {})
    print(f"✅ Cấu hình Lên lịch đăng bài: {sched_pub}")
    
    # 3. Check Autostart
    is_auto = autostart_mgr.is_autostart_enabled()
    print(f"✅ Trạng thái Autostart: {is_auto}")
    
    # 4. Check Post History
    history = db.get_post_history(limit=5)
    print(f"✅ Lịch sử bài đăng ({len(history)} mục gần nhất)")

async def test_hatbuinho_step(force_latest=True):
    print("\n" + "="*65)
    print(" [2/6] KIỂM THỬ QUÉT TẢI TỪ HATBUINHO.COM (TRÌNH DUYỆT THỰC TẾ)")
    print("="*65)
    
    results = await hatbuinho_crawler.scan_and_download(max_items=1, force_latest=force_latest, oldest_first=False)
    if results:
        v = results[0]
        print(f"🎉 TẢI THÀNH CÔNG: {v.get('title')}")
        print(f"   - Tệp: {v.get('file_path')}")
        print(f"   - Tiêu đề tối ưu: '{v.get('suggested_title')}'")
        print(f"   - Hashtags: '{v.get('hashtags')}'")
        print(f"   - Dung lượng: {v.get('file_size') // 1024} KB")
        return v
    else:
        print("⚠️ Không có video nào được tải về từ HatBuiNho.")
        return None

async def get_test_video():
    # 1. Try DB
    videos = db.list_videos(limit=10)
    for v in videos:
        if v.get("file_path") and os.path.exists(v.get("file_path")):
            return v
            
    # 2. Try downloads folder
    if os.path.exists(DOWNLOADS_DIR):
        for f in os.listdir(DOWNLOADS_DIR):
            if f.endswith(".mp4"):
                full_path = os.path.join(DOWNLOADS_DIR, f)
                title = f.replace(".mp4", "")
                vid_data = {
                    "hatbuinho_id": "test_" + f[:8],
                    "title": title,
                    "raw_script": title,
                    "suggested_title": title,
                    "hashtags": "#luatnhanqua #loiphatday #baihoccuocsong #daycon #Shorts",
                    "file_path": full_path,
                    "file_size": os.path.getsize(full_path),
                    "status": "downloaded"
                }
                vid_id = db.add_or_update_video(vid_data)
                vid_data["id"] = vid_id
                return vid_data
    return None

async def test_youtube_step(video_data, schedule_time="20:00"):
    print("\n" + "="*65)
    print(f" [3/6] KIỂM THỬ YOUTUBE SHORTS (HẸN GIỜ: {schedule_time} TỐI NAY)")
    print("="*65)
    
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    
    res = await youtube_poster.post_video(page, video_data, schedule_time=schedule_time)
    print(f"📊 Kết quả YouTube: {res}")
    return res

async def test_tiktok_step(video_data, schedule_time="20:00"):
    print("\n" + "="*65)
    print(f" [4/6] KIỂM THỬ TIKTOK CREATOR (HẸN GIỜ: {schedule_time} TỐI NAY)")
    print("="*65)
    
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    
    res = await tiktok_poster.post_video(page, video_data, schedule_time=schedule_time)
    print(f"📊 Kết quả TikTok: {res}")
    return res

async def test_facebook_step(video_data, schedule_time="20:00"):
    print("\n" + "="*65)
    print(" [5/6] KIỂM THỬ FACEBOOK REELS / FEED (CHẾ ĐỘ THỬ NGHIỆM ONLY ME)")
    print("="*65)
    
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    
    res = await facebook_poster.post_video(page, video_data, schedule_time=schedule_time)
    print(f"📊 Kết quả Facebook: {res}")
    return res

async def test_instagram_step(video_data, schedule_time="20:00"):
    print("\n" + "="*65)
    print(" [6/6] KIỂM THỬ INSTAGRAM BÀI VIẾT (CHIA SẺ NGAY, COPY LINK THANH ĐỊA CHỈ)")
    print("="*65)
    
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    
    res = await instagram_poster.post_video(page, video_data, schedule_time=schedule_time)
    print(f"📊 Kết quả Instagram: {res}")
    return res

async def main():
    parser = argparse.ArgumentParser(description="Test Suite Auto Đăng Video")
    parser.add_argument("--step", choices=["api", "hatbuinho", "youtube", "tiktok", "facebook", "instagram", "all"], default="all")
    parser.add_argument("--schedule", default="10:00", help="Giờ hẹn native (mặc định 10:00 sáng mai)")
    args = parser.parse_args()

    print("="*65)
    print("   🚀 HỆ THỐNG KIỂM THỬ TOÀN DIỆN AUTO ĐĂNG VIDEO PRO")
    print(f"   ⏰ Mốc giờ hẹn kiểm thử: {args.schedule} Tối Nay")
    print("="*65)

    if args.step in ["api", "all"]:
        await test_api_and_db()

    target_video = None
    if args.step in ["hatbuinho", "all"]:
        target_video = await test_hatbuinho_step(force_latest=True)

    if not target_video:
        target_video = await get_test_video()

    if not target_video and args.step != "api":
        print("❌ Không tìm thấy video hợp lệ để chạy test các nền tảng mạng xã hội.")
        await browser_engine.close()
        return

    if target_video:
        print(f"\n🎯 Video sử dụng cho kiểm thử: #{target_video.get('id', 1)} '{target_video.get('suggested_title') or target_video.get('title')}'")
        print(f"📁 Tệp: {target_video.get('file_path')}")

    if args.step in ["youtube", "all"]:
        await test_youtube_step(target_video, schedule_time=args.schedule)

    if args.step in ["tiktok", "all"]:
        await test_tiktok_step(target_video, schedule_time=args.schedule)

    if args.step in ["facebook", "all"]:
        await test_facebook_step(target_video, schedule_time=args.schedule)

    if args.step in ["instagram", "all"]:
        await test_instagram_step(target_video, schedule_time=args.schedule)

    await browser_engine.close()
    print("\n" + "="*65)
    print("🎉 HOÀN TẤT BƯỚC KIỂM THỬ!")
    print("="*65)

if __name__ == "__main__":
    asyncio.run(main())
