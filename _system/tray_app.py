import os
import sys

# 1. Khac phuc triet de loi sys.stdout/stderr is None trong PyInstaller --noconsole
class DummyWriter:
    def write(self, s):
        pass
    def flush(self):
        pass
    def isatty(self):
        return False

if sys.stdout is None or not hasattr(sys.stdout, 'write'):
    sys.stdout = DummyWriter()
if sys.stderr is None or not hasattr(sys.stderr, 'write'):
    sys.stderr = DummyWriter()

import time
import threading
import traceback
import webbrowser
import urllib.request
import uvicorn
import pystray
from PIL import Image, ImageDraw

from core.logger import logger
from core.config_manager import ROOT_DIR, SYSTEM_DIR
from core.autostart_manager import autostart_mgr

# Base directory
sys.path.insert(0, SYSTEM_DIR)
sys.path.insert(0, ROOT_DIR)

SAFE_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(levelname)s - %(message)s",
        },
    },
    "handlers": {
        "default": {
            "class": "logging.NullHandler",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO"},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}

class TrayApplication:
    def __init__(self):
        self.server = None
        self.server_thread = None
        self.icon = None
        self._is_running = True

    def create_tray_image(self):
        """Tạo icon khay hệ thống: Đám Mây Tải Lên (Cloud Upload Arrow) màu tím Neon"""
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # 1. Nền tròn màu tím sang trọng (Gradient neon vibe)
        draw.ellipse((2, 2, 62, 62), fill=(124, 58, 237, 255), outline=(168, 85, 247, 255), width=2)
        
        # 2. Vẽ hình Đám Mây (Cloud) phát sáng nhẹ
        draw.ellipse((14, 28, 30, 44), fill=(147, 51, 234, 220))   # Cánh trái
        draw.ellipse((34, 26, 50, 44), fill=(147, 51, 234, 220))   # Cánh phải
        draw.ellipse((22, 18, 42, 40), fill=(168, 85, 247, 240))   # Đỉnh giữa
        draw.rectangle((22, 32, 42, 44), fill=(147, 51, 234, 220)) # Đáy mây

        # 3. Vẽ Mũi Tên Tải Lên (Upload Arrow) màu trắng tinh khôi sắc nét
        arrow_points = [
            (32, 14), # Đỉnh nhọn
            (21, 26), # Cánh trái
            (27, 26), # Khớp trái
            (27, 46), # Chân trái
            (37, 46), # Chân phải
            (37, 26), # Khớp phải
            (43, 26), # Cánh phải
        ]
        draw.polygon(arrow_points, fill=(255, 255, 255, 255), outline=(243, 232, 255, 255))
        
        # 4. Đốm sáng tạo hiệu ứng Neon
        draw.ellipse((46, 10, 52, 16), fill=(236, 72, 153, 255))
        
        return image

    def start_uvicorn(self):
        """Chạy FastAPI uvicorn server với event loop chuẩn trong thread riêng"""
        try:
            import asyncio
            import app as main_app
            config = uvicorn.Config(
                app=main_app.app,
                host="127.0.0.1",
                port=8000,
                log_config=SAFE_LOGGING_CONFIG,
                access_log=False
            )
            self.server = uvicorn.Server(config)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.server.serve())
        except Exception as ex:
            err_msg = traceback.format_exc()
            try:
                err_file = os.path.join(SYSTEM_DIR, "server_error.log")
                with open(err_file, "w", encoding="utf-8") as f:
                    f.write(f"Lỗi khởi chạy máy chủ:\n{str(ex)}\n\nChi tiết:\n{err_msg}")
            except Exception:
                pass

    def wait_and_open_dashboard(self, timeout: float = 15.0):
        """Kiểm tra máy chủ sẵn sàng qua Port Polling trước khi mở trình duyệt"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                req = urllib.request.Request("http://127.0.0.1:8000/api/system/version", headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=1.0) as response:
                    if response.status == 200:
                        logger.success("Máy chủ đã sẵn sàng, đang mở Bảng Điều Khiển...", "SERVER")
                        webbrowser.open("http://127.0.0.1:8000")
                        return
            except Exception:
                pass
            time.sleep(0.4)
        
        # Sau 15s nếu chưa phản hồi vẫn thử mở trình duyệt
        webbrowser.open("http://127.0.0.1:8000")

    def open_dashboard(self, icon=None, item=None):
        """Mở Bảng Điều Khiển trên trình duyệt"""
        webbrowser.open("http://127.0.0.1:8000")

    def toggle_autostart(self, icon=None, item=None):
        """Bật / Tắt khởi động cùng Windows"""
        is_enabled = autostart_mgr.is_autostart_enabled()
        if is_enabled:
            autostart_mgr.disable_autostart()
        else:
            autostart_mgr.enable_autostart()

    def check_update(self, icon=None, item=None):
        """Mở Dashboard và kiểm tra cập nhật"""
        webbrowser.open("http://127.0.0.1:8000#settings")

    def exit_app(self, icon=None, item=None):
        """Thoát ứng dụng an toàn"""
        self._is_running = False
        if self.icon:
            self.icon.stop()
        if self.server:
            self.server.should_exit = True
        os._exit(0)

    def is_autostart_checked(self, item):
        return autostart_mgr.is_autostart_enabled()

    def build_menu(self):
        """Tạo menu chuột phải cho Icon khay hệ thống"""
        return pystray.Menu(
            pystray.MenuItem(
                "🌐 Mở Bảng Điều Khiển",
                self.open_dashboard,
                default=True
            ),
            pystray.MenuItem(
                "🚀 Khởi Động Cùng Windows",
                self.toggle_autostart,
                checked=self.is_autostart_checked
            ),
            pystray.MenuItem(
                "🔄 Kiểm Tra Cập Nhật",
                self.check_update
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "❌ Thoát Ứng Dụng",
                self.exit_app
            )
        )

    def run(self):
        # 1. Khởi động FastAPI server trong thread nền
        self.server_thread = threading.Thread(target=self.start_uvicorn, daemon=True)
        self.server_thread.start()

        # 2. Khởi chạy luồng kiểm tra cổng sẵn sàng và mở Web
        threading.Thread(target=self.wait_and_open_dashboard, daemon=True).start()

        # 3. Chạy System Tray Icon trên luồng chính
        tray_image = self.create_tray_image()
        menu = self.build_menu()
        
        self.icon = pystray.Icon(
            "AutoVideoPro",
            tray_image,
            "Tự động đăng video - Đang chạy ngầm",
            menu=menu
        )

        # Chạy vòng lặp tray icon
        self.icon.run()

if __name__ == "__main__":
    app_tray = TrayApplication()
    app_tray.run()
