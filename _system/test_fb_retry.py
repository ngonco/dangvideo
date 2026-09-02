import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
from test_full_suite import get_test_video, test_facebook_step
from automation.browser_engine import browser_engine


async def main():
    v = await get_test_video()
    print("Video:", v.get("file_path"))
    fb = await test_facebook_step(v, schedule_time="10:00")
    await browser_engine.close()
    print("FB", fb)
    return 0 if fb.get("success") and not fb.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
