"""Read-only reconciliation. A missing row is never permission to repost."""
import asyncio
import re


def normalized(text):
    return re.sub(r'\s+', ' ', text or '').strip().casefold()


def schedule_fields_match(date, time, scheduled_for):
    from datetime import datetime
    if not scheduled_for:
        return False
    dt=datetime.strptime(scheduled_for,'%Y-%m-%d %H:%M:%S')
    date=normalized(date)
    dates=(dt.strftime('%b %d, %Y').casefold().replace(' 0',' '),dt.strftime('%Y-%m-%d'),
           dt.strftime('%d/%m/%Y'),f'{dt.day}/{dt.month}/{dt.year}',f'{dt.day} thg {dt.month}, {dt.year}')
    times=(dt.strftime('%H:%M'),dt.strftime('%I:%M %p').lstrip('0').casefold())
    return date in dates and normalized(time) in times


async def matching_library_row(page, caption, scheduled_for='', expected_url=''):
    title = (caption or '').split('\n')[0].strip()
    rows = await page.evaluate('''({title,expected}) => {
        const norm=t=>(t||'').replace(/\\s+/g,' ').trim().toLowerCase();
        const candidates=[...document.querySelectorAll('tr,li,div')].filter(e=>{
            const t=norm(e.innerText);
            return e.getClientRects().length && t.length<1600 && t.includes(norm(title))
                && (/scheduled|lên lịch|đã lên lịch|published|công khai|đã đăng/.test(t)
                    || e.querySelector('[data-tt="components_PublishStageLabel_FlexCenter"]'));
        });
        return candidates.filter(e=>!candidates.some(x=>x!==e&&e.contains(x))).map(e=>({
            text:e.innerText, href:e.querySelector('a[href*="/video/"],a[href*="/videos/"],a[href*="/reel/"],a[href*="/share/r/"],a[href*="/share/v/"],a[href*="/posts/"]')?.href||'',
            scheduled:!!e.querySelector('[data-tt="components_PublishStageLabel_FlexCenter"] [data-icon="Alarm"]'),
            stageText:e.querySelector('[data-tt="components_PublishStageLabel_FlexCenter"]')?.innerText||'',
            dates:[...e.querySelectorAll('time[datetime]')].map(t=>t.getAttribute('datetime'))
        })).filter(row=>!expected || !row.href || row.href.split('?')[0].replace(/\/$/,'')===expected.split('?')[0].replace(/\/$/,''));
    }''', {'title':title,'expected':expected_url})
    # Ambiguous same-caption posts must not become another video's success.
    if len(rows) != 1 or not title:
        from core.logger import logger
        logger.warning(f'Thư viện: {len(rows)} hàng khớp tiêu đề đầy đủ; chưa thể xác minh.', 'VERIFY')
        return None
    row = rows[0]
    text = normalized(row['text'])
    scheduled = row.get('scheduled') or bool(re.search(r'scheduled|lên lịch',text))
    if scheduled and scheduled_for:
        from datetime import datetime
        dt = datetime.strptime(scheduled_for,'%Y-%m-%d %H:%M:%S')
        times = (dt.strftime('%H:%M'),dt.strftime('%I:%M %p').lstrip('0').casefold())
        dates = (dt.strftime('%Y-%m-%d'),dt.strftime('%d/%m/%Y'),dt.strftime('%m/%d/%Y'),f'{dt.month}/{dt.day}/{dt.year}',f'{dt.day}/{dt.month}/{dt.year}',dt.strftime('%b %d').casefold(),f'{dt.strftime("%b").casefold()} {dt.day}',dt.strftime('%d/%m'))
        # Date must be displayed too; Tomorrow is accepted only relative to the verifier's current date.
        from core.posting_store import local_now
        tomorrow = (dt.date()-local_now().date()).days == 1 and ('tomorrow' in text or 'ngày mai' in text)
        today = dt.date()==local_now().date() and ('today' in text or 'hôm nay' in text)
        if not any(re.search(r'(?<!\d)'+re.escape(t)+r'(?!\d)', text) for t in times) or not (any(d in text for d in dates) or tomorrow or today):
            from core.logger import logger
            logger.warning(f'Hàng thư viện chưa khớp lịch {scheduled_for}: {text[:400]}', 'VERIFY')
            return None
    row['state'] = 'scheduled' if scheduled else 'published'
    return row


async def verify_delivery(page, poster, platform, video, task, candidate_url=''):
    caption = poster.format_caption(video)
    expected = candidate_url or task.get('post_url','')
    if platform == 'youtube':
        await page.goto('https://studio.youtube.com/',wait_until='domcontentloaded',timeout=45000)
        await asyncio.sleep(3)
        url = await poster._verify_in_shorts_content(page,poster._clean_title(video.get('suggested_title') or video.get('title') or ''),expected)
        if not url:
            return {'verified':False,'url':''}
        identity=url.rstrip('/').split('/')[-1]
        row=page.locator('ytcp-video-row').filter(has=page.locator(f'a[href*="/video/{identity}/"]')).first
        visibility=normalized(await row.locator('.tablecell-visibility').inner_text())
        if visibility in ('public','công khai'):
            return {'verified':True,'url':url,'state':'published'}
        await row.locator('.tablecell-visibility .editable').evaluate('(e)=>e.click()')
        await asyncio.sleep(1)
        date=await page.locator('#datepicker-trigger:visible').inner_text(timeout=8000)
        values=await page.locator('input:visible').evaluate_all('(es)=>es.map(e=>e.value)')
        correct=any(schedule_fields_match(date,value,task.get('scheduled_for')) for value in values)
        # Leave the read-only inspection without saving anything.
        await page.keyboard.press('Escape')
        return {'verified':correct,'url':url if correct else '', 'state':'scheduled'}
    if platform in ('tiktok','facebook'):
        if platform=='tiktok':
            await page.goto('https://www.tiktok.com/tiktokstudio/content',wait_until='domcontentloaded',timeout=45000)
            await asyncio.sleep(4)
            await poster._click_posts_tab(page)
        else:
            from automation.posters.facebook_poster import FB_LIBRARY_SCHEDULED
            await page.goto(FB_LIBRARY_SCHEDULED,wait_until='domcontentloaded',timeout=45000)
            await asyncio.sleep(4)
            await poster._dismiss_fb_popups(page)
        row = await matching_library_row(page,caption,task.get('scheduled_for',''),expected)
        if not row and platform == 'facebook':
            from core.posting_store import stamp
            if task.get('scheduled_for') and task['scheduled_for'] <= stamp():
                await page.goto(FB_LIBRARY_SCHEDULED.replace('SCHEDULED','PUBLISHED'),wait_until='domcontentloaded',timeout=45000)
                await asyncio.sleep(4)
                await poster._dismiss_fb_popups(page)
                row=await matching_library_row(page,caption,task['scheduled_for'],expected)
        if not row:
            return {'verified':False,'url':''}
        if row['state'] == 'published':
            from datetime import datetime
            from core.posting_store import VIETNAM
            if not task.get('submitted_at'):
                return {'verified':False,'url':''}
            submitted=datetime.strptime(task['submitted_at'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=VIETNAM)
            valid_dates=[]
            for value in row.get('dates',[]):
                try:
                    valid_dates.append(datetime.fromisoformat(value.replace('Z','+00:00')))
                except ValueError:
                    pass
            if platform == 'tiktok' and row.get('stageText'):
                # Studio's observed published date is plain text, not a <time>.
                # Anchor its missing year to this task, never an arbitrary old row.
                stage = normalized(row['stageText'])
                anchor = task.get('scheduled_for') or task['submitted_at']
                for fmt in ('%b %d, %I:%M %p', '%b %d, %H:%M'):
                    try:
                        value = datetime.strptime(stage,fmt).replace(year=int(anchor[:4]),tzinfo=VIETNAM)
                        valid_dates.append(value)
                        break
                    except ValueError:
                        continue
            if platform == 'facebook':
                anchor=task.get('scheduled_for') or task['submitted_at']
                date_match=re.search(r'(?:published|đã đăng)\s*[•·]\s*(\d{1,2}\s+[a-z]{3}\s+at\s+\d{1,2}:\d{2})',normalized(row['text']))
                if date_match:
                    try:
                        valid_dates.append(datetime.strptime(date_match.group(1),'%d %b at %H:%M').replace(year=int(anchor[:4]),tzinfo=VIETNAM))
                    except ValueError:
                        pass
            if not any(0 <= (d-submitted).total_seconds() <= 172800 for d in valid_dates if d.tzinfo):
                return {'verified':False,'url':''}
        url = row['href'] or (expected if task.get('state') in ('scheduled','published') else '')
        if not url:
            try:
                if platform == 'facebook':
                    url = await asyncio.wait_for(poster._copy_scheduled_post_link(page,caption,published=row['state']=='published',scheduled_for=task.get('scheduled_for','')),timeout=35)
                else:
                    url = await asyncio.wait_for(poster._copy_scheduled_post_link(page,caption),timeout=35)
            except Exception:
                url = ''
        valid = poster._is_tt_permalink(url) if platform=='tiktok' else poster._is_fb_permalink(url)
        return {'verified':True,'url':url if valid else '', 'state':row['state']}
    # Instagram: inspect candidate permalink, or recent profile entries after a crash.
    if platform=='instagram':
        if expected and poster._is_permalink(expected):
            urls=[expected]
        else:
            await page.goto('https://www.instagram.com/',wait_until='domcontentloaded',timeout=45000)
            await asyncio.sleep(3)
            await poster._goto_own_profile(page)
            urls=await page.locator('a[href*="/p/"],a[href*="/reel/"]').evaluate_all('(a)=>a.slice(0,12).map(e=>e.href)')
        for url in dict.fromkeys(urls):
            await page.goto(url,wait_until='domcontentloaded',timeout=45000)
            await asyncio.sleep(3)
            text=await page.locator('main').inner_text(timeout=10000)
            if normalized(caption) not in normalized(text):
                continue
            dates=await page.locator('time[datetime]').evaluate_all('(els)=>els.map(e=>e.getAttribute("datetime"))')
            if not dates or not task.get('submitted_at'):
                continue
            from datetime import datetime, timezone
            from core.posting_store import VIETNAM
            submitted=datetime.strptime(task['submitted_at'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=VIETNAM)
            if any(abs((datetime.fromisoformat(d.replace('Z','+00:00')).astimezone(timezone.utc)-submitted.astimezone(timezone.utc)).total_seconds())<1800 for d in dates):
                return {'verified':True,'url':poster._normalize_url(url),'state':'published'}
    return {'verified':False,'url':''}
