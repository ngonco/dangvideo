import os
import sys
import asyncio
import subprocess
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.logger import logger
from core.database import db
from core.config_manager import config_mgr, ROOT_DIR, SYSTEM_DIR, DOWNLOADS_DIR, get_app_version
from core.autostart_manager import autostart_mgr
from core.browser_runtime import browser_runtime
from core.update_manager import update_manager
from automation.workflow_manager import workflow_mgr
from scheduler.task_scheduler import task_scheduler

STATIC_DIR = os.path.join(SYSTEM_DIR, "static")
if not os.path.exists(STATIC_DIR):
    if hasattr(sys, '_MEIPASS') and os.path.exists(os.path.join(sys._MEIPASS, "static")):
        STATIC_DIR = os.path.join(sys._MEIPASS, "static")
    elif os.path.exists(os.path.join(ROOT_DIR, "static")):
        STATIC_DIR = os.path.join(ROOT_DIR, "static")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

_browser_runtime_install_task = None


async def _install_browser_runtime():
    try:
        logger.info("Đang chuẩn bị Camoufox riêng cho Auto Đăng Video...", "BROWSER")
        await asyncio.to_thread(browser_runtime.ensure_ready)
        logger.success("Camoufox riêng của Auto Đăng Video đã sẵn sàng.", "BROWSER")
    except Exception as exc:
        logger.error(f"Không chuẩn bị được Camoufox riêng: {exc}", "BROWSER")


def _start_browser_runtime_install():
    global _browser_runtime_install_task
    if browser_runtime.is_ready:
        return None
    if _browser_runtime_install_task is None or _browser_runtime_install_task.done():
        _browser_runtime_install_task = asyncio.create_task(_install_browser_runtime())
    return _browser_runtime_install_task


async def require_browser_runtime():
    if browser_runtime.is_ready:
        return
    _start_browser_runtime_install()
    status = browser_runtime.status()
    raise HTTPException(
        status_code=503,
        detail={
            "code": "browser_runtime_not_ready",
            "message": "Camoufox riêng đang được cài đặt. Vui lòng theo dõi Nhật ký và thử lại.",
            "runtime_status": status.get("status"),
            "error": status.get("error"),
        },
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fix Windows asyncio Proactor 10054 noise on connection reset
    try:
        loop = asyncio.get_running_loop()
        orig_handler = loop.get_exception_handler()
        def win_asyncio_exception_handler(loop, context):
            msg = str(context.get("exception", "") or context.get("message", ""))
            if "10054" in msg or "connection_lost" in msg or "ConnectionResetError" in msg:
                return
            if orig_handler:
                orig_handler(loop, context)
            else:
                loop.default_exception_handler(context)
        loop.set_exception_handler(win_asyncio_exception_handler)
    except Exception:
        pass

    # Startup: Start scheduler if auto mode enabled
    logger.info("Khởi động hệ thống Auto Đăng Video...", "SERVER")
    _start_browser_runtime_install()
    task_scheduler.start()
    update_manager.set_busy_provider(lambda: workflow_mgr.is_busy)
    await update_manager.start()
    yield
    # Shutdown: Stop scheduler & close browser
    await update_manager.stop()
    task_scheduler.stop()
    from automation.browser_engine import browser_engine
    await browser_engine.close()
    logger.info("Đã tắt hệ thống an toàn.", "SERVER")

app = FastAPI(title="Auto Video Uploader & Downloader", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class ConfigUpdateRequest(BaseModel):
    hatbuinho: Optional[Dict[str, Any]] = None
    platforms: Optional[Dict[str, Any]] = None
    schedule: Optional[Dict[str, Any]] = None
    cleanup: Optional[Dict[str, Any]] = None
    browser: Optional[Dict[str, Any]] = None
    schedule_publish: Optional[Dict[str, Any]] = None
    custom_caption: Optional[Dict[str, Any]] = None

class PostVideoRequest(BaseModel):
    video_id: int
    target_platforms: Optional[List[str]] = None
    schedule_time: Optional[str] = None
    target_date: Optional[str] = None

class RunWorkflowRequest(BaseModel):
    mode: Optional[str] = "normal"
    schedule_time: Optional[str] = None
    target_date: Optional[str] = None
    force_repost: Optional[bool] = False
    video_id: Optional[int] = None

class RepostVideoRequest(BaseModel):
    video_id: int
    schedule_time: Optional[str] = None
    target_date: Optional[str] = None
    target_platforms: Optional[List[str]] = None

class ScanRequest(BaseModel):
    max_items: Optional[int] = None
    force_latest: Optional[bool] = False

class OpenLoginRequest(BaseModel):
    url: Optional[str] = "https://hatbuinho.com/"

# API Endpoints
@app.get("/api/stats")
async def get_stats():
    stats = db.get_stats()
    sched_cfg = config_mgr.get("schedule", {})
    stats["auto_mode"] = sched_cfg.get("auto_mode", False)
    stats["max_posts_per_day"] = 1
    stats["is_busy"] = workflow_mgr.is_busy
    return stats

@app.get("/api/videos")
async def get_videos(limit: int = 50, offset: int = 0):
    videos = db.list_videos(limit=limit, offset=offset)
    return {"videos": videos}

@app.get("/api/history")
async def get_history(limit: int = 100):
    history = db.get_all_videos_with_latest_posts(limit=limit)
    return {"history": history}

@app.get("/api/system/posting-health")
async def get_posting_health():
    health = db.get_posting_health()
    health['is_busy'] = workflow_mgr.is_busy
    return health

@app.get("/api/videos/{video_id}/history")
async def get_video_history(video_id: int):
    posts = db.get_post_history(video_id=video_id)
    video = db.get_video_by_id(video_id)
    return {"video": video, "posts": posts}

@app.get("/api/config")
async def get_config():
    return config_mgr.config

@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    mute_changed = False
    headless_changed = False
    if isinstance(updates.get("browser"), dict):
        current_browser = dict(config_mgr.get("browser") or {})
        mute_changed = "mute_audio" in updates["browser"]
        headless_changed = "headless" in updates["browser"]
        current_browser.update(updates["browser"])
        updates["browser"] = current_browser
    if isinstance(updates.get("platforms"), dict):
        current_platforms = dict(config_mgr.get("platforms") or {})
        for plat, p_cfg in updates["platforms"].items():
            if isinstance(p_cfg, dict) and isinstance(current_platforms.get(plat), dict):
                merged = dict(current_platforms[plat])
                merged.update(p_cfg)
                current_platforms[plat] = merged
            else:
                current_platforms[plat] = p_cfg
        updates["platforms"] = current_platforms
    config_mgr.update(updates)
    if 'platforms' in updates:
        db.update_today_targets([p for p,cfg in config_mgr.get('platforms',{}).items() if cfg.get('enabled',False)])
    task_scheduler.reload_jobs()
    logger.info("Đã cập nhật cấu hình hệ thống.", "CONFIG")
    if mute_changed or headless_changed:
        from automation.browser_engine import browser_engine
        if workflow_mgr.is_busy:
            logger.info(
                "Đã lưu cấu hình trình duyệt; sẽ áp dụng lần mở tiếp theo (đang đăng, không đóng cửa sổ).",
                "BROWSER",
            )
        else:
            await browser_engine.close()
    return {"success": True, "config": config_mgr.config}

@app.get("/api/facebook/pages")
async def get_facebook_pages():
    await require_browser_runtime()
    """Quét danh sách các Fanpage mà tài khoản Facebook đang quản trị."""
    if workflow_mgr.is_busy:
        raise HTTPException(status_code=400, detail="Hệ thống đang bận thực hiện tác vụ khác.")
    from automation.posters.facebook_poster import facebook_poster
    try:
        pages = await facebook_poster.scan_managed_pages()
        return {"success": True, "pages": pages}
    except Exception as e:
        logger.error(f"Lỗi khi quét Fanpage Facebook: {e}", "FACEBOOK")
        return {"success": False, "error": str(e), "pages": []}

@app.post("/api/action/scan")
async def trigger_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    await require_browser_runtime()
    if workflow_mgr.is_busy:
        raise HTTPException(status_code=400, detail="Hệ thống đang bận thực hiện tác vụ khác.")
    
    background_tasks.add_task(workflow_mgr.scan_and_download, req.max_items, req.force_latest)
    mode_text = "Test ép tải video mới nhất" if req.force_latest else "Quét video 'Chưa tải xuống'"
    return {"success": True, "message": f"Đã bắt đầu {mode_text} trong nền."}

@app.post("/api/action/post")
async def trigger_post(req: PostVideoRequest, background_tasks: BackgroundTasks):
    await require_browser_runtime()
    if workflow_mgr.is_busy:
        raise HTTPException(status_code=400, detail="Hệ thống đang bận thực hiện tác vụ khác.")
    
    video = db.get_video_by_id(req.video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Không tìm thấy video.")

    background_tasks.add_task(workflow_mgr.publish_video_to_platforms, req.video_id, req.target_platforms, req.schedule_time)
    return {"success": True, "message": f"Đã bắt đầu đăng video #{req.video_id} lên các nền tảng."}

@app.post("/api/action/run-workflow")
async def trigger_run_workflow(req: Optional[RunWorkflowRequest] = None):
    await require_browser_runtime()
    if workflow_mgr.is_busy:
        return {"success": False, "message": "Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi..."}

    force_repost = bool(req and req.force_repost)

    pending = None
    if not force_repost:
        pending = db.get_oldest_pending_video()

    if not pending:
        logger.info(
            f"Kho trống, quét video 'Chưa tải xuống' trên HatBuiNho{' (ép tải lại: BẬT)' if force_repost else ' (chống trùng: BẬT)'}...",
            "WORKFLOW"
        )
        new_vids = await workflow_mgr.scan_and_download(
            max_items=1,
            force_latest=force_repost,
            oldest_first=True,
            fallback_latest=force_repost,
            force_repost=force_repost,
        )
        if new_vids:
            pending = db.get_oldest_pending_video()

    if not pending:
        if not force_repost:
            return {
                "success": False,
                "need_confirmation": True,
                "message": "Tất cả video trên HatBuiNho đều đã được đăng lên các nền tảng.\n\nBạn có chắc chắn muốn ép tải và đăng lại video gần nhất không?",
            }
        return {"success": False, "message": "Không tìm thấy video nào để đăng trên HatBuiNho."}

    from core.schedule_helper import get_native_schedule
    native = get_native_schedule(
        time_override=req.schedule_time or "" if req else "",
        target_date_override=req.target_date if req else None
    )
    sched_time = native["time"]
    target_date = native["date_iso"]
    res = await workflow_mgr.publish_video_to_platforms(
        pending["id"],
        schedule_time=sched_time,
        target_date=target_date,
        allow_repost=force_repost,
        enforce_ig_gap=True
    )
    v_title = pending.get("suggested_title") or pending.get("title")
    return {
        "success": True,
        "message": f"Đã hoàn thành phân phối đăng video #{pending['id']}: '{v_title}' (Hẹn native: {native['label']})!",
        "details": res.get("details", {})
    }

@app.get("/api/schedule/next-slot-options")
async def get_next_slot_options():
    """Lấy danh sách các khung giờ hẹn đăng khả dụng tính từ post_time_slots cài đặt."""
    from core.schedule_helper import get_available_slot_options, get_next_post_time_slot
    return {
        "next_slot": get_next_post_time_slot(),
        "options": get_available_slot_options()
    }

@app.get("/api/videos/selection-list")
async def get_selection_list(limit: int = 100):
    """Danh sách tất cả video trong hệ thống (cả chờ đăng lẫn đã đăng) để người dùng chọn đăng lại."""
    videos = db.get_all_videos_for_selection(limit=limit)
    return {"videos": videos}

@app.post("/api/action/repost")
async def repost_video(req: RepostVideoRequest):
    await require_browser_runtime()
    """Đăng lại một video cụ thể theo khung giờ hẹn do người dùng chọn."""
    if workflow_mgr.is_busy:
        return {"success": False, "message": "Hệ thống đang bận thực hiện tác vụ khác. Vui lòng đợi..."}
    
    video = db.get_video_by_id(req.video_id)
    if not video:
        return {"success": False, "message": f"Không tìm thấy video #{req.video_id}"}
    
    from core.schedule_helper import get_native_schedule
    native = get_native_schedule(req.schedule_time or "", target_date_override=req.target_date)
    sched_time = native["time"]
    target_date = native["date_iso"]
    
    res = await workflow_mgr.publish_video_to_platforms(
        video_id=req.video_id,
        target_platforms=req.target_platforms,
        schedule_time=sched_time,
        target_date=target_date,
        allow_repost=True,
        enforce_ig_gap=False
    )
    v_title = video.get("suggested_title") or video.get("title") or f"#{req.video_id}"
    return {
        "success": res.get("success", False),
        "scheduled_for": native["label"],
        "message": f"Đã lên lịch đăng lại video '{v_title}' vào lúc {native['label']}!",
        "details": res.get("details", {})
    }

@app.post("/api/action/cleanup")
@app.post("/api/action/cleanup-old-videos")
async def trigger_cleanup():
    cleanup_cfg = config_mgr.get("cleanup", {})
    retention_days = cleanup_cfg.get("retention_days", 2)
    res = db.clean_old_posted_videos(retention_days=retention_days)
    logger.info(f"Thực hiện dọn dẹp: Đã xóa {res['deleted_count']} video cũ (> {retention_days} ngày), giải phóng {res['freed_mb']} MB.", "CLEANUP")
    return {"success": True, "message": f"Đã dọn dẹp {res['deleted_count']} video cũ, giải phóng {res['freed_mb']} MB.", "results": res}

@app.post("/api/action/open-login")
async def open_login(req: OpenLoginRequest, background_tasks: BackgroundTasks):
    await require_browser_runtime()
    background_tasks.add_task(workflow_mgr.open_login_browser, req.url)
    return {"success": True, "message": f"Đang mở trình duyệt đăng nhập: {req.url}"}

@app.post("/api/action/toggle-scheduler")
async def toggle_scheduler():
    current_auto = config_mgr.get("schedule", {}).get("auto_mode", False)
    new_auto = not current_auto
    sched_cfg = config_mgr.get("schedule", {})
    sched_cfg["auto_mode"] = new_auto
    config_mgr.update({"schedule": sched_cfg})
    task_scheduler.reload_jobs()
    status_str = "BẬT" if new_auto else "TẮT"
    logger.info(f"Đã {status_str} chế độ tự động đăng theo lịch.", "SCHEDULER")
    return {"success": True, "auto_mode": new_auto}

class TimeSlotsRequest(BaseModel):
    time_slots: List[str]

@app.post("/api/schedule/timeslots")
async def update_time_slots(req: TimeSlotsRequest):
    sched_cfg = config_mgr.get("schedule", {})
    slots = sorted(list(set([s.strip() for s in req.time_slots if s.strip()])))
    sched_cfg["post_time_slots"] = slots
    config_mgr.update({"schedule": sched_cfg})
    task_scheduler.reload_jobs()
    logger.info(f"Đã cập nhật khung giờ hẹn đăng: {', '.join(slots)}", "SCHEDULER")
    return {"success": True, "time_slots": slots}

@app.get("/api/queue/summary")
async def get_queue_summary():
    summary = db.get_queue_summary(slots_per_day=1)
    return {"success": True, "queue": summary}

@app.get("/api/queue/videos")
async def get_queue_videos():
    videos = db.get_pending_videos_list()
    for v in videos:
        fpath = v.get("file_path") or ""
        v["file_exists"] = bool(fpath and os.path.exists(fpath))
        v["filename"] = os.path.basename(fpath) if fpath else ""
        fsize = v.get("file_size") or 0
        v["file_size_mb"] = round(fsize / (1024 * 1024), 2)
    return {"success": True, "videos": videos}

@app.post("/api/videos/{video_id}/open-player")
async def open_video_in_player(video_id: int):
    video = db.get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Không tìm thấy video trong hệ thống.")
    file_path = video.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Tệp video không còn tồn tại trên máy tính (có thể đã bị xóa hoặc dọn dẹp).")
    try:
        if hasattr(os, "startfile"):
            os.startfile(file_path)
        else:
            subprocess.Popen(["xdg-open", file_path])
        return {"success": True, "message": f"Đã mở tệp video: {os.path.basename(file_path)}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể mở tệp video: {str(e)}")

@app.delete("/api/videos/{video_id}/queue")
async def delete_queue_video(video_id: int):
    success = db.remove_video_from_queue(video_id)
    if success:
        logger.info(f"Đã xóa video #{video_id} khỏi kho hàng đợi theo yêu cầu của người dùng.", "QUEUE")
        return {"success": True, "message": f"Đã xóa video #{video_id} khỏi kho hàng đợi."}
    raise HTTPException(status_code=404, detail="Không tìm thấy video hoặc không thể xóa.")

@app.post("/api/action/open-downloads-folder")
async def open_downloads_folder():
    if not os.path.exists(DOWNLOADS_DIR):
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    try:
        if hasattr(os, "startfile"):
            os.startfile(DOWNLOADS_DIR)
        else:
            subprocess.Popen(["xdg-open", DOWNLOADS_DIR])
        return {"success": True, "message": "Đã mở thư mục downloads"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể mở thư mục downloads: {str(e)}")

@app.post("/api/action/open-logs-folder")
async def open_logs_folder():
    logs_dir = logger.get_logs_dir()
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir, exist_ok=True)
    try:
        if hasattr(os, "startfile"):
            os.startfile(logs_dir)
        else:
            subprocess.Popen(["xdg-open", logs_dir])
        return {"success": True, "message": "Đã mở thư mục logs"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể mở thư mục logs: {str(e)}")

@app.get("/api/logs/file")
async def get_log_file_content(lines: int = 500):
    log_path = logger.get_log_file_path()
    if not os.path.exists(log_path):
        return {"success": True, "content": "File log chưa được tạo.", "total_lines": 0}
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {"success": True, "content": "".join(tail_lines), "total_lines": len(all_lines)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Không thể đọc file log: {str(e)}")

@app.get("/api/logs/download")
async def download_log_file():
    from datetime import datetime
    log_path = logger.get_log_file_path()
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="File log chưa tồn tại.")
    return FileResponse(
        log_path,
        media_type="text/plain; charset=utf-8",
        filename=f"app_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

@app.post("/api/action/batch-download-queue")
async def batch_download_queue():
    await require_browser_runtime()
    from automation.workflow_manager import workflow_mgr
    res = await workflow_mgr.batch_download_to_queue(max_items=50)
    return res

@app.get("/api/accounts/status")
async def get_accounts_status():
    from automation.browser_engine import browser_engine
    statuses = await browser_engine.get_login_statuses()
    return {"success": True, "statuses": statuses}


@app.get("/api/system/browser-runtime")
async def get_browser_runtime_status():
    return browser_runtime.status()

@app.post("/api/browser/open-login/{platform}")
async def open_browser_login(platform: str):
    await require_browser_runtime()
    from automation.browser_engine import browser_engine
    try:
        # Run login opener without blocking HTTP request
        asyncio.create_task(browser_engine.open_login_page(platform))
        return {"success": True, "message": f"Đang mở trình duyệt để đăng nhập {platform.upper()}"}
    except Exception as ex:
        return {"success": False, "error": str(ex)}

@app.post("/api/action/send-test-email")
async def send_test_email():
    from core.email_reporter import email_reporter
    success = email_reporter.send_test_email()
    if success:
        return {"success": True, "message": "Đã gửi email kiểm thử thành công tới thv.vinh@gmail.com!"}
    else:
        return {"success": False, "error": "Không thể gửi email kiểm thử. Vui lòng kiểm tra kết nối mạng."}

@app.get("/api/system/version")
async def get_system_version():
    version = get_app_version()
    commit_hash = f"v{version}"
    commit_date = ""
    commit_msg = "Phiên bản mới nhất"
    try:
        res = subprocess.run(["git", "log", "-1", "--format=%h|%cd|%s", "--date=short"], capture_output=True, text=True, cwd=ROOT_DIR, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split("|")
            if len(parts) >= 3:
                commit_hash, commit_date, commit_msg = parts[0], parts[1], parts[2]
    except Exception:
        pass
    return {
        "version": version,
        "commit": commit_hash,
        "date": commit_date,
        "message": commit_msg
    }

@app.get("/api/system/autostart")
async def get_autostart_status():
    return {"enabled": autostart_mgr.is_autostart_enabled()}

class AutoStartRequest(BaseModel):
    enabled: bool

@app.post("/api/system/autostart")
async def toggle_autostart(req: AutoStartRequest):
    if req.enabled:
        success = autostart_mgr.enable_autostart()
    else:
        success = autostart_mgr.disable_autostart()
    return {"success": success, "enabled": autostart_mgr.is_autostart_enabled()}

@app.post("/api/system/update")
async def perform_system_update():
    """Backward-compatible alias for the packaged release updater."""
    return await update_manager.trigger_check()


@app.get("/api/system/update/status")
async def get_system_update_status():
    return {"success": True, **update_manager.status()}


@app.post("/api/system/update/check")
async def check_system_update():
    return await update_manager.trigger_check()

@app.get("/api/logs")
async def get_logs():
    return {"logs": logger.get_recent_logs()}

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    queue = logger.subscribe()
    try:
        for entry in logger.get_recent_logs()[-30:]:
            await websocket.send_json(entry)

        while True:
            log_entry = await queue.get()
            await websocket.send_json(log_entry)
    except (WebSocketDisconnect, ConnectionResetError):
        pass
    except Exception:
        pass
    finally:
        logger.unsubscribe(queue)

# Serve downloads media
@app.get("/media/{filename}")
async def get_media_file(filename: str):
    file_path = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File không tồn tại.")
    return FileResponse(file_path, media_type="video/mp4")

# Serve UI static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"message": "Server đang chạy. Giao diện đang tải..."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
