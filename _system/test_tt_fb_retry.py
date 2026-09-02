import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
from test_full_suite import get_test_video, test_tiktok_step, test_facebook_step
from automation.browser_engine import browser_engine


async def main():
    v = await get_test_video()
    if not v:
        print("Khong co video")
        return 1
    print("Video:", v.get("suggested_title") or v.get("title"), v.get("file_path"))
    tt = await test_tiktok_step(v, schedule_time="10:00")
    fb = await test_facebook_step(v, schedule_time="10:00")
    await browser_engine.close()
    print("TT", tt)
    print("FB", fb)
    tt_ok = bool(tt.get("success")) and not tt.get("error")
    fb_ok = bool(fb.get("success")) and not fb.get("error")
    return 0 if tt_ok and fb_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
