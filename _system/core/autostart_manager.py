import os
import sys
import subprocess
from core.logger import logger
from core.config_manager import ROOT_DIR, SYSTEM_DIR

class AutoStartManager:
    def __init__(self):
        self.app_dir = ROOT_DIR
        self.startup_dir = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        )
        self.shortcut_path = os.path.join(self.startup_dir, "AutoVideoPro.lnk")
        self.exe_target = os.path.join(ROOT_DIR, "Tu_dong_dang_video.exe")
        self.vbs_target = os.path.join(SYSTEM_DIR, "run_hidden.vbs")
        self.bat_target = os.path.join(SYSTEM_DIR, "run.bat")

    def is_autostart_enabled(self) -> bool:
        """Kiểm tra xem shortcut khởi động cùng Windows đã tồn tại chưa"""
        return os.path.exists(self.shortcut_path)

    def enable_autostart(self) -> bool:
        """Tạo shortcut khởi động cùng Windows trỏ tới Tu_dong_dang_video.exe hoặc run_hidden.vbs"""
        try:
            os.makedirs(self.startup_dir, exist_ok=True)
            
            # Ưu tiên chạy qua Tu_dong_dang_video.exe nếu có
            if os.path.exists(self.exe_target):
                target = self.exe_target
            elif os.path.exists(self.vbs_target):
                target = self.vbs_target
            else:
                target = self.bat_target
            
            # Sử dụng PowerShell để tạo file .lnk Windows Shortcut chuẩn xác
            ps_script = f"""
            $WshShell = New-Object -ComObject WScript.Shell;
            $Shortcut = $WshShell.CreateShortcut('{self.shortcut_path}');
            $Shortcut.TargetPath = '{target}';
            $Shortcut.WorkingDirectory = '{self.app_dir}';
            $Shortcut.Description = 'Auto Video Pro - Tu dong dang video';
            $Shortcut.Save();
            """
            
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if res.returncode == 0 and os.path.exists(self.shortcut_path):
                logger.success(f"Đã bật tự động khởi động cùng Windows (Shortcut: {self.shortcut_path})", "AUTOSTART")
                return True
            else:
                logger.error(f"Lỗi khi tạo shortcut khởi động: {res.stderr}", "AUTOSTART")
                return False
        except Exception as ex:
            logger.error(f"Lỗi ngoại lệ khi bật autostart: {str(ex)}", "AUTOSTART")
            return False

    def disable_autostart(self) -> bool:
        """Xóa shortcut khởi động cùng Windows"""
        try:
            if os.path.exists(self.shortcut_path):
                os.remove(self.shortcut_path)
                logger.info("Đã tắt tự động khởi động cùng Windows.", "AUTOSTART")
            return True
        except Exception as ex:
            logger.error(f"Lỗi khi xóa shortcut khởi động: {str(ex)}", "AUTOSTART")
            return False

autostart_mgr = AutoStartManager()
