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
from automation.hatbuinho_crawler import hatbuinho_crawler

async def main():
    print("=" * 60)
    print("  BẮT ĐẦU: KIỂM THỬ TẢI VIDEO MỚI NHẤT TỪ HATBUINHO (TEST MODE)")
    print("=" * 60)

    # Force headed mode for visual testing
    ctx = await browser_engine.get_context(headless=False)
    
    print("\n[INFO] Đang tiến hành tải video mới nhất (kể cả trạng thái Đã tải xuống)...")
    results = await hatbuinho_crawler.scan_and_download(max_items=1, force_latest=True)

    print("\n" + "=" * 60)
    if results:
        print(f"✅ THÀNH CÔNG! Đã tải về {len(results)} video:")
        for idx, item in enumerate(results, 1):
            print(f"\n--- Video #{idx} ---")
            print(f"📌 Tiêu đề hoàn chỉnh : {item.get('suggested_title')}")
            print(f"🏷️  Hashtags           : {item.get('hashtags')}")
            print(f"📁 Tệp video          : {item.get('file_path')}")
            print(f"📊 Kích thước         : {item.get('file_size', 0) // 1024} KB")
            print(f"📝 Kịch bản gốc       : {item.get('raw_script', '')[:100]}...")
    else:
        print("⚠️  Không tìm thấy video nào trên trang.")
    print("=" * 60)

    await asyncio.sleep(4)
    await browser_engine.close()

if __name__ == "__main__":
    asyncio.run(main())
