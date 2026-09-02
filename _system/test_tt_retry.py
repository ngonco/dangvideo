import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
from test_full_suite import get_test_video, test_tiktok_step
from automation.browser_engine import browser_engine


async def main():
    v = await get_test_video()
    print("Video:", v.get("file_path"))
    tt = await test_tiktok_step(v, schedule_time="10:00")
    await browser_engine.close()
    print("TT", tt)
    ok = tt.get("success") and not tt.get("error")
    url = (tt.get("url") or "")
    if ok and "tiktokstudio" in url:
        print("WARN: url vẫn là Studio Content, chưa copy permalink")
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
