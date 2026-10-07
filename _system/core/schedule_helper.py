from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from core.config_manager import config_mgr
from core.posting_store import local_now


def get_next_post_time_slot(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Tính mốc giờ đăng tiếp theo dựa trên post_time_slots do user cài đặt.
    Nếu hôm nay còn mốc giờ chưa tới (cách giờ hiện tại ít nhất 20 phút), dùng mốc hôm nay.
    Nếu đã qua hết các mốc hôm nay, lấy mốc đầu tiên của ngày mai.
    """
    if now is None:
        now = local_now()
    sched_cfg = config_mgr.get("schedule", {}) or {}
    slots = sched_cfg.get("post_time_slots") or []
    
    sorted_slots = []
    for s in slots:
        try:
            h, m = [int(x) for x in str(s).strip().split(":")[:2]]
            if 0 <= h < 24 and 0 <= m < 60:
                sorted_slots.append((h, m, f"{h:02d}:{m:02d}"))
        except Exception:
            pass
    sorted_slots.sort()
    if not sorted_slots:
        cfg = config_mgr.get('schedule_publish', {})
        try:
            hour, minute = map(int, cfg.get('default_time', '10:00').split(':'))
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, TypeError):
            target = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if cfg.get('target_date', 'tomorrow') != 'today' or target < now + timedelta(minutes=20):
            target += timedelta(days=1)
        return {'datetime':target, 'time':target.strftime('%H:%M'), 'target_date':target.date().isoformat(), 'label':target.strftime('%d/%m/%Y %H:%M'), 'is_today':target.date()==now.date()}

    buffer_now = now + timedelta(minutes=20)
    for h, m, slot_str in sorted_slots:
        cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand >= buffer_now:
            return {
                "datetime": cand,
                "time": slot_str,
                "target_date": "today",
                "label": f"{slot_str} - Hôm nay ({cand.strftime('%d/%m')})",
                "is_today": True
            }

    first_h, first_m, first_slot_str = sorted_slots[0]
    cand_tomorrow = (now + timedelta(days=1)).replace(hour=first_h, minute=first_m, second=0, microsecond=0)
    return {
        "datetime": cand_tomorrow,
        "time": first_slot_str,
        "target_date": "tomorrow",
        "label": f"{first_slot_str} - Ngày mai ({cand_tomorrow.strftime('%d/%m')})",
        "is_today": False
    }


def get_available_slot_options(now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Trả về toàn bộ danh sách các khung giờ hợp lệ tính từ post_time_slots do user cài đặt,
    được phân loại xem mốc nào là hôm nay hay ngày mai, và mốc nào là mốc khuyến nghị tiếp theo."""
    if now is None:
        now = local_now()
    sched_cfg = config_mgr.get("schedule", {}) or {}
    slots = sched_cfg.get("post_time_slots") or []
    
    sorted_slots = []
    for s in slots:
        try:
            h, m = [int(x) for x in str(s).strip().split(":")[:2]]
            sorted_slots.append((h, m, f"{h:02d}:{m:02d}"))
        except Exception:
            pass
    sorted_slots.sort()
    if not sorted_slots:
        fallback = get_next_post_time_slot(now)
        return [{'time':fallback['time'], 'target_date':fallback['target_date'], 'datetime_iso':fallback['datetime'].isoformat(), 'label':fallback['label'], 'is_recommended':True}]

    next_slot = get_next_post_time_slot(now)
    buffer_now = now + timedelta(minutes=20)
    
    options = []
    for h, m, slot_str in sorted_slots:
        cand_today = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand_today >= buffer_now:
            is_rec = (slot_str == next_slot["time"] and next_slot["is_today"])
            options.append({
                "time": slot_str,
                "target_date": "today",
                "datetime_iso": cand_today.isoformat(),
                "label": f"{slot_str} - Hôm nay ({cand_today.strftime('%d/%m')})",
                "is_recommended": is_rec
            })
        else:
            cand_tom = (now + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
            is_rec = (slot_str == next_slot["time"] and not next_slot["is_today"])
            options.append({
                "time": slot_str,
                "target_date": "tomorrow",
                "datetime_iso": cand_tom.isoformat(),
                "label": f"{slot_str} - Ngày mai ({cand_tom.strftime('%d/%m')})",
                "is_recommended": is_rec
            })

    # Đảm bảo mốc khuyến nghị nằm đầu tiên
    options.sort(key=lambda x: (not x["is_recommended"], x["datetime_iso"]))
    return options


def get_native_schedule(
    time_override: str = "",
    target_date_override: Optional[str] = None
) -> Dict[str, Any]:
    """Mốc hẹn native trên nền tảng (YouTube / TikTok / Facebook).
    
    Nếu có time_override và target_date_override thì áp dụng chính xác.
    Nếu không có override: Tự động dùng mốc giờ tiếp theo từ post_time_slots của user
    (nếu hôm nay còn kịp mốc thì hôm nay, nếu qua rồi thì mốc đầu tiên ngày mai).
    """
    now = local_now()
    cfg = config_mgr.get("schedule_publish", {}) or {}
    enabled = cfg.get("enabled", True)

    time_override = (time_override or "").strip()
    target_date_override = (target_date_override or "").strip() if target_date_override else None

    if not time_override and not target_date_override:
        next_slot = get_next_post_time_slot(now)
        target = next_slot["datetime"]
        hour = target.hour
        minute = target.minute
        time_str = next_slot["time"]
    else:
        time_str = str(time_override or cfg.get("default_time") or "10:00").strip()
        try:
            hour, minute = [int(x) for x in time_str.split(":")[:2]]
        except Exception:
            hour, minute = 10, 0
            time_str = "10:00"

        if target_date_override:
            target_date = str(target_date_override).strip().lower()
        else:
            # Tự động nhận diện: nếu hôm nay còn kịp (cách ít nhất 20 phút) thì là hôm nay, ngược lại ngày mai
            cand_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if cand_today >= now + timedelta(minutes=20):
                target_date = "today"
            else:
                target_date = "tomorrow"

        if target_date in ("today", "hom_nay"):
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
        elif target_date in ("tomorrow", "ngay_mai"):
            target = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        else:
            try:
                target = datetime.fromisoformat(target_date).replace(hour=hour, minute=minute, second=0, microsecond=0)
            except Exception:
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
        "time_12h_no_pad": f"{target.hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}",
        "label": f"{target.strftime('%d/%m/%Y')} {hour:02d}:{minute:02d}",
    }


def get_instagram_min_gap_hours() -> float:
    """Khoảng cách tối thiểu giữa 2 lần đăng Instagram (chạy thật)."""
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
