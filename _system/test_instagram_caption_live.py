"""Kiểm tra live ô caption Instagram nhưng tuyệt đối không bấm Share."""

import argparse
import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from automation.browser_engine import browser_engine
from automation.posters.instagram_poster import IG_HOME, instagram_poster
from core.database import db


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", type=int, required=True)
    args = parser.parse_args()
    video = db.get_video_by_id(args.video_id)
    if not video:
        print(f"Không tìm thấy video #{args.video_id}")
        return 2

    context = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(context)
    try:
        await page.goto(IG_HOME, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        await instagram_poster._dismiss_ig_dialogs(page)
        if not await instagram_poster._wait_login(page):
            print("Instagram chưa đăng nhập")
            return 1
        if not await instagram_poster._open_new_post(page):
            print("Không mở được New post")
            return 1
        await instagram_poster._choose_post_type(page)
        await asyncio.sleep(1)
        if not await instagram_poster._attach_file(page, video.get("file_path", "")):
            print("Không đính kèm được video")
            return 1
        await asyncio.sleep(2)
        if not await instagram_poster._click_next_twice(page):
            print("Không tới được bước caption")
            return 1
        caption = instagram_poster.format_caption(video)
        ok = await instagram_poster._fill_caption(page, caption)
        await instagram_poster._shot(page, "ig_caption_live_test")
        print("CAPTION_OK" if ok else "CAPTION_FAILED")
        print("Không bấm Share; đóng bản nháp kiểm tra.")
        return 0 if ok else 1
    finally:
        await browser_engine.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
