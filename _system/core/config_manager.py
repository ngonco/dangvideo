import json
import os
from typing import Dict, Any

import sys

# Dynamic Path Resolution supporting PyInstaller frozen mode and _system/ directory structure
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(os.path.abspath(sys.executable))
    SYSTEM_DIR = os.path.join(ROOT_DIR, "_system")
    if not os.path.exists(SYSTEM_DIR):
        SYSTEM_DIR = ROOT_DIR
else:
    CURR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.basename(CURR_DIR) == "_system":
        SYSTEM_DIR = CURR_DIR
        ROOT_DIR = os.path.dirname(CURR_DIR)
    else:
        SYSTEM_DIR = CURR_DIR
        ROOT_DIR = CURR_DIR

DOWNLOADS_DIR = os.path.join(ROOT_DIR, "downloads")
PROFILES_DIR = os.path.join(SYSTEM_DIR, "browser_profiles")
CONFIG_PATH = os.path.join(SYSTEM_DIR, "config.json")
DB_PATH = os.path.join(SYSTEM_DIR, "data.db")
VERSION_PATH = os.path.join(SYSTEM_DIR, "VERSION")


def get_app_version() -> str:
    """Đọc phiên bản từ _system/VERSION (cả khi chạy .exe PyInstaller)."""
    candidates = [os.path.join(SYSTEM_DIR, "VERSION"), os.path.join(ROOT_DIR, "VERSION")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.insert(0, os.path.join(meipass, "VERSION"))
    for path in candidates:
        if os.path.isfile(path):
            try:
                value = open(path, encoding="utf-8").read().strip().split()[0]
                if value:
                    return value
            except Exception:
                continue
    return "0.0.0"

DEFAULT_CONFIG = {
    "hatbuinho": {
        "url": "https://hatbuinho.com/",
        "username": "",
        "password": "",
        "auto_login": True
    },
    "platforms": {
        "youtube": {"enabled": True, "privacy": "public", "mark_ai": True, "name": "YouTube Shorts"},
        "tiktok": {"enabled": True, "privacy": "public", "mark_ai": True, "name": "TikTok"},
        "facebook": {"enabled": True, "target_type": "professional_dashboard", "page_name": "", "mark_ai": True, "name": "Facebook Reels"},
        "instagram": {"enabled": True, "share_to_feed": True, "mark_ai": True, "min_gap_hours": 3, "name": "Instagram Reels"}
    },
    "schedule": {
        "auto_mode": True,
        "max_posts_per_day": 1,
        "post_time_slots": ["08:00", "11:30", "19:30"],
        "min_delay_between_posts_minutes": 180
    },
    "browser": {
        "headless": True,
        "mute_audio": True,
        "user_data_dir": "browser_profiles/camoufox"
    },
        "schedule_publish": {
            "enabled": True,
            "default_time": "10:00",
            "target_date": "tomorrow"
        },
    "custom_caption": {
        "prefix_text": "",
        "append_text": ""
    }
}

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    res = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(res.get(k), dict):
            res[k] = _deep_merge(res[k], v)
        else:
            res[k] = v
    return res

class ConfigManager:
    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self._config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return _deep_merge(DEFAULT_CONFIG, data)
        except Exception:
            return DEFAULT_CONFIG.copy()

    def save_config(self, new_config: Dict[str, Any]):
        self._config = new_config
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_platform_config(self, platform_name: str) -> Dict[str, Any]:
        platforms = self._config.get("platforms", {})
        return platforms.get(platform_name, {})

    def update(self, updates: Dict[str, Any]):
        self._config = _deep_merge(self._config, updates)
        self.save_config(self._config)

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

config_mgr = ConfigManager()
config_manager = config_mgr
