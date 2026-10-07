"""Repair only explicitly requested metadata on an already identified TikTok post."""
import asyncio
from automation.posting_verifier import normalized


async def repair_tiktok_caption(page, poster, video, task):
    url = task.get('post_url', '')
    if not task.get('submitted_at') or not poster._is_tt_permalink(url):
        return False
    await page.goto('https://www.tiktok.com/tiktokstudio/content',wait_until='domcontentloaded',timeout=45000)
    await asyncio.sleep(4)
    caption = poster.format_caption(video)
    identity = url.rstrip('/').split('/')[-1].split('?')[0]
    result = await page.evaluate(r'''({id,caption}) => {
        const a=[...document.querySelectorAll('a[href*="/video/"]')].filter(a=>a.href.split('?')[0].replace(/\/$/,'').endsWith('/'+id));
        if(a.length!==1) return 'ambiguous';
        const norm=t=>(t||'').replace(/\s+/g,' ').trim().toLowerCase();
        if(norm(a[0].innerText)===norm(caption))return 'already-correct';
        const row=a[0].closest('[data-tt="components_PostTable_Absolute"]');
        const pen=row?.querySelector('[data-icon="Pen"]')?.closest('[data-tt="components_ActionCell_Container"]');
        if(!pen||pen.getAttribute('cursor')==='not-allowed'||pen.getAttribute('aria-disabled')==='true')return 'locked';
        pen.click();return 'opened';
    }''',{'id':identity,'caption':caption})
    if result=='already-correct':
        return True
    if result!='opened':
        return False
    await asyncio.sleep(3)
    if not await poster._fill_caption(page,caption):
        return False
    save = page.get_by_role('button',name='Save',exact=True).or_(page.get_by_role('button',name='Lưu',exact=True)).first
    if not await save.is_visible(timeout=5000) or not await save.is_enabled():
        return False
    await save.focus()
    await asyncio.wait_for(page.keyboard.press('Enter'),timeout=8)
    await asyncio.sleep(4)
    await page.goto('https://www.tiktok.com/tiktokstudio/content',wait_until='domcontentloaded',timeout=45000)
    await asyncio.sleep(4)
    text=await page.locator(f'a[href*="/video/{identity}"]').inner_text(timeout=10000)
    return normalized(text)==normalized(caption)
