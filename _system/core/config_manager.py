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

DEFAULT_CONFIG = {
    "hatbuinho": {
        "url": "https://hatbuinho.com/",
        "username": "cun",
        "password": "123",
        "auto_login": True
    },
    "platforms": {
        "youtube": {"enabled": True, "privacy": "public", "mark_ai": True, "name": "YouTube Shorts"},
        "tiktok": {"enabled": True, "privacy": "public", "mark_ai": True, "name": "TikTok"},
        "facebook": {"enabled": True, "target_type": "page", "page_name": "", "mark_ai": True, "name": "Facebook Reels"},
        "instagram": {"enabled": True, "share_to_feed": True, "mark_ai": True, "name": "Instagram Reels"}
    },
    "schedule": {
        "auto_mode": False,
        "max_posts_per_day": 3,
        "post_time_slots": ["08:00", "11:30", "19:30"],
        "scan_interval_minutes": 60,
        "min_delay_between_posts_minutes": 60
    },
    "browser": {
        "headless": False,
        "user_data_dir": "browser_profiles/default"
    },
    "custom_caption": {
        "prefix_text": "",
        "append_text": "\n#hatbuinho #dao_duc #song_dep #tam_hon"
    }
}

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
                return data
        except Exception:
            return DEFAULT_CONFIG.copy()

    def save_config(self, new_config: Dict[str, Any]):
        self._config = new_config
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def update(self, updates: Dict[str, Any]):
        self._config.update(updates)
        self.save_config(self._config)

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

config_mgr = ConfigManager()
