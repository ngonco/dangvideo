import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import asyncio
import json

from core.database import db
from core.schedule_helper import get_native_schedule
from automation.browser_engine import browser_engine
from automation.workflow_manager import workflow_mgr


async def main():
    native = get_native_schedule()
    print("=" * 65)
    print("  TEST NÚT ĐĂNG 1 VIDEO NGAY (4 NỀN TẢNG, HẸN 10:00 SÁNG MAI)")
    print(f"  Mốc native: {native['label']}")
    print("=" * 65)

    pending = db.get_oldest_pending_video()
    if not pending:
        print("Kho trống — ưu tiên Chưa tải xuống, hết thì video mới nhất...")
        await workflow_mgr.scan_and_download(
            max_items=1, force_latest=False, oldest_first=True, fallback_latest=True
        )
        pending = db.get_oldest_pending_video()

    if not pending:
        print("❌ Không tìm thấy video nào để đăng.")
        await browser_engine.close()
        return 1

    print(f"Video #{pending['id']}: {pending.get('suggested_title') or pending.get('title')}")
    print(f"File: {pending.get('file_path')}")

    # Giống nút Đăng 1 video ngay, nhưng bỏ cổng 3 tiếng IG để kiểm thử đủ 4 kênh.
    result = await workflow_mgr.publish_video_to_platforms(
        pending["id"],
        schedule_time=native["time"],
        enforce_ig_gap=False,
    )

    details = result.get("details") or {}
    print("\n" + "=" * 65)
    print("KẾT QUẢ:")
    print(json.dumps(details, ensure_ascii=False, indent=2, default=str))
    print("=" * 65)

    ok = 0
    fail = 0
    for plat, res in details.items():
        success = bool(res.get("success")) and not res.get("error")
        skipped = bool(res.get("skipped"))
        if success or skipped:
            ok += 1
            mark = "SKIP" if skipped else "OK"
        else:
            fail += 1
            mark = "FAIL"
        print(f"  [{mark}] {plat}: {res.get('url') or res.get('error')}")

    await browser_engine.close()
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
