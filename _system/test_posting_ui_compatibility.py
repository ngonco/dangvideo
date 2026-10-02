"""Browser regression tests with local fixtures; never publish external posts."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from automation.browser_engine import browser_engine
from automation.posters.facebook_poster import FacebookPoster
from automation.posters.youtube_poster import YouTubePoster


class FacebookClipboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_headless_browser_link_takes_precedence_over_stale_os_link(self):
        poster = FacebookPoster()
        page = SimpleNamespace(evaluate=AsyncMock(return_value='https://www.facebook.com/share/r/NEW/'))
        with patch.object(poster, '_read_os_clipboard', return_value='https://www.facebook.com/share/r/OLD/'):
            self.assertEqual(await poster._read_fb_clipboard(page), 'https://www.facebook.com/share/r/NEW/')

    async def test_os_clipboard_fallback_when_browser_read_is_unavailable(self):
        poster = FacebookPoster()
        page = SimpleNamespace(evaluate=AsyncMock(side_effect=RuntimeError('Clipboard denied')))
        with patch.object(poster, '_read_os_clipboard', return_value='https://www.facebook.com/share/r/OS/'):
            self.assertEqual(await poster._read_fb_clipboard(page), 'https://www.facebook.com/share/r/OS/')


class PostingUICompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_visible_bilingual_reel_menu_and_contents_upload_host(self):
        ctx = await browser_engine.get_context(headless=True)
        page = await browser_engine.get_page(ctx)
        try:
            poster = FacebookPoster()
            for label in ('Reel', 'Thước phim'):
                await page.set_content(f'''
                    <span onclick="document.body.dataset.wrong='true'">Reels</span>
                    <div role="menu" style="display:none"><div role="menuitem">{label}</div></div>
                    <button id="create_post_global" onclick="document.getElementById('prodash_create_menu_items').hidden=false">Create a post</button>
                    <div role="menu" id="prodash_create_menu_items" hidden>
                      <div role="menuitem" onclick="document.body.dataset.wrong='true'">Bulk upload reels</div>
                      <div role="menuitem" onclick="document.body.dataset.right='true'">{label}</div>
                    </div>''')
                await page.evaluate("document.body.dataset.right='false'; document.body.dataset.wrong='false'")
                self.assertTrue(await poster._click_create_reel(page))
                self.assertTrue(await page.evaluate("document.body.dataset.right === 'true'"))
                self.assertFalse(await page.evaluate("document.body.dataset.wrong === 'true'"))

            await page.set_content('''<button id="create_post_global">Create a post</button>
                <span onclick="document.body.dataset.wrong='true'">Reels</span>''')
            await page.evaluate("document.body.dataset.wrong='false'")
            self.assertFalse(await poster._click_create_reel(page))
            self.assertFalse(await page.evaluate("document.body.dataset.wrong === 'true'"))

            await page.set_content('''
                <div style="width:600px;padding:20px"><span>Older video</span>
                  <span>Scheduled • Tomorrow at 10:00</span>
                  <button onclick="document.body.dataset.wrong='true'">Menu</button></div>
                <div style="width:600px;padding:20px"><span>Target video</span>
                  <span>Scheduled • Tomorrow at 10:00</span>
                  <button onclick="document.body.dataset.right='true'">Menu</button></div>''')
            await page.evaluate("document.body.dataset.right='false'; document.body.dataset.wrong='false'")
            self.assertTrue(await poster._open_scheduled_row_menu(page, 'Target video\n#test'))
            self.assertTrue(await page.evaluate("document.body.dataset.right === 'true'"))
            self.assertFalse(await page.evaluate("document.body.dataset.wrong === 'true'"))

            await page.set_content('''<div role="menu" style="position:absolute;left:300px;top:300px;width:200px"><div role="menuitem" tabindex="0"
                onclick="document.body.dataset.copied=event.isTrusted">Copy link</div></div>''')
            self.assertTrue(await asyncio.wait_for(poster._click_copy_link_item(page), timeout=15))
            self.assertTrue(await page.evaluate("document.body.dataset.copied === 'true'"))

            # Modern Studio's display:contents host has no own bounding box.
            await page.set_content('''
                <ytcp-uploads-dialog style="display:contents">
                  <div role="dialog"><a id="video-url" href="https://youtube.com/shorts/0SoqzO-FzKo">video</a></div>
                </ytcp-uploads-dialog>
                <a href="https://youtube.com/shorts/OLDVIDEO123">old page link</a>''')
            yt = YouTubePoster()
            self.assertEqual(await yt._extract_youtube_url(page), 'https://youtube.com/shorts/0SoqzO-FzKo')
            await page.locator('ytcp-uploads-dialog').evaluate('el => el.style.display="none"')
            self.assertEqual(await yt._extract_youtube_url(page), '')
        finally:
            await page.close()
            await browser_engine.close()


if __name__ == '__main__':
    unittest.main()
