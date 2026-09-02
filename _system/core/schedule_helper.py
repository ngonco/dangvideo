from datetime import datetime, timedelta
from typing import Any, Dict

from core.config_manager import config_mgr


def get_native_schedule(time_override: str = "") -> Dict[str, Any]:
    """Mốc hẹn native trên nền tảng: 10:00 sáng mai (máy local / VN).

    Video được tải lên NGAY, nhưng chỉ hiện công khai lúc mốc này —
    máy tắt vẫn lên bài vì lịch nằm trên YouTube/TikTok/Facebook.
    Instagram web không hẹn giờ: chia sẻ ngay, cách tối thiểu 3 tiếng khi chạy thật.
    """
    cfg = config_mgr.get("schedule_publish", {}) or {}
    time_str = str(time_override or cfg.get("default_time") or "10:00").strip()
    target_date = str(cfg.get("target_date") or "tomorrow").strip().lower()
    enabled = cfg.get("enabled", True)

    try:
        hour, minute = [int(x) for x in time_str.split(":")[:2]]
    except Exception:
        hour, minute = 10, 0
        time_str = "10:00"

    now = datetime.now()
    if target_date in ("today", "hom_nay"):
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
    else:
        target = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)

    time_12h = target.strftime("%I:%M %p").lstrip("0")
    if time_12h.startswith(": "):
        time_12h = target.strftime("%I:%M %p")

    return {
        "enabled": bool(enabled),
        "datetime": target,
        "time": f"{hour:02d}:{minute:02d}",
        "hour": hour,
        "minute": minute,
        "day": target.day,
        "month": target.month,
        "year": target.year,
        "date_iso": target.strftime("%Y-%m-%d"),
        "date_dmy": target.strftime("%d/%m/%Y"),
        "date_us": target.strftime("%b %d, %Y"),
        "time_12h": time_12h,
        "time_12h_no_pad": target.strftime("%-I:%M %p") if False else f"{target.hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}",
        "label": f"{target.strftime('%d/%m/%Y')} {hour:02d}:{minute:02d}",
    }


def get_instagram_min_gap_hours() -> float:
    """Khoảng cách tối thiểu giữa 2 lần đăng Instagram (chạy thật). Test không dùng."""
    ig_cfg = (config_mgr.get("platforms", {}) or {}).get("instagram", {}) or {}
    if ig_cfg.get("min_gap_hours") is not None:
        try:
            return float(ig_cfg.get("min_gap_hours"))
        except (TypeError, ValueError):
            pass
    mins = (config_mgr.get("schedule", {}) or {}).get("min_delay_between_posts_minutes", 180)
    try:
        return float(mins) / 60.0
    except (TypeError, ValueError):
        return 3.0
