import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
import os
import json

from automation.browser_engine import browser_engine

SHOT = os.path.join(os.path.dirname(__file__), "debug_screenshots")
os.makedirs(SHOT, exist_ok=True)


async def shot(page, name):
    path = os.path.join(SHOT, f"{name}.png")
    await page.screenshot(path=path, full_page=False)
    print("SHOT", path)


async def dump_schedule_controls(page, label):
    data = await page.evaluate(
        """() => {
            const keys = ['lên lịch', 'schedule', 'chia sẻ ngay', 'share now', 'đăng', 'post', 'share'];
            const els = Array.from(document.querySelectorAll(
                'button, [role="button"], [role="menuitem"], [role="switch"], input, label, span, div[aria-label]'
            ));
            const hits = [];
            for (const el of els) {
                const aria = (el.getAttribute('aria-label') || '').trim();
                const text = (el.innerText || '').trim().slice(0, 80);
                const blob = (text + ' ' + aria).toLowerCase();
                if (!keys.some(k => blob.includes(k))) continue;
                if (!text && !aria) continue;
                hits.push({
                    tag: el.tagName,
                    role: el.getAttribute('role') || '',
                    aria,
                    text,
                    type: el.getAttribute('type') || ''
                });
                if (hits.length >= 40) break;
            }
            return { url: location.href, title: document.title, hits, body: (document.body.innerText || '').slice(0, 1800) };
        }"""
    )
    print("\n====", label, "====")
    print("URL", data.get("url"))
    print("HITS:")
    for h in data.get("hits") or []:
        print(" ", h)
    print("--- body ---")
    print((data.get("body") or "")[:1200])
    return data


async def inspect_facebook(page):
    print("\n##### FACEBOOK FEED COMPOSER #####")
    await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)
    await page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('div[role="button"], button'));
        const hit = btns.find(b => {
            const t = (b.innerText || '').trim().toLowerCase();
            return t === 'lúc khác' || t === 'not now';
        });
        if (hit) hit.click();
    }""")
    await asyncio.sleep(1)
    composer = page.locator(
        'div[role="button"]:has-text("Ảnh/video"), div[role="button"]:has-text("Photo/video"), '
        'div[role="button"]:has-text("Bạn đang nghĩ gì"), div[role="button"]:has-text("What\'s on your mind")'
    ).first
    if await composer.is_visible(timeout=8000):
        await composer.click(force=True)
        await asyncio.sleep(2.5)
    await dump_schedule_controls(page, "FB composer empty")
    await shot(page, "sched_fb_composer")

    # Click chevron / more next to Post
    more = await page.evaluate("""() => {
        const dialogs = document.querySelectorAll('div[role="dialog"]');
        const d = dialogs[dialogs.length - 1];
        if (!d) return '';
        const all = Array.from(d.querySelectorAll('[aria-haspopup], div[role="button"], [aria-label]'));
        const chev = all.find(b => {
            const a = (b.getAttribute('aria-label') || '').toLowerCase();
            const t = (b.innerText || '').toLowerCase();
            return a.includes('more') || a.includes('tùy chọn') || a.includes('menu') || t.includes('▼');
        });
        if (chev) { chev.click(); return chev.getAttribute('aria-label') || chev.innerText || 'chevron'; }
        return '';
    }""")
    print("Clicked more/chevron:", more)
    await asyncio.sleep(1.5)
    await dump_schedule_controls(page, "FB after more menu")
    await shot(page, "sched_fb_more")

    print("\n##### FACEBOOK REELS CREATE #####")
    await page.goto("https://www.facebook.com/reels/create", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)
    await dump_schedule_controls(page, "FB reels create")
    await shot(page, "sched_fb_reels")

    print("\n##### META BUSINESS SUITE COMPOSER #####")
    await page.goto("https://business.facebook.com/latest/composer", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(5)
    await dump_schedule_controls(page, "Meta Business Suite")
    await shot(page, "sched_meta_suite")


async def inspect_tiktok(page):
    print("\n##### TIKTOK STUDIO UPLOAD #####")
    await page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)
    await page.evaluate("""() => {
        const b = Array.from(document.querySelectorAll('button')).find(x => (x.innerText||'').includes('Discard'));
        if (b) b.click();
    }""")
    await asyncio.sleep(1)
    await dump_schedule_controls(page, "TikTok upload (no file)")
    await shot(page, "sched_tt_upload")


async def inspect_instagram(page):
    print("\n##### INSTAGRAM HOME / CREATE #####")
    await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(4)
    await page.evaluate("""() => {
        const svg = document.querySelector('svg[aria-label="New post"], svg[aria-label="Bài viết mới"], svg[aria-label="Tạo"]');
        if (svg) {
            const btn = svg.closest('a, div[role="button"], button') || svg;
            btn.click();
        }
    }""")
    await asyncio.sleep(2)
    await dump_schedule_controls(page, "IG create menu")
    await shot(page, "sched_ig_create")


async def inspect_youtube(page):
    print("\n##### YOUTUBE STUDIO #####")
    await page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(3)
    print("URL", page.url)
    await shot(page, "sched_yt_studio")


async def main():
    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)
    await inspect_facebook(page)
    await inspect_tiktok(page)
    await inspect_instagram(page)
    await inspect_youtube(page)
    await asyncio.sleep(2)
    await browser_engine.close()


if __name__ == "__main__":
    asyncio.run(main())
