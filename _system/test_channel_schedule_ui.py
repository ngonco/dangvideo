"""Real Camoufox with isolated temporary profile and local-only bilingual fixtures."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, Mock
from camoufox.async_api import AsyncCamoufox
from core.browser_runtime import browser_runtime,CAMOUFOX_FIREFOX_MAJOR
from automation.posters.tiktok_poster import TikTokPoster
from automation.posters.facebook_poster import FacebookPoster


class ChannelScheduleUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.manager=AsyncCamoufox(headless=True,persistent_context=True,user_data_dir=self.temp.name,
            executable_path=str(browser_runtime.ensure_ready()),ff_version=CAMOUFOX_FIREFOX_MAJOR,
            i_know_what_im_doing=True,env=browser_runtime.launch_environment(),
            **browser_runtime.launch_addon_options(),os='windows')
        self.ctx=await self.manager.__aenter__()
        self.page=await self.ctx.new_page()

    async def asyncTearDown(self):
        await self.manager.__aexit__(None,None,None)
        self.temp.cleanup()

    async def test_new_date_time_order_never_selects_timezone_and_verifies_both(self):
        for date in ('Oct 26, 2026','26 tháng 10, 2026'):
            await self.page.set_content(f'''<div class="scheduled-picker">
                <button id="date" onclick="document.getElementById('calendar').hidden=false">{date}</button>
                <button id="time" onclick="document.getElementById('wheel').hidden=false">07:30</button>
                <input placeholder="Search" value="(GMT+7) Local Time" onclick="document.body.dataset.wrong='true'">
                </div><div id="wheel" class="tiktok-timepicker" hidden>
                <span class="tiktok-timepicker-option-text tiktok-timepicker-left" onclick="document.getElementById('time').textContent='20:30'">20</span>
                <span class="tiktok-timepicker-option-text tiktok-timepicker-right" onclick="document.getElementById('time').textContent='20:00';document.getElementById('wheel').hidden=true">00</span>
                </div><div id="calendar" hidden><span class="day valid" onclick="document.getElementById('calendar').hidden=true">26</span></div>
                <div class="scheduled-picker" style="display:none"><input value="07:30"></div>
                <div id="react-joyride-portal">Tour</div>''')
            poster=TikTokPoster()
            native={'hour':20,'minute':0,'time':'20:00','year':2026,'month':10,'day':26}
            await poster._dismiss_overlays(self.page)
            self.assertTrue(await poster._configure_schedule_picker(self.page,native))
            self.assertIsNone(await self.page.evaluate('document.body.dataset.wrong'))
            await self.page.locator('#date').evaluate("e=>e.textContent='Oct 27, 2026'")
            self.assertFalse(await poster._picker_shows_date(self.page,native))
            await self.page.locator('#time').evaluate("e=>e.textContent='02:00'")
            self.assertFalse(await poster._picker_shows_time(self.page,native))

    async def test_old_input_layout_still_recognized_and_missing_controls_fail_closed(self):
        await self.page.set_content('<div class="scheduled-picker"><input readonly value="11:30"><input readonly value="2026-10-26"></div>')
        poster=TikTokPoster()
        native={'hour':11,'minute':30,'year':2026,'month':10,'day':26}
        self.assertTrue(await poster._picker_shows_time(self.page,native))
        self.assertTrue(await poster._picker_shows_date(self.page,native))
        await self.page.set_content('<div class="scheduled-picker"><input value="(GMT+7) Local Time"></div>')
        self.assertIsNone(await poster._schedule_control(self.page,'time'))
        self.assertIsNone(await poster._schedule_control(self.page,'date'))

    async def test_modern_picker_sets_date_before_enabling_earlier_hour(self):
        for hour_label,minute_label in (('Hours','Minutes'),('Giờ','Phút')):
            await self.page.set_content(f'''<div class="scheduled-picker">
                <div role="combobox" aria-label="Select date" onclick="document.getElementById('calendar').hidden=false">
                    <span id="date" class="Picker__value">Oct 25, 2026</span></div>
                <div role="combobox" aria-label="Select time" onclick="document.getElementById('timepanel').hidden=false">
                    <span id="time" class="Picker__value">22:35</span></div>
                <input value="(GMT+7) Local Time" onclick="document.body.dataset.wrong='true'"></div>
                <div id="calendar" hidden><button class="DatePicker__titleMonth">October</button>
                    <button class="DatePicker__titleYear">2026</button>
                    <button class="DatePicker__day" data-outside="false" onclick="document.getElementById('date').textContent='Oct 26, 2026';document.getElementById('hour').disabled=false;document.getElementById('calendar').hidden=true">26</button></div>
                <div class="TimePicker__panel" id="timepanel" hidden>
                    <div role="listbox" aria-label="{hour_label}"><button id="hour" role="option" disabled
                        onclick="document.getElementById('time').textContent='20:35'">20</button></div>
                    <div role="listbox" aria-label="{minute_label}"><button role="option"
                        onclick="document.getElementById('time').textContent='20:00'">00</button></div></div>
                <script>document.addEventListener('keydown',e=>{{if(e.key==='Escape'){{
                    document.getElementById('calendar').hidden=true;document.getElementById('timepanel').hidden=true;}}}})</script>''')
            poster=TikTokPoster()
            native={'hour':20,'minute':0,'time':'20:00','year':2026,'month':10,'day':26}
            self.assertTrue(await poster._configure_schedule_picker(self.page,native))
            self.assertEqual(await self.page.locator('#date').inner_text(),'Oct 26, 2026')
            self.assertEqual(await self.page.locator('#time').inner_text(),'20:00')
            self.assertIsNone(await self.page.evaluate('document.body.dataset.wrong'))

    async def test_modern_date_picker_navigates_to_correct_month_before_day(self):
        await self.page.set_content('''<div class="scheduled-picker"><div role="combobox"
            onclick="document.getElementById('calendar').hidden=false"><span id="date">Oct 31, 2026</span></div></div>
            <div id="calendar" hidden><button id="month" class="DatePicker__titleMonth">October</button>
                <button class="DatePicker__titleYear">2026</button><button aria-label="Next month"
                onclick="document.getElementById('month').textContent='November';document.getElementById('day').disabled=false">Next</button>
                <button id="day" class="DatePicker__day" data-outside="false" disabled
                onclick="document.getElementById('date').textContent='Nov 1, 2026';document.getElementById('calendar').hidden=true">1</button></div>''')
        poster=TikTokPoster()
        self.assertTrue(await poster._set_date_picker(self.page,{'year':2026,'month':11,'day':1}))
        self.assertEqual(await self.page.locator('#date').inner_text(),'Nov 1, 2026')

    async def test_facebook_page_edit_next_exposes_settings_in_both_languages(self):
        for next_label,public_label in (('Next','Post audience Public'),('Tiếp','Đối tượng của bài viết Công khai')):
            await self.page.set_content(f'''<button onclick="document.getElementById('settings').hidden=false;this.hidden=true">{next_label}</button>
                <section id="settings" hidden><div role="button">{public_label}</div></section>''')
            self.assertTrue(await FacebookPoster()._ensure_page_reel_settings(self.page))
            self.assertTrue(await FacebookPoster()._ensure_page_reel_settings(self.page))

    async def test_facebook_replaces_restored_caption_without_appending(self):
        await self.page.set_content('<div contenteditable="true" role="textbox" style="white-space:pre-wrap">Old draft caption #oldOld draft caption #old</div>')
        caption='KHÔNG LẦM LỖI\n\n#baihoccuocsong #songdep'
        poster=FacebookPoster()
        self.assertTrue(await poster._fill_page_reel_caption(self.page,caption))
        self.assertTrue(await poster._fill_page_reel_caption(self.page,caption))
        self.assertEqual(await self.page.get_by_role('textbox').inner_text(),caption)

    async def test_facebook_settings_reads_current_preview_without_using_dashboard_or_hidden_editor(self):
        caption='Correct title #songdep'
        await self.page.set_content(f'''<div>{caption}</div>
            <div contenteditable="true" role="textbox" style="display:none">{caption}</div>
            <section role="complementary"><h3>Preview</h3><p>Different reel</p></section>''')
        poster=FacebookPoster()
        self.assertFalse(await poster._page_reel_caption_matches(self.page,caption))
        await self.page.locator('section p').evaluate('(e,t)=>e.textContent=t',caption)
        self.assertTrue(await poster._page_reel_caption_matches(self.page,caption))

    async def test_facebook_ai_switch_supports_input_div_and_both_languages(self):
        for label in ('Add AI label','Thêm nhãn AI'):
            for tag in ('input','div'):
                await self.page.set_content(f'''<div role="button">{label}
                    <{tag} role="switch" aria-checked="false" onclick="this.setAttribute('aria-checked','true')"></{tag}></div>
                    <div role="switch" aria-checked="false" onclick="document.body.dataset.wrong='true'"></div>
                    <div style="display:none"><div role="button">{label}<input role="switch"></div></div>''')
                poster=FacebookPoster()
                self.assertTrue(await poster._enable_page_ai_label(self.page))
                self.assertTrue(await poster._enable_page_ai_label(self.page))
                self.assertIsNone(await self.page.evaluate('document.body.dataset.wrong'))

    async def test_facebook_page_schedule_with_div_switch_and_exact_readback(self):
        await self.page.route('https://fixture.invalid/**',lambda route:route.fulfill(body='<body></body>'))
        await self.page.goto('https://fixture.invalid/reels/create')
        await self.page.set_content('''<div contenteditable="true" role="textbox"></div>
            <div role="button">Add AI label<div role="switch" aria-checked="false"
                onclick="this.setAttribute('aria-checked','true')"></div></div>
            <div role="button">Post audience Public</div>
            <button onclick="document.getElementById('panel').hidden=false">Schedule</button>
            <div role="dialog" id="panel" hidden><input role="combobox" type="search" placeholder="Search Facebook"><input role="combobox"><input role="combobox">
                <button onclick="document.getElementById('panel').hidden=true;document.getElementById('submit').textContent='Schedule Post'">Schedule for later</button></div>
            <button id="submit" onclick="document.body.dataset.sent='true';history.pushState({},'','/complete')">Post</button>''')
        poster=FacebookPoster()
        poster.checkpoint_submission=Mock()
        poster._copy_scheduled_post_link=AsyncMock(return_value='https://www.facebook.com/reel/12345/')
        poster._shot=AsyncMock()
        native={'enabled':True,'time':'20:00','year':2026,'month':10,'day':26,
            'label':'26/10/2026 20:00','datetime':datetime(2026,10,26,20)}
        result=await poster._schedule_page_reel(self.page,'Chú thích #songdep',native,True)
        self.assertTrue(result['success'])
        fields=self.page.locator('input:not([type="search"])')
        self.assertEqual(await fields.nth(0).input_value(),'26 Oct 2026')
        self.assertEqual(await fields.nth(1).input_value(),'20:00')
        self.assertEqual(await self.page.evaluate('document.body.dataset.sent'),'true')
        poster.checkpoint_submission.assert_called_once()


if __name__=='__main__':unittest.main()
