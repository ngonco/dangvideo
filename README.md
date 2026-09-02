# Tự Động Đăng Video — Quét HatBuiNho & Đăng Đa Nền Tảng

Hệ thống tự động tải video từ **HatBuiNho.com** và đăng lên **YouTube Shorts, TikTok, Facebook, Instagram**.

---

## Tải về và cài (khuyến nghị)

Tải file `.exe` bản mới nhất:

**https://github.com/ngonco/dangvideo/releases/latest**

1. Tải `Tu_dong_dang_video.exe`.
2. Click đúp để chạy. Dashboard mở tại `http://127.0.0.1:8000`.
3. Điền tài khoản HatBuiNho trên Dashboard, rồi **Mở Trình Duyệt Đăng Nhập** từng kênh (YouTube / TikTok / Facebook / Instagram) một lần.

Cookie đăng nhập, `browser_profiles`, `.env`, `data.db` và mật khẩu **chỉ nằm trên máy bạn** — không đưa lên GitHub.

---

## Mã nguồn (không gồm .exe)

[Tải ZIP mã nguồn `main`](https://github.com/ngonco/dangvideo/archive/refs/heads/main.zip)

Sao chép [`_system/config.example.json`](_system/config.example.json) thành `_system/config.json` rồi điền tài khoản. Không commit `config.json`.

---

## Tính năng

- Hẹn native công khai **10:00 sáng mai** trên YouTube, TikTok, Facebook.
- Instagram web: **Bài viết, Share ngay**, lấy permalink từ thanh địa chỉ.
- Hashtag đạo lý + hashtag phổ biến do AI chọn khi tải (không chữ ký thương hiệu).
- Tray icon, khởi động cùng Windows, dọn video cũ.

Tài liệu kỹ thuật: [`_system/SYSTEM_MAP.MD`](_system/SYSTEM_MAP.MD)
