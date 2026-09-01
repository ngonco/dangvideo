import json
import os
from typing import Dict, Any

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

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
