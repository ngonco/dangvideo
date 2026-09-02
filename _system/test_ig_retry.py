import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
from test_full_suite import get_test_video, test_instagram_step
from automation.browser_engine import browser_engine
from automation.posters.instagram_poster import InstagramPoster


async def main():
    v = await get_test_video()
    print("Video:", v.get("file_path") if v else None)
    ig = await test_instagram_step(v, schedule_time="10:00")
    await browser_engine.close()
    print("IG", ig)
    ok = ig.get("success") and not ig.get("error")
    url = (ig.get("url") or "")
    if ok and not InstagramPoster._is_permalink(url):
        print("WARN: url chưa phải permalink /p/ hoặc /reel/:", url)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
