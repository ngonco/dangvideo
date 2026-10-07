"""Bổ sung caption cho bài Instagram đã đăng nếu caption đang thiếu."""

import argparse
import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from automation.browser_engine import browser_engine
from automation.posters.instagram_poster import instagram_poster
from core.database import db


async def _click_exact_text(page, names) -> bool:
    return bool(await page.evaluate("""(names) => {
        const wanted = new Set(names.map(x => x.toLowerCase()));
        const nodes = Array.from(document.querySelectorAll(
            'div[role="dialog"] button, div[role="dialog"] div[role="button"], ' +
            'div[role="dialog"] [role="menuitem"]'
        ));
        const hit = nodes.find(el => {
            const text = (el.innerText || '').trim().toLowerCase();
            const r = el.getBoundingClientRect();
            return r.width > 3 && r.height > 3 && wanted.has(text);
        });
        if (!hit) return false;
        hit.click();
        return true;
    }""", list(names)))


async def _click_done_trusted(page) -> bool:
    """Focus nút Done rồi nhấn Enter để Instagram nhận sự kiện bàn phím thật."""
    focused = await page.evaluate("""() => {
        const nodes = Array.from(document.querySelectorAll('div[role="dialog"] *'));
        const hits = nodes.filter(el => {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            return r.width > 3 && r.height > 3 && (text === 'Done' || text === 'Xong');
        }).sort((a, b) => {
            const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
            return (ar.width * ar.height) - (br.width * br.height);
        });
        const hit = hits[0];
        if (!hit) return false;
        const button = hit.closest('button, div[role="button"]') || hit;
        button.focus();
        return true;
    }""")
    if not focused:
        return False
    await asyncio.wait_for(page.keyboard.press("Enter"), timeout=5)
    return True


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", type=int, required=True)
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()

    video = db.get_video_by_id(args.video_id)
    rows = db.get_post_history(args.video_id, limit=100)
    post = next(
        (x for x in rows if x.get("platform") == "instagram" and x.get("status") == "success"),
        None,
    )
    if not post:
        task = db.get_posting_task(args.video_id, 'instagram')
        if task and task.get('submitted_at') and task.get('post_url'):
            post = task
    if not video or not post or not instagram_poster._is_permalink(post.get("post_url", "")):
        print("Không tìm thấy video hoặc permalink Instagram thành công.")
        return 2

    url = post["post_url"]
    caption = instagram_poster.format_caption(video)
    from automation.posting_verifier import normalized
    marker = normalized(caption)
    context = await browser_engine.get_context(headless=args.headless)
    page = await browser_engine.get_page(context)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(6)
        body = await page.locator("body").inner_text(timeout=10000)
        if marker and marker in normalized(body):
            print("CAPTION_ALREADY_PRESENT")
            return 0

        opened = await page.evaluate("""() => {
            const labels = ['More options', 'Tùy chọn khác', 'Thêm tùy chọn'];
            const nodes = Array.from(document.querySelectorAll('[aria-label], svg[aria-label]'));
            const hit = nodes.find(el => labels.includes((el.getAttribute('aria-label') || '').trim()));
            if (!hit) return false;
            (hit.closest('button, div[role="button"]') || hit).click();
            return true;
        }""")
        if not opened:
            await instagram_poster._shot(page, "ig_caption_repair_menu_missing")
            print("Không thấy nút More options của bài Instagram.")
            return 1
        await asyncio.sleep(2)
        if not await _click_exact_text(page, ("Edit", "Chỉnh sửa")):
            await instagram_poster._shot(page, "ig_caption_repair_edit_missing")
            print("Không thấy mục Edit trong menu bài Instagram.")
            return 1
        await asyncio.sleep(3)

        box = page.locator(
            'div[role="dialog"] [contenteditable="true"][role="textbox"]:visible, '
            'div[role="dialog"] textarea:visible, '
            'div[role="dialog"] [contenteditable="true"]:visible'
        ).first
        await box.wait_for(state="visible", timeout=15000)
        await box.evaluate("""el => {
            el.focus();
            const range = document.createRange();
            range.selectNodeContents(el);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
        }""")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(caption, delay=8)
        await asyncio.sleep(1)
        actual = await box.evaluate("el => (el.value || el.innerText || el.textContent || '').trim()")
        if normalized(caption) != normalized(actual):
            await instagram_poster._shot(page, "ig_caption_repair_fill_failed")
            print("Ô Edit chưa nhận caption; không bấm Done.")
            return 1
        await instagram_poster._shot(page, "ig_caption_repair_before_save")
        if not await _click_done_trusted(page):
            await instagram_poster._shot(page, "ig_caption_repair_done_missing")
            print("Đã điền caption nhưng không thấy Done; chưa lưu thay đổi.")
            return 1
        for _ in range(30):
            await asyncio.sleep(1)
            editing = await page.get_by_text("Edit info", exact=True).is_visible(timeout=300)
            editing = editing or await page.get_by_text("Chỉnh sửa thông tin", exact=True).is_visible(timeout=300)
            if not editing:
                break
        else:
            await instagram_poster._shot(page, "ig_caption_repair_save_stuck")
            print("CAPTION_SAVE_DIALOG_STUCK")
            return 1

        verify_page = await context.new_page()
        await verify_page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(6)
        await instagram_poster._shot(verify_page, "ig_caption_repaired")
        verified_body = await verify_page.locator("body").inner_text(timeout=15000)
        if marker and marker not in normalized(verified_body):
            print("CAPTION_SAVE_NOT_VERIFIED")
            return 1
        print(f"CAPTION_REPAIRED {url}")
        return 0
    finally:
        await browser_engine.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
