import argparse
import asyncio
import re
import sys
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from automation.browser_engine import browser_engine
from automation.posters.facebook_poster import FB_LIBRARY_SCHEDULED, facebook_poster
from automation.posters.tiktok_poster import TT_CONTENT, tiktok_poster
from automation.posters.youtube_poster import youtube_poster
from core.config_manager import config_mgr
from core.database import db


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _best_title_match(rows, title: str):
    wanted = _fold(title).replace(" shorts", "").strip()
    if not wanted:
        return None
    best = None
    best_score = 0
    wanted_words = set(wanted.split())
    for row in rows:
        candidate = _fold(row.get("title", "")).replace(" shorts", "").strip()
        if not candidate:
            continue
        candidate_words = set(candidate.split())
        score = len(wanted_words & candidate_words)
        if candidate.startswith(wanted[:24]) or wanted.startswith(candidate[:24]):
            score += 20
        if score > best_score:
            best = row
            best_score = score
    return best if best_score >= 4 else None


async def _repair_youtube(page, video) -> str:
    await page.goto(
        "https://studio.youtube.com/?approve_browser_access=true",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    await asyncio.sleep(4)
    if not await youtube_poster._is_studio_logged_in(page):
        return ""
    channel_match = re.search(r"(https://studio\.youtube\.com/channel/[^/?#]+)", page.url)
    if channel_match:
        target = channel_match.group(1) + "/videos/short"
    else:
        target = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const hit = links.find(a => /\/channel\/[^/]+\/videos/.test(a.href || ''));
            return (hit && hit.href) || '';
        }""")
    if not target:
        print(f"YouTube Studio chưa trả URL kênh (url={page.url})")
        return ""
    print(f"Mở danh sách Shorts: {target}")
    await page.goto(target, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(8)
    rows = await page.evaluate("""() => Array.from(document.querySelectorAll('ytcp-video-row')).map(row => {
        const title = row.querySelector('#video-title');
        const link = row.querySelector('a#video-title[href], a[href*="/video/"][href*="/edit"]');
        return { title: (title?.innerText || title?.textContent || '').trim(), href: link?.href || '' };
    }).filter(x => x.title && x.href)""")
    if not rows:
        debug = await page.evaluate("""() => ({
            url: location.href,
            body: (document.body.innerText || '').slice(0, 2200),
            links: Array.from(document.querySelectorAll('a[href*="/video/"]')).slice(0, 20).map(a => ({
                text: (a.innerText || a.textContent || '').trim().slice(0, 160),
                href: a.href || ''
            }))
        })""")
        print("YouTube debug URL:", debug.get("url", ""))
        print("YouTube debug body:", debug.get("body", ""))
        print("YouTube debug links:", debug.get("links", []))
    match = _best_title_match(rows, video.get("suggested_title") or video.get("title") or "")
    if not match:
        print("Các tiêu đề Shorts đang thấy:")
        for row in rows[:12]:
            print(" -", row.get("title", ""), row.get("href", ""))
        return ""
    video_id_match = re.search(r"/video/([A-Za-z0-9_-]{8,15})", match.get("href", ""))
    return f"https://youtube.com/shorts/{video_id_match.group(1)}" if video_id_match else ""


async def _repair_tiktok(page, video) -> str:
    await page.goto(TT_CONTENT, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)
    caption = tiktok_poster.format_caption(video)
    return await tiktok_poster._copy_scheduled_post_link(page, caption)


async def _repair_facebook(page, video) -> str:
    cfg = config_mgr.get("platforms", {}).get("facebook", {})
    if cfg.get("target_type") == "fanpage" and cfg.get("page_url"):
        await facebook_poster._ensure_switched_to_fanpage(page, cfg.get("page_url"))
    await page.goto(FB_LIBRARY_SCHEDULED, wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)
    caption = facebook_poster.format_caption(video)
    return await facebook_poster._copy_scheduled_post_link(page, caption)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Khôi phục permalink chính xác cho lịch sử đăng")
    parser.add_argument("--video-id", type=int, required=True)
    parser.add_argument("--platform", choices=("youtube", "tiktok", "facebook"), required=True)
    args = parser.parse_args()

    video = db.get_video_by_id(args.video_id)
    if not video:
        print(f"Không tìm thấy video #{args.video_id}")
        return 2

    context = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(context)
    try:
        if args.platform == "youtube":
            url = await _repair_youtube(page, video)
            valid = bool(re.match(r"^https://youtube\.com/shorts/[A-Za-z0-9_-]{8,15}$", url or ""))
        elif args.platform == "tiktok":
            url = await _repair_tiktok(page, video)
            valid = tiktok_poster._is_tt_permalink(url)
        else:
            url = await _repair_facebook(page, video)
            valid = facebook_poster._is_fb_permalink(url)

        if not valid:
            print(f"Chưa tìm thấy permalink chính xác cho {args.platform} video #{args.video_id}")
            return 1
        if not db.update_latest_success_post_url(args.video_id, args.platform, url):
            db.record_post(args.video_id, args.platform, "success", post_url=url, error_message="")
        print(f"Đã cập nhật {args.platform} video #{args.video_id}: {url}")
        return 0
    finally:
        await browser_engine.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
