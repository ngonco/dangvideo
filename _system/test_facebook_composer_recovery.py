"""Regression fixtures from the October 8 Facebook page composer."""
import asyncio, pathlib, tempfile, unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch
from automation.browser_engine import browser_engine
from automation.posters.facebook_poster import FacebookPoster
from automation.posting_verifier import facebook_publication_time,verify_delivery,normalized
from core.posting_store import VIETNAM


class PublicationDateTests(unittest.TestCase):
    task={'scheduled_for':'2026-10-07 20:00:00','submitted_at':'2026-10-07 14:42:41'}

    def test_real_yesterday_label_and_vietnamese_equivalent(self):
        for label in ('Published • Yesterday at 20:01','Đã đăng • Hôm qua lúc 20:01'):
            result=facebook_publication_time(label,self.task,datetime(2026,10,8,6,tzinfo=VIETNAM))
            self.assertEqual(result,datetime(2026,10,7,20,1,tzinfo=VIETNAM))

    def test_today_and_year_boundary_use_vietnam_day(self):
        now=datetime(2027,1,1,0,10,tzinfo=VIETNAM)
        self.assertEqual(facebook_publication_time('Published • Yesterday at 20:00',self.task,now),datetime(2026,12,31,20,tzinfo=VIETNAM))
        self.assertEqual(facebook_publication_time('Đã đăng • Hôm nay lúc 00:05',self.task,now),datetime(2027,1,1,0,5,tzinfo=VIETNAM))

    def test_absolute_date_still_supported_unknown_label_stays_unverified(self):
        self.assertEqual(facebook_publication_time('Published • 7 Oct at 20:01',self.task),datetime(2026,10,7,20,1,tzinfo=VIETNAM))
        for label in ('Scheduled • Yesterday at 20:00','Published • Yesterday at 25:90','Published • Some other date'):
            self.assertIsNone(facebook_publication_time(label,self.task))


class ComposerRecoveryFixtures(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.page=await browser_engine.get_page(await browser_engine.get_context(headless=True))
        self.poster=FacebookPoster()
        await self.page.route('https://www.facebook.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body='<body></body>'))
        await self.page.goto('https://www.facebook.com/test-fixture')

    async def asyncTearDown(self):
        await self.page.close();await browser_engine.close()

    async def test_delayed_navigation_detects_page_instead_of_waiting_for_old_dialog(self):
        await self.page.set_content('''<div id="content">Loading</div><script>setTimeout(()=>{
          history.pushState({},'', '/reels/create');
          document.getElementById('content').innerHTML='<div contenteditable="true" role="textbox" aria-placeholder="What is on your mind?"></div>';
        },400)</script>''')
        self.assertEqual(await asyncio.wait_for(self.poster._wait_reel_composer(self.page),timeout=4),'page')

    async def test_bilingual_dialogs_and_caption_ignore_hidden_popup(self):
        for label in ('Create reel','Tạo thước phim'):
            await self.page.set_content(f'<div role="dialog" style="display:none">{label}</div><div role="dialog">{label}<input type="file"></div>')
            self.assertEqual(await self.poster._wait_reel_composer(self.page),'dialog')
        for label in ("What's on your mind, Page?",'Bạn đang nghĩ gì, Trang?','Describe your reel','Mô tả thước phim'):
            await self.page.set_content(f'''<div class="react-joyride" style="display:none"><div contenteditable="true" role="textbox">Hidden old caption</div></div>
              <div contenteditable="true" role="textbox" aria-placeholder="{label}"></div>''')
            caption='Bài học cuộc sống\n#baihoccuocsong #nhanquabaoung'
            self.assertTrue(await self.poster._fill_page_reel_caption(self.page,caption))
            self.assertEqual(normalized(await self.page.locator('[contenteditable]:visible').inner_text()),normalized(caption))
            self.assertEqual(await self.page.locator('.react-joyride [contenteditable]').inner_text(),'Hidden old caption')
        await self.page.set_content('<div contenteditable="true" role="textbox">One</div><div contenteditable="true" role="textbox">Two</div>')
        self.assertFalse(await self.poster._fill_page_reel_caption(self.page,'Never fill another editor'))

    async def test_lost_chooser_reattaches_once_and_does_not_replace_existing_preview(self):
        with tempfile.TemporaryDirectory() as temp:
            media=pathlib.Path(temp)/'fixture.mp4';media.write_bytes(b'fixture')
            await self.page.set_content('''<video src="blob:old" style="display:none"></video>
                <div role="button">Add video<br>or drag and drop</div>
                <input type="file" accept="video/*" onchange="document.body.dataset.changes=String(Number(document.body.dataset.changes||0)+1)">''')
            self.assertTrue(await self.poster._attach_page_reel_media(self.page,str(media)))
            self.assertTrue(await self.poster._attach_page_reel_media(self.page,str(media)))
            self.assertEqual(await self.page.evaluate('document.body.dataset.changes'),'1')
            await self.page.set_content('''<video style="width:300px;height:200px" src="blob:existing"></video><div role="button">Thêm video</div>
                <input type="file" accept="video/*" onchange="document.body.dataset.changed='true'">''')
            self.assertTrue(await self.poster._attach_page_reel_media(self.page,str(media)))
            self.assertIsNone(await self.page.evaluate('document.body.dataset.changed'))
            await self.page.set_content('<div role="button">Add video</div><input type="file" accept="video/*"><input type="file" accept="video/*">')
            self.assertFalse(await self.poster._attach_page_reel_media(self.page,str(media)))

    async def test_published_relative_label_verifies_saved_post_but_rejects_stale_date(self):
        page_caption='Correct title #test'
        async def navigate(url,**kwargs):
            text='<div>Other post</div>' if 'SCHEDULED' in url else f'<div>{page_caption} Published • Yesterday at 20:01</div>'
            await self.page.set_content(text)
        task={'state':'scheduled','submitted_at':'2026-10-07 14:42:41','scheduled_for':'2026-10-07 20:00:00','post_url':'https://www.facebook.com/share/v/SAVED/'}
        with patch.object(self.page,'goto',AsyncMock(side_effect=navigate)),patch.object(self.poster,'_dismiss_fb_popups',AsyncMock()),patch('automation.posting_verifier.asyncio.sleep',AsyncMock()),patch('core.posting_store.local_now',return_value=datetime(2026,10,8,6,tzinfo=VIETNAM)):
            result=await verify_delivery(self.page,self.poster,'facebook',{'title':'Correct title','hashtags':'#test'},task)
            self.assertTrue(result['verified']);self.assertEqual(result['state'],'published');self.assertEqual(result['url'],task['post_url'])
            page_caption='Correct title #other'
            result=await verify_delivery(self.page,self.poster,'facebook',{'title':'Correct title','hashtags':'#test'},task)
            self.assertFalse(result['verified'])
            page_caption='Correct title #test'
            task['submitted_at']='2026-10-08 05:00:00'
            result=await verify_delivery(self.page,self.poster,'facebook',{'title':'Correct title','hashtags':'#test'},task)
            self.assertFalse(result['verified'])


if __name__=='__main__':unittest.main()
