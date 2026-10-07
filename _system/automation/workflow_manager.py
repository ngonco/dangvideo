import asyncio
from typing import List, Dict, Any, Optional
from core.logger import logger
from core.database import db
from core.config_manager import config_mgr
from automation.browser_engine import browser_engine
from automation.hatbuinho_crawler import hatbuinho_crawler
from automation.posters.youtube_poster import youtube_poster
from automation.posters.tiktok_poster import tiktok_poster
from automation.posters.facebook_poster import facebook_poster
from automation.posters.instagram_poster import instagram_poster

class WorkflowManager:
    def __init__(self):
        self._is_busy = False
        self._lock = asyncio.Lock()

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    async def scan_and_download(
        self,
        max_items: Optional[int] = None,
        force_latest: bool = False,
        oldest_first: bool = True,
        exclude_today: bool = False,
        fallback_latest: bool = False,
        force_repost: bool = False,
    ) -> List[Dict[str, Any]]:
        if self._is_busy:
            logger.warning("Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi...", "WORKFLOW")
            return []

        async with self._lock:
            if self._is_busy:
                return []
            self._is_busy = True
            try:
                safety_str = " (Lọc an toàn: Bỏ qua video tạo hôm nay)" if exclude_today else ""
                mode_name = "TEST ÉP TẢI VIDEO MỚI NHẤT" if force_latest else f"QUÉT TẢI VIDEO 'CHƯA TẢI XUỐNG' ({'Cũ nhất' if oldest_first else 'Mới nhất'}){safety_str}"
                if fallback_latest and not force_latest:
                    mode_name += " (hết Chưa tải thì lấy video mới nhất)"
                if force_repost:
                    mode_name += " [XÁC NHẬN ÉP ĐĂNG LẠI]"
                logger.info(f"Bắt đầu tác vụ: {mode_name} từ hatbuinho.com...", "WORKFLOW")
                results = await hatbuinho_crawler.scan_and_download(
                    max_items=max_items,
                    force_latest=force_latest,
                    oldest_first=oldest_first,
                    exclude_today=exclude_today,
                    fallback_latest=fallback_latest,
                    force_repost=force_repost,
                )
                return results
            finally:
                self._is_busy = False

    async def batch_download_to_queue(self, max_items: int = 50) -> Dict[str, Any]:
        """Tải hàng loạt toàn bộ video 'Chưa tải xuống' vào kho hàng đợi để đăng đa ngày"""
        if self._is_busy:
            logger.warning("Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi...", "WORKFLOW")
            return {"success": False, "error": "Hệ thống đang bận thực hiện tác vụ khác"}

        async with self._lock:
            self._is_busy = True
            try:
                logger.info(f"🚀 Bắt đầu quét & tải hàng loạt toàn bộ video 'Chưa tải xuống' vào Kho Hàng Đợi...", "WORKFLOW")
                results = await hatbuinho_crawler.scan_and_download(max_items=max_items, force_latest=False, oldest_first=True)
                
                queue_summary = db.get_queue_summary(slots_per_day=1)
                
                if len(results) > 0:
                    msg = f"Đã tải về thành công {len(results)} video vào Kho Hàng Đợi! (Hiện có {queue_summary['total_pending']} video, dự kiến đăng trong {queue_summary['estimated_days']} ngày)."
                else:
                    source_status = hatbuinho_crawler.last_scan_status
                    if source_status.get('state') in ('unreadable','network_error','needs_login'):
                        return {'success':False,'downloaded_count':0,'total_pending':queue_summary['total_pending'],'estimated_days':queue_summary['estimated_days'],'error':source_status['detail']}
                    if queue_summary['total_pending'] > 0:
                        msg = f"Toàn bộ video hiển thị trên HatBuiNho đều đã được tải. Kho hàng đợi hiện đang có {queue_summary['total_pending']} video sẵn sàng đăng (dự kiến đăng trong {queue_summary['estimated_days']} ngày)."
                    else:
                        msg = hatbuinho_crawler.last_scan_status.get('detail') or "Không có video mới hợp lệ để tải thêm."

                return {
                    "success": True,
                    "downloaded_count": len(results),
                    "total_pending": queue_summary["total_pending"],
                    "estimated_days": queue_summary["estimated_days"],
                    "message": msg
                }
            except Exception as ex:
                logger.error(f"Lỗi khi tải hàng loạt vào hàng đợi: {ex}", "WORKFLOW")
                return {"success": False, "error": str(ex)}
            finally:
                self._is_busy = False

    async def publish_video_to_platforms(
        self,
        video_id: int,
        target_platforms: Optional[List[str]] = None,
        schedule_time: Optional[str] = None,
        target_date: Optional[str] = None,
        allow_repost: bool = False,
        enforce_ig_gap: bool = True,
        respect_retry: bool = False,
    ) -> Dict[str, Any]:
        if self._is_busy:
            logger.warning("Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi...", "WORKFLOW")
            return {"success": False, "error": "Hệ thống đang bận"}

        async with self._lock:
            if self._is_busy:
                return {"success": False, "error": "Hệ thống đang bận"}
            self._is_busy = True
            try:
                video = db.get_video_by_id(video_id)
                if not video:
                    logger.error(f"Không tìm thấy video ID #{video_id} trong cơ sở dữ liệu.", "WORKFLOW")
                    return {"success": False, "error": "Video không tồn tại"}

                import os
                file_path = video.get("file_path", "")
                attempted_restore = False

                logger.info(f"Bắt đầu đăng tải video ID #{video_id}: '{video.get('suggested_title') or video.get('title')}'{' (Cho phép đăng lại)' if allow_repost else ''}...", "WORKFLOW")
                
                platforms_cfg = config_mgr.get("platforms", {})
                if target_platforms is None:
                    target_platforms = [p for p, cfg in platforms_cfg.items() if cfg.get("enabled", False)]
                all_enabled = [p for p, cfg in platforms_cfg.items() if cfg.get('enabled', False)]
                db.claim_manual_daily_video(video_id, all_enabled)

                from core.schedule_helper import get_native_schedule, get_instagram_min_gap_hours
                from datetime import datetime
                native = get_native_schedule(schedule_time or "", target_date_override=target_date)
                sched_time = native["time"]
                target_dt_str = native["date_iso"]
                logger.info(
                    f"Hẹn native công khai: {native['label']} (tải lên ngay, hẹn lúc {native['label']}). Instagram: chia sẻ ngay.",
                    "WORKFLOW",
                )

                already_success_platforms = db.get_successful_platforms_for_video(video_id)

                results = {}
                for plat in target_platforms:
                    logger.info(f"--- Đang chuẩn bị đăng lên {plat.upper()} ---", "WORKFLOW")

                    # CHỐNG ĐĂNG TRÙNG THEO TỪNG KÊNH: Bỏ qua kênh nếu video này đã từng đăng thành công trước đó (trừ khi cho phép đăng lại)
                    if plat in already_success_platforms and not allow_repost:
                        msg = f"Video #{video_id} đã đăng thành công lên {plat.upper()} trước đó. Tự động bỏ qua kênh này để chống đăng trùng."
                        logger.info(f"[SKIP ĐĂNG TRÙNG] {msg}", plat.upper())
                        db.record_post(
                            video_id=video_id,
                            platform=plat,
                            status="skipped",
                            post_url="",
                            error_message=msg,
                        )
                        results[plat] = {"success": True, "skipped": True, "url": "", "error": msg}
                        await asyncio.sleep(1)
                        continue

                    from core.posting_store import local_now, stamp
                    task = db.ensure_posting_task(video_id, plat)
                    if respect_retry and task['state'] == 'needs_login':
                        results[plat] = {'success': False, 'state':'needs_login', 'error':task['error']}
                        continue
                    if respect_retry and task['next_retry'] and task['next_retry'] > stamp():
                        results[plat] = {'success': False, 'deferred': True, 'state': task['state']}
                        continue

                    if plat == "instagram" and enforce_ig_gap and not task['submitted_at']:
                        gap_hours = get_instagram_min_gap_hours()
                        last_ig = db.get_last_success_at("instagram")
                        if last_ig:
                            elapsed = (local_now() - last_ig).total_seconds() / 3600.0
                            if elapsed < gap_hours:
                                remain = round(gap_hours - elapsed, 1)
                                msg = (
                                    f"Instagram chưa đủ {gap_hours:g} tiếng kể lần đăng trước "
                                    f"({last_ig.strftime('%d/%m %H:%M')}). Bỏ qua kênh này, còn {remain} tiếng."
                                )
                                logger.info(msg, "INSTAGRAM")
                                db.record_post(
                                    video_id=video_id,
                                    platform="instagram",
                                    status="skipped",
                                    post_url="",
                                    error_message=msg,
                                )
                                results[plat] = {"success": True, "skipped": True, "url": "", "error": msg}
                                from datetime import timedelta
                                db.finish_posting_task(video_id, plat, 'deferred', msg, retry_at=last_ig+timedelta(hours=gap_hours))
                                await asyncio.sleep(1)
                                continue
                    res = {"success": False, "error": "Nền tảng chưa hỗ trợ", "url": ""}
                    page = None
                    posters = {'youtube': youtube_poster, 'tiktok': tiktok_poster, 'facebook': facebook_poster, 'instagram': instagram_poster}
                    poster = posters.get(plat)
                    from automation.delivery_context import delivery_context
                    token = delivery_context.set((video_id, plat))

                    try:
                        ctx = await browser_engine.get_context()
                        page = await browser_engine.get_page(ctx)
                        from automation.posting_verifier import verify_delivery
                        if task['submitted_at'] and not allow_repost:
                            db.begin_verification_attempt(video_id,plat)
                            verified = await verify_delivery(page, poster, plat, video, task)
                            res = {'success': verified['verified'], 'url': verified.get('url',''), 'state': verified.get('state','verifying'), 'error': '' if verified['verified'] else 'Đã gửi trước đó; chưa xác định kết quả. Không tải lên lần nữa.'}
                        elif poster:
                            # Submitted channels can reconcile even if the local file disappeared.
                            # Only a fresh upload needs the media, and removed videos stay removed.
                            if not file_path or not os.path.isfile(file_path):
                                if respect_retry and video.get('status') == 'cleaned':
                                    raise FileNotFoundError('Video đã dọn khỏi kho; không tự khôi phục.')
                                if not attempted_restore:
                                    attempted_restore = True
                                    new_path = await hatbuinho_crawler.redownload_video_for_repost(video)
                                    if new_path and os.path.isfile(new_path):
                                        file_path = new_path
                                        db.update_video_file_path(video_id,new_path,os.path.getsize(new_path),'downloaded')
                                        video = db.get_video_by_id(video_id)
                                if not file_path or not os.path.isfile(file_path):
                                    raise FileNotFoundError('Thiếu tệp video và chưa thể tải lại từ nguồn.')
                            if task['state'] == 'failed' and task['attempts']:
                                await browser_engine.close()
                                ctx = await browser_engine.get_context()
                                page = await browser_engine.get_page(ctx)
                            if allow_repost:
                                with db.get_connection() as conn:
                                    conn.execute("UPDATE posting_tasks SET submitted_at='',post_url='' WHERE video_id=? AND platform=?",(video_id,plat))
                            db.begin_posting(video_id, plat, native['datetime'].strftime('%Y-%m-%d %H:%M:%S') if plat != 'instagram' else '')
                            poster.delivery_video_id = video_id
                            res = await asyncio.wait_for(poster.post_video(page, video, schedule_time=sched_time, target_date=target_dt_str), timeout=1800)
                            if res.get('success'):
                                if res.get('url'):
                                    db.set_posting_candidate_url(video_id,plat,res['url'])
                                task = db.get_posting_task(video_id, plat)
                                verified = await verify_delivery(page, poster, plat, video, task, res.get('url',''))
                                res.update(success=verified['verified'], url=verified.get('url',''), state=verified.get('state','verifying'))
                                if not verified['verified']:
                                    res['error'] = 'Đã gửi nhưng chưa xác minh đúng bài và lịch; sẽ kiểm tra lại, không đăng lại.'

                    except Exception as ex:
                        import traceback
                        tb = traceback.format_exc()
                        logger.error(f"Lỗi ngoại lệ khi đăng lên {plat.upper()}: {str(ex)}", "WORKFLOW")
                        res = {"success": False, "error": str(ex) or type(ex).__name__, "url": "", "error_details": tb}
                    finally:
                        if poster:
                            poster.delivery_video_id = None
                        delivery_context.reset(token)

                    status = "success" if res.get("success") else "failed"
                    task_state = res.get('state') if res.get('success') else ('needs_login' if 'đăng nhập' in res.get('error','').casefold() else 'failed')
                    task_state = task_state or ('published' if plat == 'instagram' else 'scheduled')
                    db.finish_posting_task(video_id, plat, task_state, res.get('error',''), res.get('url',''))
                    incident_changed = db.set_health(f'channel:{video_id}:{plat}', task_state if status == 'success' else db.get_posting_task(video_id,plat)['state'], res.get('error',''))
                    if status == "failed" and res.get("error") and incident_changed:
                        try:
                            from core.email_reporter import email_reporter
                            v_title = video.get('suggested_title') or video.get('title') or f"Video #{video_id}"
                            email_reporter.send_error_alert(
                                platform=plat,
                                error_message=res.get("error"),
                                step=f"Đăng bài '{v_title}' lên {plat.upper()} — AI không xử lý được, bỏ kênh này, tiếp tục kênh khác",
                                details=res.get("error_details") or res.get("ai_diagnosis") or "",
                            )
                        except Exception:
                            pass

                    db.record_post(
                        video_id=video_id,
                        platform=plat,
                        status=status,
                        post_url=res.get("url", ""),
                        error_message=res.get("error", "")
                    )
                    results[plat] = res

                    # Delay between platforms
                    await asyncio.sleep(4)

                successful_after_run = set(db.get_successful_platforms_for_video(video_id))
                required_platforms = set(all_enabled)
                missing_platforms = sorted(required_platforms - successful_after_run)
                if missing_platforms:
                    db.set_video_status(video_id, "downloaded")
                    logger.warning(
                        "Video vẫn được giữ trong hàng đợi vì chưa đăng thành công lên: "
                        + ", ".join(p.upper() for p in missing_platforms),
                        "WORKFLOW",
                    )
                else:
                    db.set_video_status(video_id, "posted")
                    logger.success("Video đã hoàn tất trên tất cả kênh mục tiêu.", "WORKFLOW")

                return {"success": True, "completed": not missing_platforms, "missing_platforms": missing_platforms, "details": results}

            finally:
                self._is_busy = False

    async def open_login_browser(self, target_url: str = "https://hatbuinho.com/"):
        logger.info(f"Mở trình duyệt cho người dùng đăng nhập tài khoản: {target_url}", "AUTH")
        ctx = await browser_engine.get_context(headless=False)
        page = await browser_engine.get_page(ctx)
        await page.goto(target_url)

    async def repair_pending_links(self):
        if self._is_busy:
            return
        async with self._lock:
            self._is_busy = True
            try:
                from automation.posting_verifier import verify_delivery
                from core.posting_store import stamp, local_now
                from datetime import timedelta
                posters = {'youtube': youtube_poster, 'tiktok': tiktok_poster, 'facebook': facebook_poster, 'instagram': instagram_poster}
                for task in db.tasks_missing_links():
                    video = db.get_video_by_id(task['video_id'])
                    if not video:
                        continue
                    try:
                        page = await browser_engine.get_page(await browser_engine.get_context())
                        verified = await verify_delivery(page, posters[task['platform']], task['platform'], video, task)
                        if verified.get('verified'):
                            if verified.get('url'):
                                db.update_latest_success_post_url(video['id'], task['platform'], verified['url'])
                            db.finish_posting_task(video['id'], task['platform'], verified['state'], post_url=verified.get('url',''))
                        if not verified.get('url'):
                            with db.get_connection() as conn:
                                conn.execute('UPDATE posting_tasks SET next_retry=? WHERE video_id=? AND platform=?', (stamp(local_now()+timedelta(hours=2)),video['id'],task['platform']))
                    except Exception as exc:
                        logger.warning(f'Chưa khôi phục được link {task["platform"]}: {exc}', 'WORKFLOW')
            finally:
                self._is_busy = False

    async def repair_requested_captions(self):
        if self._is_busy:
            return
        async with self._lock:
            self._is_busy = True
            try:
                import json
                with db.get_connection() as conn:
                    requests=[dict(r) for r in conn.execute("SELECT * FROM posting_health WHERE name LIKE 'caption-repair:%' AND state='pending'")]
                from automation.caption_repair import repair_tiktok_caption
                for request in requests:
                    data=json.loads(request['detail'])
                    task=db.get_posting_task(data['video_id'],'tiktok')
                    video=db.get_video_by_id(data['video_id'])
                    if not task or not video or task.get('post_url')!=data['post_url']:
                        continue
                    try:
                        page=await browser_engine.get_page(await browser_engine.get_context())
                        repaired=await asyncio.wait_for(repair_tiktok_caption(page,tiktok_poster,video,task),timeout=90)
                        if repaired:
                            db.set_health(request['name'],'complete',request['detail'])
                            from core.posting_store import local_now
                            db.finish_posting_task(video['id'],'tiktok','verifying','Đã sửa chú thích; đang chờ đối chiếu bài.',retry_at=local_now())
                            logger.success('Đã sửa và đọc lại chú thích bài TikTok đã tồn tại; không đăng lại.', 'TIKTOK')
                    except Exception as exc:
                        logger.warning(f'Chưa sửa được chú thích bài đã tồn tại: {type(exc).__name__}', 'TIKTOK')
            finally:
                self._is_busy = False

workflow_mgr = WorkflowManager()
