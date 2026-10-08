"""Real Camoufox fixtures; no external posts or authenticated content."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch
from automation.browser_engine import browser_engine
from automation.hatbuinho_crawler import HatBuiNhoCrawler
from automation.posters.tiktok_poster import TikTokPoster
from automation.posting_verifier import matching_library_row, normalized


class SourceUIFixtures(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ctx=await browser_engine.get_context(headless=True)
        self.page=await self.ctx.new_page()

    async def asyncTearDown(self):
        await self.page.close()
        await browser_engine.close()

    def body(self, items):
        return '<button id="history_tab_done" class="history-tab-btn--active">Đã xong</button><div id="history_list_done">'+items+'</div>'

    async def test_visible_done_scope_bilingual_deleted_hidden(self):
        await self.page.set_content(self.body('''
            <details class="history-order"><summary><span>🗑️ Video đã xoá</span><div class="history-script-body">Kịch bản mẫu</div></summary></details>
            <details class="history-order"><summary><span>Not downloaded</span></summary></details>
            <details class="history-order"><summary><span style="display:none">Chưa tải xuống</span><span>Unknown state</span></summary></details>
            <details class="history-order" style="display:none"><summary><span>Chưa tải xuống</span></summary></details>
            ''')+'''<div style="display:none"><details class="history-order"><summary><span>Chưa tải xuống</span></summary></details></div>''')
        self.assertEqual(await HatBuiNhoCrawler()._read_source_states(self.page),['deleted','pending','unknown'])

    async def test_waits_for_slow_list_and_loads_more(self):
        await self.page.set_content(self.body('')+'''<button id="more">Load more</button>
          <script>setTimeout(()=>document.querySelector('#history_list_done').innerHTML='<details class="history-order"><summary><span>Chưa tải xuống</span></summary></details>',500)</script>''')
        await self.page.evaluate('''() => { document.getElementById('more').onclick=function(){
            document.getElementById('history_list_done').insertAdjacentHTML('beforeend','<details class="history-order"><summary><span>Downloaded</span></summary></details>');this.remove();
        }; }''')
        crawler=HatBuiNhoCrawler()
        with patch.object(crawler,'_open_done_video_list',AsyncMock(return_value=True)):
            self.assertEqual(await crawler._prepare_source(self.page),['pending','downloaded'])

    async def test_unknown_reloads_once_and_reports_unreadable(self):
        await self.page.set_content(self.body('<details class="history-order"><summary><span>New unknown label</span></summary></details>'))
        crawler=HatBuiNhoCrawler()
        with patch.object(crawler,'_open_done_video_list',AsyncMock(return_value=True)),patch.object(self.page,'reload',AsyncMock()) as reload,patch.object(crawler,'_source_state',Mock()) as state:
            self.assertEqual(await crawler._prepare_source(self.page),['unknown'])
        reload.assert_awaited_once()
        self.assertEqual(state.call_args.args[0],'unreadable')

    async def test_tiktok_copy_does_not_choose_other_title(self):
        await self.page.set_content('''<div>Unrelated old title Scheduled 20:00<button>View</button><button onclick="document.body.dataset.wrong='yes'">Copy link</button></div>
        <div>Correct unique title Scheduled 20:00<button>View</button><button aria-label="Copy link" onclick="document.body.dataset.correct='yes'">Copy link</button></div>''')
        self.assertTrue((await TikTokPoster()._open_copy_on_scheduled_row(self.page,'Correct unique title\n#test')).startswith('ok:'))
        self.assertEqual(await self.page.evaluate('document.body.dataset.correct'),'yes')
        self.assertIsNone(await self.page.evaluate('document.body.dataset.wrong'))

    async def test_caption_preserves_vietnamese_and_hashtags(self):
        await self.page.set_content('<div class="caption-editor"><div contenteditable="true" role="combobox"></div></div><span class="caption-title">Description</span>')
        caption='Bài học cuộc sống\n#baihoccuocsong #nhanquabaoung'
        self.assertTrue(await TikTokPoster()._fill_caption(self.page,caption))
        self.assertEqual(normalized(await self.page.locator('[contenteditable]').inner_text()),normalized(caption))

    async def test_instagram_share_uses_trusted_activation(self):
        from automation.posters.instagram_poster import InstagramPoster
        await self.page.set_content('<div role="dialog"><button onclick="document.body.dataset.shared=event.isTrusted">Share</button></div>')
        self.assertTrue(await InstagramPoster()._click_share(self.page))
        self.assertEqual(await self.page.evaluate('document.body.dataset.shared'),'true')

    async def test_caption_repair_keeps_locked_tiktok_post(self):
        from automation.caption_repair import repair_tiktok_caption
        await self.page.set_content('<div data-tt="components_PostTable_Absolute"><a href="https://www.tiktok.com/@test/video/1234567890123456789">Wrong caption</a><div data-tt="components_ActionCell_Container" cursor="not-allowed" onclick="document.body.dataset.changed=true"><span data-icon="Pen"></span></div></div>')
        with patch.object(self.page,'goto',AsyncMock()),patch('automation.caption_repair.asyncio.sleep',AsyncMock()):
            self.assertFalse(await repair_tiktok_caption(self.page,TikTokPoster(),{'title':'Correct caption'},{'submitted_at':'2026-10-07 15:00:00','post_url':'https://www.tiktok.com/@test/video/1234567890123456789'}))
        self.assertIsNone(await self.page.evaluate('document.body.dataset.changed'))

    async def test_wrong_schedule_or_ambiguous_title_is_not_verified(self):
        await self.page.set_content('<div>Correct unique title Scheduled 2026-10-07 18:00</div>')
        self.assertIsNone(await matching_library_row(self.page,'Correct unique title','2026-10-07 20:00:00'))
        await self.page.set_content('<div>Correct unique title Scheduled 2026-10-07 20:00</div><div>Correct unique title Scheduled 2026-10-07 20:00</div>')
        self.assertIsNone(await matching_library_row(self.page,'Correct unique title','2026-10-07 20:00:00'))

    async def test_real_tiktok_scheduled_alarm_label(self):
        await self.page.set_content('<div><a href="https://www.tiktok.com/@test/video/123">Bài học cuộc sống #test</a><div data-tt="components_PublishStageLabel_FlexCenter"><span data-icon="Alarm"></span>Oct 7, 8:00\u202fPM</div></div>')
        row=await matching_library_row(self.page,'Bài học cuộc sống','2026-10-07 20:00:00')
        self.assertEqual(row['state'],'scheduled')
        self.assertTrue(row['href'].endswith('/123'))

    async def test_facebook_moves_to_published_with_matching_date(self):
        from automation.posters.facebook_poster import FacebookPoster
        from automation.posting_verifier import verify_delivery
        from datetime import datetime
        async def navigate(url,**kwargs):
            content='<div>Unrelated old title Published • 4 Oct at 20:00</div>' if 'SCHEDULED' in url else '<div><a href="https://www.facebook.com/reel/1234567890123/">Correct title #test</a>Published • 7 Oct at 20:00</div>'
            await self.page.set_content(content)
        poster=FacebookPoster()
        with patch.object(self.page,'goto',AsyncMock(side_effect=navigate)),patch.object(poster,'_dismiss_fb_popups',AsyncMock()),patch('automation.posting_verifier.asyncio.sleep',AsyncMock()),patch('core.posting_store.local_now',return_value=datetime(2026,10,7,21)):
            result=await verify_delivery(self.page,poster,'facebook',{'title':'Correct title','hashtags':'#test'},{'state':'scheduled','submitted_at':'2026-10-07 15:00:00','scheduled_for':'2026-10-07 20:00:00'})
        self.assertTrue(result['verified'])
        self.assertEqual(result['state'],'published')
        self.assertTrue(result['url'].endswith('/1234567890123/'))

if __name__=='__main__':unittest.main()
