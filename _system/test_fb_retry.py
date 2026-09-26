import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
from test_full_suite import get_test_video, test_facebook_step
from automation.browser_engine import browser_engine
from automation.posters.facebook_poster import FacebookPoster


async def main():
    v = await get_test_video()
    print("Video:", v.get("file_path"))
    fb = await test_facebook_step(v, schedule_time="10:00")
    await browser_engine.close()
    print("FB", fb)
    ok = fb.get("success") and not fb.get("error")
    url = (fb.get("url") or "")
    if ok and not FacebookPoster()._is_fb_permalink(url):
        print("WARN: url chưa phải permalink Facebook Reel:", url)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
