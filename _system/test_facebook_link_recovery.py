"""Facebook link recovery fixtures; no external posts or clipboard writes."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from automation.browser_engine import browser_engine
from automation.posters.facebook_poster import FacebookPoster
from automation.posting_verifier import matching_library_row


class FacebookLinkRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.page=await browser_engine.get_page(await browser_engine.get_context(headless=True))
        self.poster=FacebookPoster()

    async def asyncTearDown(self):
        await self.page.close()
        await browser_engine.close()

    async def test_bilingual_copy_returns_new_video_share_link_within_verifier_budget(self):
        for label,status,role in (('Copy link','Scheduled','menuitem'),('Sao chép liên kết','Đã lên lịch','none')):
            await self.page.set_content(f'''
              <div role="dialog" class="react-joyride"><button onclick="this.parentElement.remove()">Not now</button></div>
              <div style="display:none">Correct title #test {status} • 2026-10-07 20:00 <button>Menu</button></div>
              <div style="width:700px;padding:10px">Correct title #test
                <div><span>{status} • 2026-10-07 20:00</span>
                  <button aria-label="Link to view a post page" onclick="document.body.dataset.wrong='true'">View</button></div>
                <button aria-label="Actions for this post" onclick="document.getElementById('menu').hidden=false">Menu</button></div>
              <div role="{role}" tabindex="0" style="display:none" onclick="document.body.dataset.wrong='true'">{label}</div>
              <div id="menu" role="menu" hidden><div role="{role}" tabindex="0"
                onclick="document.body.dataset.copied='true'"
                onkeydown="if(event.key==='Enter')document.body.dataset.copied='true'">{label}</div></div>''')
            async def read_clipboard(*args):
                copied=await self.page.evaluate("document.body.dataset.copied==='true'")
                return 'https://www.facebook.com/share/v/NEW/?mibextid=tracking' if copied else 'https://www.facebook.com/share/r/OLD/'
            with patch.object(self.page,'goto',AsyncMock()),patch.object(self.poster,'_read_fb_clipboard',side_effect=read_clipboard),patch('core.clipboard.windows_clipboard_sequence',return_value=0):
                url=await asyncio.wait_for(self.poster._copy_scheduled_post_link(self.page,'Correct title\n#test',scheduled_for='2026-10-07 20:00:00'),timeout=15)
            self.assertEqual(url,'https://www.facebook.com/share/v/NEW/')
            self.assertIsNone(await self.page.evaluate('document.body.dataset.wrong'))
            self.assertEqual(await self.page.locator('div.react-joyride').count(),0)

    async def test_dom_links_ignore_notifications_hidden_rows_and_partial_titles(self):
        await self.page.set_content('''
          <aside><a href="https://www.facebook.com/share/v/NOTIFICATION/">Correct title #test</a></aside>
          <div style="display:none">Correct title #test Scheduled • 2026-10-07 20:00 <a href="https://www.facebook.com/share/v/HIDDEN/">View</a></div>
          <div>Correct title with other content #other Scheduled • 2026-10-07 20:00 <a href="https://www.facebook.com/share/v/WRONG/">View</a></div>
          <div>Correct title #test Scheduled • 2026-10-07 20:00 <a href="https://www.facebook.com/share/v/RIGHT/">View</a></div>''')
        self.assertEqual(await self.poster._find_fb_permalink_in_loaded_library(self.page,'Correct title\n#test'),'https://www.facebook.com/share/v/RIGHT/')
        row=await matching_library_row(self.page,'Correct title #test','2026-10-07 20:00:00')
        self.assertEqual(row['href'],'https://www.facebook.com/share/v/RIGHT/')

    async def test_ambiguous_rows_do_not_open_menu_or_reuse_clipboard(self):
        await self.page.set_content('''<div>Same title Scheduled • 2026-10-07 20:00 <button onclick="document.body.dataset.changed=true">Menu</button></div>
          <div>Same title Scheduled • 2026-10-08 20:00 <button onclick="document.body.dataset.changed=true">Menu</button></div>''')
        self.assertFalse(await self.poster._open_scheduled_row_menu(self.page,'Same title'))
        self.assertIsNone(await self.page.evaluate('document.body.dataset.changed'))
        with patch.object(self.page,'goto',AsyncMock()),patch.object(self.poster,'_dismiss_fb_popups',AsyncMock()),patch.object(self.poster,'_click_copy_link_item',AsyncMock()) as click,patch('automation.posters.facebook_poster.asyncio.sleep',AsyncMock()):
            self.assertEqual(await self.poster._copy_scheduled_post_link(self.page,'Same title',scheduled_for='2026-10-07 20:00:00'),'')
        click.assert_not_awaited()

    async def test_failed_copy_never_returns_valid_but_stale_clipboard(self):
        await self.page.set_content('''<div>Correct title #test <span>Scheduled • 2026-10-07 20:00</span>
            <button onclick="document.getElementById('menu').hidden=false">Menu</button></div>
            <div id="menu" role="menu" hidden><div role="menuitem" tabindex="0" onkeydown="if(event.key==='Enter')document.body.dataset.attempted='true'">Copy link</div></div>''')
        with patch.object(self.page,'goto',AsyncMock()),patch.object(self.page,'reload',AsyncMock()),patch.object(self.poster,'_dismiss_fb_popups',AsyncMock()),patch.object(self.poster,'_read_fb_clipboard',AsyncMock(return_value='https://www.facebook.com/share/v/OLD/')),patch('core.clipboard.windows_clipboard_sequence',return_value=0),patch('automation.posters.facebook_poster.asyncio.sleep',AsyncMock()):
            self.assertEqual(await self.poster._copy_scheduled_post_link(self.page,'Correct title\n#test',scheduled_for='2026-10-07 20:00:00'),'')
        self.assertEqual(await self.page.evaluate('document.body.dataset.attempted'),'true')

    async def test_delayed_published_row_recovers_from_correct_library(self):
        await self.page.set_content('''<div id="list">Loading</div><script>
          setTimeout(()=>document.getElementById('list').innerHTML='<div>Correct title #test Published • 7 Oct at 20:00 <a href="https://www.facebook.com/share/v/PUBLISHED/">View</a></div>',500);
          </script>''')
        with patch.object(self.page,'goto',AsyncMock()) as goto:
            url=await asyncio.wait_for(self.poster._copy_scheduled_post_link(self.page,'Correct title\n#test',published=True,scheduled_for='2026-10-07 20:00:00'),timeout=8)
        self.assertEqual(url,'https://www.facebook.com/share/v/PUBLISHED/')
        self.assertIn('filter=PUBLISHED',goto.call_args.args[0])


if __name__=='__main__':unittest.main()
