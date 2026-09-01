import os
import sys
import time
import threading
import webbrowser
import uvicorn
import pystray
from PIL import Image, ImageDraw
from core.logger import logger
from core.autostart_manager import autostart_mgr

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

class TrayApplication:
    def __init__(self):
        self.server = None
        self.server_thread = None
        self.icon = None
        self._is_running = True

    def create_tray_image(self):
        """Tạo icon khay hệ thống đẹp mắt với hình tên lửa / video"""
        width = 64
        height = 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Vẽ nền tròn gradient tím xanh
        draw.ellipse((4, 4, 60, 60), fill=(99, 102, 241, 255), outline=(129, 140, 248, 255), width=2)
        
        # Vẽ hình tam giác Play / Rocket
        points = [(24, 18), (24, 46), (48, 32)]
        draw.polygon(points, fill=(255, 255, 255, 255))
        
        # Vẽ đốm sáng nhỏ
        draw.ellipse((42, 16, 48, 22), fill=(236, 72, 153, 255))
        
        return image

    def start_uvicorn(self):
        """Chạy FastAPI uvicorn server"""
        from app import app
        config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, log_level="warning", access_log=False)
        self.server = uvicorn.Server(config)
        self.server.run()

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

        # 2. Chờ 1.5 giây để server sẵn sàng và mở Dashboard
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8000")

        # 3. Chạy System Tray Icon trên luồng chính
        tray_image = self.create_tray_image()
        menu = self.build_menu()
        
        self.icon = pystray.Icon(
            "AutoVideoPro",
            tray_image,
            "Tự động đăng video - Đang chạy ngầm",
            menu=menu
        )

        # Chạy tray icon
        self.icon.run()

if __name__ == "__main__":
    app_tray = TrayApplication()
    app_tray.run()
