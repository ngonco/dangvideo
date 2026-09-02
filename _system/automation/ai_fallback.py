import os
import re
import json
import base64
import asyncio
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

from core.logger import logger
from core.config_manager import SYSTEM_DIR

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(SYSTEM_DIR, ".env"))
except Exception:
    pass

SCREENSHOT_DIR = os.path.join(SYSTEM_DIR, "debug_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

SCHEDULE_GOAL = (
    "Mục tiêu: tải video lên (nếu chưa có), điền tiêu đề/caption, "
    "hẹn native CÔNG KHAI lúc 10:00 SÁNG MAI trên nền tảng. "
    "KHÔNG bấm Đăng/Post/Share/Publish ngay lập tức. "
    "Chỉ bấm Schedule / Lên lịch / Done khi đã chọn ngày mai 10:00. "
    "Đóng popup cản trở (Got it, Discard bản nháp, Not now, Đã đọc). "
    "KHÔNG xóa video, KHÔNG đổi mật khẩu, KHÔNG captcha/2FA (nếu gặp thì abort)."
)

DOWNLOAD_GOAL = (
    "Mục tiêu: đóng overlay Đã đọc, bấm nút Video (#btn_view_history), tab Đã xong, "
    "mở video Chưa tải xuống, bấm Tải xuống rồi Tải xuống 2. Không xóa video."
)

INSTAGRAM_SHARE_GOAL = (
    "Mục tiêu: tạo Bài viết / Post (không Story, không Reel), đính video, 2 lần Tiếp / Next, "
    "điền chú thích, bấm Chia sẻ / Share ngay (Instagram web không có Lên lịch). "
    "Không bật switch, không Cài đặt nâng cao, không sheet Chia sẻ bài viết. "
    "Sau Xong / Done: mở video đầu trên profile, lấy permalink từ thanh địa chỉ (/p/ hoặc /reel/). "
    "Không xóa video, không đổi mật khẩu, không captcha/2FA."
)

_FORBIDDEN_TEXT = (
    "xóa video", "xoá video", "delete video", "delete", "change password",
    "đổi mật khẩu", "logout", "đăng xuất",
)
_FORBIDDEN_PUBLISH_EXACT = {"đăng", "post", "share", "publish", "chia sẻ"}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def get_ai_config() -> Dict[str, str]:
    return {
        "api_key": _env("VILAO_API_KEY"),
        "base_url": _env("VILAO_BASE_URL", "https://api.vilao.ai/v1"),
        "model": _env("VILAO_MODEL", "anxs/gemini-3.7-flash-high"),
    }


def _parse_json_payload(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}


async def _snapshot_page(page: Page, platform: str, step: int) -> Dict[str, Any]:
    shot_path = os.path.join(SCREENSHOT_DIR, f"ai_{platform}_{step}.png")
    b64 = ""
    try:
        await page.screenshot(path=shot_path, full_page=False)
        with open(shot_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as ex:
        logger.warning(f"Không chụp được screenshot AI: {ex}", "AI")

    dom = {"url": page.url, "title": "", "buttons": []}
    try:
        dom = await page.evaluate(
            """() => {
                const buttons = Array.from(document.querySelectorAll(
                    'button, a, [role="button"], [role="tab"], [role="menuitem"], [role="radio"], [role="option"], input, textarea, [contenteditable="true"]'
                )).map(el => ({
                    tag: el.tagName,
                    id: el.id || '',
                    aria: el.getAttribute('aria-label') || '',
                    name: el.getAttribute('name') || '',
                    type: el.getAttribute('type') || '',
                    text: ((el.innerText || el.value || '') + '').trim().slice(0, 80)
                })).filter(x => x.text || x.id || x.aria).slice(0, 60);
                return {
                    url: location.href,
                    title: document.title || '',
                    body: (document.body.innerText || '').slice(0, 2500),
                    buttons
                };
            }"""
        )
    except Exception as ex:
        logger.warning(f"Không đọc được DOM AI: {ex}", "AI")

    return {"screenshot_path": shot_path, "b64": b64, "dom": dom}


def _is_forbidden(action: str, text: str, selector: str, platform: str = "") -> bool:
    blob = f"{text} {selector}".lower().strip()
    if not blob:
        return False
    if any(k in blob for k in _FORBIDDEN_TEXT):
        return True
    if action in ("click_text", "click_selector") and blob in _FORBIDDEN_PUBLISH_EXACT:
        if platform == "instagram" and blob in ("share", "chia sẻ"):
            return False
        return True
    return False


async def _execute_action(page: Page, payload: Dict[str, Any], platform: str = "") -> str:
    action = (payload.get("action") or "").strip().lower()
    text = (payload.get("text") or "").strip()
    selector = (payload.get("selector") or "").strip()
    key = (payload.get("key") or "").strip()
    seconds = payload.get("seconds") or 1
    try:
        seconds = float(seconds)
    except Exception:
        seconds = 1.0

    if _is_forbidden(action, text, selector, platform):
        return f"blocked_guardrail:{text or selector}"

    if action == "wait":
        await asyncio.sleep(min(max(seconds, 0.3), 8))
        return "waited"

    if action == "press" and key:
        await page.keyboard.press(key)
        await asyncio.sleep(0.4)
        return f"pressed:{key}"

    if action == "type" and text:
        target = None
        if selector:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                target = loc
        if target is None:
            target = page.locator('input:visible, textarea, [contenteditable="true"]').first
        try:
            await target.click(force=True, timeout=4000)
        except Exception:
            pass
        await page.keyboard.press("Control+A")
        await page.keyboard.type(text, delay=30)
        return f"typed:{text[:40]}"

    if action == "click_selector" and selector:
        loc = page.locator(selector).first
        await loc.click(force=True, timeout=8000)
        await asyncio.sleep(0.6)
        return f"clicked_selector:{selector}"

    if action == "click_text" and text:
        clicked = await page.evaluate(
            """(needle) => {
                const n = (needle || '').toLowerCase().trim();
                const els = Array.from(document.querySelectorAll('button, a, [role="button"], [role="tab"], [role="menuitem"], span, div'));
                const hit = els.find(el => {
                    const t = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '')).trim().toLowerCase();
                    return t === n || t.includes(n);
                });
                if (hit) { hit.click(); return true; }
                return false;
            }""",
            text,
        )
        await asyncio.sleep(0.6)
        return "clicked_text" if clicked else f"click_text_miss:{text}"

    return f"unknown_action:{action}"


def _call_vilao(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = get_ai_config()
    if not cfg["api_key"]:
        return {"recoverable": False, "action": "abort", "reason": "Thiếu VILAO_API_KEY trong _system/.env"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=messages,
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "") if resp.choices else ""
        parsed = _parse_json_payload(raw)
        if not parsed:
            return {"recoverable": False, "action": "abort", "reason": f"AI không trả JSON hợp lệ: {raw[:300]}"}
        return parsed
    except Exception as ex:
        logger.error(f"Lỗi gọi Vilao API: {ex}", "AI")
        return {"recoverable": False, "action": "abort", "reason": f"Lỗi API Vilao: {ex}"}


_BANNED_HASHTAGS = {
    "hatbuinho", "hat_bui_nho", "hatbuinho.com",
    "auto_dang_video", "tu_dong_dang_video", "tudongdangvideo",
}


def _normalize_hashtag(raw: str) -> str:
    t = (raw or "").strip()
    if t.startswith("#"):
        t = t[1:]
    t = re.sub(r"[^A-Za-z0-9_]", "", t)
    if not t:
        return ""
    return "#" + t.lower()


def suggest_popular_hashtags(title: str, script_text: str, existing: str, count: int = 5) -> List[str]:
    """Chọn 3–5 hashtag phổ biến khớp nội dung. Thiếu key / lỗi → [] (không chặn tải)."""
    cfg = get_ai_config()
    if not cfg["api_key"]:
        logger.warning("Thiếu VILAO_API_KEY — bỏ qua hashtag AI, chỉ dùng kho đạo lý.", "HASHTAG")
        return []

    existing_tags = [t for t in (existing or "").split() if t.startswith("#")]
    system_prompt = (
        "Bạn chọn hashtag cho video ngắn Việt Nam (YouTube Shorts, TikTok, Reels).\n"
        "Chỉ trả JSON thuần: {\"hashtags\": [\"#tag1\", \"#tag2\"]}.\n"
        f"Đúng {min(max(count, 3), 5)} hashtag phổ biến, đang được search nhiều, khớp nội dung.\n"
        "Chữ thường, không dấu hoặc dạng người dùng hay gõ (vd #daycon #giadinh #shorts).\n"
        "Không thương hiệu (hatbuinho, tên app, tên kênh). Không trùng các tag đã có.\n"
        "Không hashtag vô nghĩa, không chính trị, không spam."
    )
    user_text = (
        f"Tiêu đề: {(title or '')[:400]}\n"
        f"Kịch bản: {(script_text or '')[:1800]}\n"
        f"Hashtag đạo lý đã có (không trùng): {existing or '(không)'}\n"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    try:
        payload = _call_vilao(messages)
    except Exception as ex:
        logger.warning(f"Không gọi được AI hashtag: {ex}", "HASHTAG")
        return []

    raw_tags = payload.get("hashtags") if isinstance(payload, dict) else None
    if not isinstance(raw_tags, list):
        logger.warning(f"AI hashtag không trả mảng hợp lệ: {str(payload)[:200]}", "HASHTAG")
        return []

    existing_keys = {t.lower() for t in existing_tags}
    out: List[str] = []
    for item in raw_tags:
        tag = _normalize_hashtag(str(item))
        if not tag or len(tag) < 3:
            continue
        key = tag.lower()
        stem = key[1:]
        if stem in _BANNED_HASHTAGS or key in existing_keys:
            continue
        if key in {t.lower() for t in out}:
            continue
        out.append(tag)
        if len(out) >= 5:
            break
    return out[:5]


async def diagnose_and_recover(
    page: Page,
    platform: str,
    error: str,
    goal: Optional[str] = None,
    max_steps: int = 8,
) -> Dict[str, Any]:
    """Chẩn đoán lỗi UI; sửa được thì thực hiện tối đa 8 bước. Không được thì abort."""
    goal = goal or SCHEDULE_GOAL
    cfg = get_ai_config()
    if not cfg["api_key"]:
        logger.warning("Thiếu VILAO_API_KEY — bỏ qua AI recover.", "AI")
        return {
            "ok": False,
            "diagnosis": "Thiếu VILAO_API_KEY trong _system/.env — không thể nhờ AI xử lý. Lỗi gốc: " + error,
            "screenshot": "",
        }

    system_prompt = (
        "Bạn là trợ lý tự động hóa trình duyệt. Chỉ trả về JSON thuần, không markdown.\n"
        "Schema: {\"recoverable\": bool, \"reason\": str, \"action\": "
        "\"click_text\"|\"click_selector\"|\"type\"|\"press\"|\"wait\"|\"done\"|\"abort\", "
        "\"text\": str, \"selector\": str, \"key\": str, \"seconds\": number}\n"
        "recoverable=false hoặc action=abort khi: captcha, 2FA, daily upload limit, "
        "không có cách hẹn giờ, cần người dùng, hoặc không an toàn.\n"
        "action=done khi mục tiêu đã hoàn tất (đã lên lịch 10:00 sáng mai / đã tải xong).\n"
        f"Nền tảng: {platform}. {goal}"
    )

    last_result = "start"
    last_shot = ""
    for step in range(1, max_steps + 1):
        snap = await _snapshot_page(page, platform, step)
        last_shot = snap.get("screenshot_path") or ""
        buttons = snap["dom"].get("buttons") or []
        user_text = (
            f"Lỗi gốc: {error}\n"
            f"Kết quả bước trước: {last_result}\n"
            f"URL: {snap['dom'].get('url')}\n"
            f"Title: {snap['dom'].get('title')}\n"
            f"Nút/ô trên trang: {json.dumps(buttons, ensure_ascii=False)[:3500]}\n"
            f"Text trang: {(snap['dom'].get('body') or '')[:1800]}\n"
            "Hãy chẩn đoán và ra ĐÚNG MỘT action tiếp theo."
        )
        content: Any = [{"type": "text", "text": user_text}]
        if snap.get("b64"):
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{snap['b64']}"},
            })
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]
        logger.info(f"AI bước {step}/{max_steps} trên {platform}: gửi chẩn đoán...", "AI")
        payload = await asyncio.to_thread(_call_vilao, messages)
        reason = payload.get("reason") or ""
        action = (payload.get("action") or "").lower()
        recoverable = payload.get("recoverable")
        logger.info(f"AI {platform} bước {step}: action={action} recoverable={recoverable} — {reason}", "AI")

        if recoverable is False or action == "abort":
            diagnosis = reason or error
            logger.error(f"AI không xử lý được {platform}: {diagnosis}", "AI")
            return {"ok": False, "diagnosis": diagnosis, "screenshot": last_shot}

        if action == "done":
            logger.success(f"AI xác nhận đã xử lý xong {platform}: {reason}", "AI")
            return {"ok": True, "diagnosis": reason or "AI hoàn tất mục tiêu", "screenshot": last_shot, "url": page.url}

        last_result = await _execute_action(page, payload, platform)
        logger.info(f"AI đã thực thi: {last_result}", "AI")
        await asyncio.sleep(1.2)

    return {
        "ok": False,
        "diagnosis": f"AI hết {max_steps} bước vẫn chưa xong. Lỗi gốc: {error}",
        "screenshot": last_shot,
    }


async def fail_with_ai(
    page: Page,
    platform: str,
    error: str,
    goal: Optional[str] = None,
) -> Dict[str, Any]:
    """Gọi khi script fail: recover được → success; không thì trả error + chẩn đoán."""
    recovered = await diagnose_and_recover(page, platform, error, goal=goal)
    if recovered.get("ok"):
        return {
            "success": True,
            "url": recovered.get("url") or "",
            "error": "",
            "ai_recovered": True,
            "ai_diagnosis": recovered.get("diagnosis", ""),
        }
    diagnosis = recovered.get("diagnosis") or error
    shot = recovered.get("screenshot") or ""
    details = f"{diagnosis}"
    if shot:
        details += f"\nScreenshot: {shot}"
    return {
        "success": False,
        "url": "",
        "error": diagnosis,
        "ai_recovered": False,
        "ai_diagnosis": diagnosis,
        "ai_screenshot": shot,
        "error_details": details,
    }
