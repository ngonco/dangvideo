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
from core.config_manager import config_mgr
from core.autostart_manager import autostart_mgr
from automation.workflow_manager import workflow_mgr
from scheduler.task_scheduler import task_scheduler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start scheduler if auto mode enabled
    logger.info("Khởi động hệ thống Auto Đăng Video...", "SERVER")
    task_scheduler.start()
    yield
    # Shutdown: Stop scheduler & close browser
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
    custom_caption: Optional[Dict[str, Any]] = None

class PostVideoRequest(BaseModel):
    video_id: int
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
    stats["max_posts_per_day"] = sched_cfg.get("max_posts_per_day", 3)
    stats["is_busy"] = workflow_mgr.is_busy
    return stats

@app.get("/api/videos")
async def get_videos(limit: int = 50, offset: int = 0):
    videos = db.list_videos(limit=limit, offset=offset)
    return {"videos": videos}

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
    config_mgr.update(updates)
    task_scheduler.reload_jobs()
    logger.info("Đã cập nhật cấu hình hệ thống.", "CONFIG")
    return {"success": True, "config": config_mgr.config}

@app.post("/api/action/scan")
async def trigger_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    if workflow_mgr.is_busy:
        raise HTTPException(status_code=400, detail="Hệ thống đang bận thực hiện tác vụ khác.")
    
    background_tasks.add_task(workflow_mgr.scan_and_download, req.max_items, req.force_latest)
    mode_text = "Test ép tải video mới nhất" if req.force_latest else "Quét video 'Chưa tải xuống'"
    return {"success": True, "message": f"Đã bắt đầu {mode_text} trong nền."}

@app.post("/api/action/post")
async def trigger_post(req: PostVideoRequest, background_tasks: BackgroundTasks):
    if workflow_mgr.is_busy:
        raise HTTPException(status_code=400, detail="Hệ thống đang bận thực hiện tác vụ khác.")
    
    video = db.get_video_by_id(req.video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Không tìm thấy video.")

    background_tasks.add_task(workflow_mgr.publish_video_to_platforms, req.video_id, req.target_platforms)
    return {"success": True, "message": f"Đã bắt đầu đăng video #{req.video_id} lên các nền tảng."}

@app.post("/api/action/cleanup")
async def trigger_cleanup():
    cleanup_cfg = config_mgr.get("cleanup", {})
    retention_days = cleanup_cfg.get("retention_days", 2)
    res = db.clean_old_posted_videos(retention_days=retention_days)
    logger.info(f"Thực hiện dọn dẹp thủ công: Đã xóa {res['deleted_count']} video cũ (> {retention_days} ngày), giải phóng {res['freed_mb']} MB.", "CLEANUP")
    return {"success": True, "results": res}

@app.post("/api/action/open-login")
async def open_login(req: OpenLoginRequest, background_tasks: BackgroundTasks):
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

@app.get("/api/system/version")
async def get_system_version():
    commit_hash = "v1.0.0"
    commit_date = ""
    commit_msg = "Phiên bản mới nhất"
    try:
        res = subprocess.run(["git", "log", "-1", "--format=%h|%cd|%s", "--date=short"], capture_output=True, text=True, cwd=BASE_DIR, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split("|")
            if len(parts) >= 3:
                commit_hash, commit_date, commit_msg = parts[0], parts[1], parts[2]
    except Exception:
        pass
    return {
        "version": "1.0.0",
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
    logger.info("Bắt đầu kiểm tra và cập nhật mã nguồn từ GitHub...", "UPDATE")
    try:
        res = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True, cwd=BASE_DIR, timeout=40)
        output = (res.stdout or "") + (res.stderr or "")
        if res.returncode == 0:
            if "Already up to date" in output or "Already up-to-date" in output:
                logger.success("Hệ thống đã ở phiên bản mới nhất!", "UPDATE")
                return {"success": True, "message": "Hệ thống đã ở phiên bản mới nhất!", "output": output}
            else:
                logger.success(f"Đã cập nhật thành công bản mới từ GitHub:\n{output}", "UPDATE")
                return {"success": True, "message": "Đã cập nhật thành công bản mới từ GitHub!", "output": output}
        else:
            logger.error(f"Lỗi khi kéo mã nguồn từ GitHub: {output}", "UPDATE")
            return {"success": False, "error": output}
    except Exception as ex:
        logger.error(f"Lỗi ngoại lệ khi cập nhật: {str(ex)}", "UPDATE")
        return {"success": False, "error": str(ex)}

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
    except WebSocketDisconnect:
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
