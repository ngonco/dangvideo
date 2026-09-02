import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import asyncio
import os

from automation.browser_engine import browser_engine
from automation.hatbuinho_crawler import hatbuinho_crawler

SHOT_DIR = os.path.join(os.path.dirname(__file__), "debug_screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)


async def shot(page, name: str):
    path = os.path.join(SHOT_DIR, f"{name}.png")
    await page.screenshot(path=path, full_page=False)
    print(f"[SHOT] {path}")


async def inspect_version_tabs(page):
    total = await page.locator("details.history-order").count()
    print(f"\n=== KIỂM TRA TAB PHIÊN BẢN ({total} mục) ===")
    multi_idx = []
    scan_n = min(total, 8)
    for idx in range(scan_n):
        item = page.locator("details.history-order").nth(idx)
        await item.scroll_into_view_if_needed()
        await item.evaluate("el => { el.open = true; }")
        await asyncio.sleep(0.4)
        info = await item.evaluate(
            """el => {
                const tabs = Array.from(el.querySelectorAll('button.history-variant-tab'));
                return {
                    open: !!el.open,
                    tabs: tabs.map(t => ({
                        id: t.id,
                        text: (t.textContent || '').replace(/\\s+/g, ' ').trim(),
                        cls: t.className,
                    })),
                    panels: Array.from(el.querySelectorAll('.hist-ver-panel')).map(p => ({
                        id: p.id,
                        hidden: p.classList.contains('hidden'),
                    })),
                };
            }"""
        )
        summary = (await item.locator("summary").first.inner_text())[:80].replace("\n", " ")
        n_tabs = len(info.get("tabs") or [])
        print(f"  #{idx+1} tabs={n_tabs} | {summary}")
        for t in info.get("tabs") or []:
            print(f"      - {t.get('id')} | {t.get('text')} | {t.get('cls')}")
        if n_tabs > 1:
            multi_idx.append(idx)
    return multi_idx


async def main():
    print("=" * 60)
    print("  TEST: click phiên bản cao nhất trên HatBuiNho")
    print("=" * 60)

    ctx = await browser_engine.get_context(headless=False)
    page = await browser_engine.get_page(ctx)

    logged_in = await hatbuinho_crawler.login_if_needed(page)
    if not logged_in:
        print("FAIL: không đăng nhập được HatBuiNho")
        await browser_engine.close()
        return

    opened = await hatbuinho_crawler._open_done_video_list(page)
    if not opened:
        print("FAIL: không mở được danh sách video")
        await browser_engine.close()
        return

    await shot(page, "hbn_01_list")
    multi_idx = await inspect_version_tabs(page)
    print(f"\nVideo có từ 2 phiên bản: {[i+1 for i in multi_idx] or 'không thấy trong 8 mục đầu'}")

    target_idx = multi_idx[0] if multi_idx else 0
    item = page.locator("details.history-order").nth(target_idx)
    print(f"\n>>> Click phiên bản cao nhất trên mục #{target_idx+1} (chưa bấm xác nhận tải)...")
    version_n = await hatbuinho_crawler._select_highest_version_and_open_download(item)
    await asyncio.sleep(1.2)
    await shot(page, "hbn_02_after_highest_tab_and_download_btn")
    print(f">>> Hàm chọn phiên bản trả về: {version_n}")

    active = await item.evaluate(
        """el => {
            const tabs = Array.from(el.querySelectorAll('button.history-variant-tab'));
            const activeTab = tabs.find(t => t.classList.contains('history-variant-tab--active'));
            const vis = Array.from(el.querySelectorAll('.hist-ver-panel')).find(p => !p.classList.contains('hidden'));
            return {
                activeText: activeTab ? (activeTab.textContent || '').trim() : '',
                activeId: activeTab ? activeTab.id : '',
                visiblePanel: vis ? vis.id : '',
            };
        }"""
    )
    print(f">>> Tab đang active: {active}")

    modal = page.locator("#download_reminder_modal").first
    try:
        await modal.wait_for(state="visible", timeout=10000)
        print(">>> Modal tải xuống đã hiện — đóng lại, không lưu file (chỉ test click tab).")
        await page.evaluate(
            """() => {
                const m = document.getElementById('download_reminder_modal');
                if (m) m.classList.add('hidden');
            }"""
        )
    except Exception as ex:
        print(f">>> Modal tải xuống KHÔNG hiện: {ex}")

    await asyncio.sleep(3)
    await browser_engine.close()
    print("\nXONG inspect. Ảnh: _system/debug_screenshots/hbn_01_list.png và hbn_02_after_highest_tab_and_download_btn.png")


if __name__ == "__main__":
    asyncio.run(main())
